//! Direct Python-object to canonical dCBOR byte writer.
//!
//! This path keeps Python dispatch and callback order at the binding edge,
//! while writing ordinary values into a single caller-owned byte vector.
//! Maps retain only staged encoded keys and values until bytewise ordering is
//! known; frozen `CBORMap` snapshots are traversed directly from Rust state.

use crate::encode::EncodeBudget;
use crate::python_types::{PyCborMap, PyCborTag};
use crate::{depth_err, python_integer_parts, scalars, CBORError, MAX_DEPTH};
use dcbor::{CBOR, CBORCase, Map, Simple};
use pyo3::prelude::*;
use pyo3::sync::critical_section::with_critical_section;
use pyo3::types::{PyBool, PyByteArray, PyBytes, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple};
use std::collections::BTreeMap;
use unicode_normalization::{is_nfc, UnicodeNormalization};

use crate::direct_wire::{self, FloatEncoding};

pub(crate) fn encode_into(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
    depth: u32,
    out: &mut Vec<u8>,
    budget: &mut EncodeBudget,
) -> PyResult<()> {
    if depth > MAX_DEPTH {
        return Err(depth_err());
    }

    if obj.is_none() {
        budget.wire_bytes(1)?;
        out.push(0xf6);
        return Ok(());
    }
    if let Ok(value) = obj.cast::<PyBool>() {
        budget.wire_bytes(1)?;
        out.push(if value.is_true() { 0xf5 } else { 0xf4 });
        return Ok(());
    }

    // Preserve the tree converter's protocol dispatch and one-call behavior:
    // Python int subclasses and custom objects get one __index__ attempt,
    // while exact non-integer builtins skip it.
    let needs_integer_probe = obj.cast::<PyInt>().is_ok()
        || !(obj.is_exact_instance_of::<PyFloat>()
            || obj.is_exact_instance_of::<PyString>()
            || obj.is_exact_instance_of::<PyBytes>()
            || obj.is_exact_instance_of::<PyByteArray>()
            || obj.is_exact_instance_of::<PyList>()
            || obj.is_exact_instance_of::<PyTuple>()
            || obj.is_exact_instance_of::<PyDict>());
    if needs_integer_probe {
        if obj.cast::<PyInt>().is_ok() {
            write_integer(obj, out, budget)?;
            return Ok(());
        }
        let indexed = unsafe {
            Bound::<PyAny>::from_owned_ptr_or_err(
                py,
                pyo3::ffi::PyNumber_Index(obj.as_ptr()),
            )
        };
        if let Ok(indexed) = indexed {
            write_integer(&indexed, out, budget)?;
            return Ok(());
        }
    }

    if let Ok(value) = obj.cast::<PyFloat>() {
        write_float(value.value(), out, budget)?;
        return Ok(());
    }
    if let Ok(text) = obj.cast::<PyString>() {
        write_python_text(text, out, budget)?;
        return Ok(());
    }
    if let Ok(bytes) = obj.cast::<PyBytes>() {
        let payload = bytes.as_bytes();
        budget.bytes(payload.len())?;
        direct_wire::write_header(2, payload.len() as u64, out);
        out.extend_from_slice(payload);
        return Ok(());
    }
    if let Ok(bytes) = obj.cast::<PyByteArray>() {
        // The bytearray can be shared and mutable. Keep the borrowed slice
        // within the public per-object guard and perform only Rust-side budget
        // arithmetic and copying while it is live.
        let copied = with_critical_section(bytes, || {
            // Read the length and charge its complete wire cost under the
            // same object guard as the subsequent borrow and copy. If the
            // check fails, no raw slice is acquired.
            let length = bytes.len();
            if !budget.try_payload_bytes(length) {
                return false;
            }
            // SAFETY: the object critical section (or GIL in regular builds)
            // remains held through the immediate copy; no Python/PyO3 call,
            // callback, mutation, or detach occurs while this slice is live.
            let payload = unsafe { bytes.as_bytes() };
            direct_wire::write_header(2, length as u64, out);
            out.extend_from_slice(payload);
            true
        });
        return if copied {
            Ok(())
        } else {
            Err(crate::encode::budget_error())
        };
    }

    // Like the old converter, datetime recognition follows integer probing
    // and precedes explicit CBORTag dispatch. Timestamp hooks complete before
    // any wire bytes for this value are appended.
    if let Some(seconds) = scalars::datetime_timestamp(py, obj)? {
        if depth == MAX_DEPTH {
            return Err(depth_err());
        }
        budget.header(1)?;
        direct_wire::write_header(6, 1, out);
        write_float(seconds, out, budget)?;
        return Ok(());
    }

    if let Ok(tag) = obj.extract::<PyRef<'_, PyCborTag>>() {
        if depth == MAX_DEPTH {
            return Err(depth_err());
        }
        // Preserve the old immutable PyRef across recursive conversion. User
        // callbacks in the child therefore observe the same borrow behavior.
        budget.header(tag.tag)?;
        direct_wire::write_header(6, tag.tag, out);
        encode_into(py, tag.value.bind(py), depth + 1, out, budget)?;
        return Ok(());
    }

    if let Ok(list) = obj.cast::<PyList>() {
        if depth == MAX_DEPTH {
            return Err(depth_err());
        }
        let initial_len = list.len();
        budget.header(initial_len as u64)?;
        let mut iter = list.iter();
        let header_start = out.len();
        direct_wire::write_header(4, initial_len as u64, out);
        let initial_head_len = out.len() - header_start;
        // PyO3's iterator caps visits at its initial length but sees removals;
        // only rewrite/compact the head if the visited count changed.
        let mut visited = 0usize;
        for item in &mut iter {
            encode_into(py, &item, depth + 1, out, budget)?;
            visited += 1;
        }
        if visited != initial_len {
            compact_header(out, header_start, initial_head_len, 4, visited as u64);
        }
        return Ok(());
    }

    if let Ok(tuple) = obj.cast::<PyTuple>() {
        if depth == MAX_DEPTH {
            return Err(depth_err());
        }
        budget.header(tuple.len() as u64)?;
        direct_wire::write_header(4, tuple.len() as u64, out);
        for item in tuple.iter() {
            encode_into(py, &item, depth + 1, out, budget)?;
        }
        return Ok(());
    }

    if let Ok(snapshot) = obj.extract::<PyRef<'_, PyCborMap>>() {
        budget.reserve_snapshot(&snapshot.map, depth)?;
        write_snapshot_map(&snapshot.map, depth, out)?;
        return Ok(());
    }

    if let Ok(dict) = obj.cast::<PyDict>() {
        if depth == MAX_DEPTH {
            return Err(depth_err());
        }
        write_dict(py, dict, depth, out, budget)?;
        return Ok(());
    }

    Err(CBORError::new_err(format!(
        "object of type '{}' is not dCBOR serializable",
        obj.get_type().name()?
    )))
}

fn write_integer(
    obj: &Bound<'_, PyAny>,
    out: &mut Vec<u8>,
    budget: &mut EncodeBudget,
) -> PyResult<()> {
    let (major, argument) = python_integer_parts(obj)?;
    budget.header(argument)?;
    direct_wire::write_header(major, argument, out);
    Ok(())
}

fn write_float(value: f64, out: &mut Vec<u8>, budget: &mut EncodeBudget) -> PyResult<()> {
    let encoding = FloatEncoding::from_f64(value);
    budget.wire_bytes(encoding.encoded_len())?;
    encoding.write_to(out);
    Ok(())
}

fn write_text(value: &str, out: &mut Vec<u8>) {
    direct_wire::write_header(3, value.len() as u64, out);
    out.extend_from_slice(value.as_bytes());
}

fn write_python_text(
    text: &Bound<'_, PyString>,
    out: &mut Vec<u8>,
    budget: &mut EncodeBudget,
) -> PyResult<()> {
    let source = text.to_str().map_err(|_| {
        CBORError::new_err("Python string contains surrogate code points that cannot be encoded as CBOR UTF-8 text")
    })?;
    if source.is_ascii() || is_nfc(source) {
        budget.bytes(source.len())?;
        write_text(source, out);
        return Ok(());
    }

    // Charge the normalized encoded length incrementally before growing the
    // Rust string. Unicode normalization itself can buffer a non-starter run
    // before yielding; see the memory-access note for that known limitation.
    let mut normalized = String::new();
    budget.header(0)?;
    for ch in source.nfc() {
        let old_length = normalized.len();
        let new_length = old_length.checked_add(ch.len_utf8())
            .ok_or_else(crate::encode::budget_error)?;
        let header_delta = direct_wire::header_len(new_length as u64)
            - direct_wire::header_len(old_length as u64);
        budget.wire_bytes(ch.len_utf8() + header_delta)?;
        normalized.push(ch);
    }
    write_text(&normalized, out);
    Ok(())
}

/// Patch an initial canonical array head to the actual visited item count.
fn compact_header(out: &mut Vec<u8>, start: usize, old_len: usize, major: u8, value: u64) {
    let mut head = [0u8; 9];
    let head_len = header_bytes(major, value, &mut head);
    debug_assert!(head_len <= old_len, "list iteration cannot exceed initial length");
    out[start..start + head_len].copy_from_slice(&head[..head_len]);
    if head_len < old_len {
        let body_start = start + old_len;
        out.copy_within(body_start.., start + head_len);
        out.truncate(out.len() - (old_len - head_len));
    }
}

/// Stack-buffer form used only when patching an array head after traversal.
fn header_bytes(major: u8, value: u64, out: &mut [u8; 9]) -> usize {
    let prefix = major << 5;
    match value {
        0..=23 => {
            out[0] = prefix | value as u8;
            1
        }
        24..=255 => {
            out[0] = prefix | 24;
            out[1] = value as u8;
            2
        }
        256..=65_535 => {
            out[0] = prefix | 25;
            out[1..3].copy_from_slice(&(value as u16).to_be_bytes());
            3
        }
        65_536..=4_294_967_295 => {
            out[0] = prefix | 26;
            out[1..5].copy_from_slice(&(value as u32).to_be_bytes());
            5
        }
        _ => {
            out[0] = prefix | 27;
            out[1..9].copy_from_slice(&value.to_be_bytes());
            9
        }
    }
}

struct StagedEntry {
    value: Vec<u8>,
    budget_cost: usize,
}

fn write_dict(
    py: Python<'_>,
    dict: &Bound<'_, PyDict>,
    depth: u32,
    out: &mut Vec<u8>,
    budget: &mut EncodeBudget,
) -> PyResult<()> {
    // Retain only encoded bytes, preserving one-pass insertion-order callback
    // semantics. Per-entry buffers make canonical replacement reclaimable.
    let mut entries = BTreeMap::<Vec<u8>, StagedEntry>::new();
    budget.header(0)?;
    for (key, value) in dict.iter() {
        let candidate_base = budget.used();
        let mut candidate_budget = budget.fork_key();
        let mut encoded_key = Vec::new();
        encode_into(py, &key, depth + 1, &mut encoded_key, &mut candidate_budget)?;
        let candidate_cost = candidate_budget.used() - candidate_base;

        let old_count = entries.len();
        if let Some(old) = entries.remove(&encoded_key) {
            budget.release(old.budget_cost);
            drop(old);
        } else {
            let header_delta = direct_wire::header_len((old_count + 1) as u64)
                - direct_wire::header_len(old_count as u64);
            budget.wire_bytes(header_delta)?;
        }

        // This delta intentionally starts before committing the candidate
        // key cost, so a later collision releases both key-cache and value
        // accounting together.
        let before_entry = budget.used();
        budget.reserve(candidate_cost)?;
        let mut encoded_value = Vec::new();
        encode_into(py, &value, depth + 1, &mut encoded_value, budget)?;
        let entry_cost = budget.used() - before_entry;
        entries.insert(
            encoded_key,
            StagedEntry { value: encoded_value, budget_cost: entry_cost },
        );
    }

    direct_wire::write_header(5, entries.len() as u64, out);
    for (key, value) in entries {
        out.extend_from_slice(&key);
        out.extend_from_slice(&value.value);
    }
    Ok(())
}

fn write_snapshot_map(map: &Map, depth: u32, out: &mut Vec<u8>) -> PyResult<()> {
    if depth >= MAX_DEPTH {
        return Err(depth_err());
    }
    direct_wire::write_header(5, map.len() as u64, out);
    for (key, value) in map.iter() {
        write_snapshot_cbor(key, depth + 1, out)?;
        write_snapshot_cbor(value, depth + 1, out)?;
    }
    Ok(())
}

fn write_snapshot_cbor(cbor: &CBOR, depth: u32, out: &mut Vec<u8>) -> PyResult<()> {
    if depth > MAX_DEPTH {
        return Err(depth_err());
    }
    match cbor.as_case() {
        CBORCase::Unsigned(value) => direct_wire::write_header(0, *value, out),
        CBORCase::Negative(value) => direct_wire::write_header(1, *value, out),
        CBORCase::ByteString(value) => {
            direct_wire::write_header(2, value.len() as u64, out);
            out.extend_from_slice(value);
        }
        CBORCase::Text(value) => write_snapshot_text(value, out),
        CBORCase::Array(values) => {
            if depth == MAX_DEPTH {
                return Err(depth_err());
            }
            direct_wire::write_header(4, values.len() as u64, out);
            for value in values {
                write_snapshot_cbor(value, depth + 1, out)?;
            }
        }
        CBORCase::Map(map) => write_snapshot_map(map, depth, out)?,
        CBORCase::Tagged(tag, value) => {
            if depth == MAX_DEPTH {
                return Err(depth_err());
            }
            direct_wire::write_header(6, tag.value(), out);
            write_snapshot_cbor(value, depth + 1, out)?;
        }
        CBORCase::Simple(Simple::False) => out.push(0xf4),
        CBORCase::Simple(Simple::True) => out.push(0xf5),
        CBORCase::Simple(Simple::Null) => out.push(0xf6),
        CBORCase::Simple(Simple::Float(value)) => {
            FloatEncoding::from_f64(*value).write_to(out);
        }
    }
    Ok(())
}

fn write_snapshot_text(value: &str, out: &mut Vec<u8>) {
    // `CBORMap` snapshots can only be created from NFC-normalized Python
    // values or canonical validated decoder output. Preserve their stored
    // UTF-8 bytes directly instead of normalizing into another String.
    write_text(value, out);
}
