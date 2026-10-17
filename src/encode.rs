//! Conversion-scoped accounting before upstream Map caches are allocated.
use crate::{depth_err, CBORError, MAX_DEPTH};
use dcbor::{CBOR, CBORCase, Map};
use pyo3::prelude::*;
use pyo3::types::PyString;
use std::cell::RefCell;
use std::collections::HashMap;
use std::rc::Rc;
use unicode_normalization::UnicodeNormalization;

const TEXT_REUSE_CACHE_BYTES: usize = 2 * 1024 * 1024;

#[derive(Default)]
struct TextReuseCache {
    bytes: usize,
    values: HashMap<usize, (Py<PyString>, CBOR)>,
}

pub(crate) struct EncodeBudget {
    key_bytes: usize,
    /// Every byte of the current subtree is retained in each enclosing key.
    active_keys: usize,
    /// Python strings are immutable. Sharing their normalized CBOR value keeps
    /// repeated references from multiplying the non-cache representation while
    /// each map's encoded-key cache is still charged independently.
    texts: Rc<RefCell<TextReuseCache>>,
}

impl Default for EncodeBudget {
    fn default() -> Self {
        Self {
            key_bytes: 0,
            active_keys: 0,
            texts: Rc::new(RefCell::new(TextReuseCache::default())),
        }
    }
}

fn budget_error() -> PyErr {
    CBORError::new_err("encoded map key cache exceeds the maximum supported size")
}

impl EncodeBudget {
    pub(crate) fn used(&self) -> usize { self.key_bytes }
    pub(crate) fn in_key(&self) -> bool { self.active_keys != 0 }
    pub(crate) fn fork_key(&self) -> Self {
        // Keep the parent's live charge in the fork so constructing a
        // candidate key cannot temporarily exceed the process-wide limit.
        Self {
            key_bytes: self.key_bytes,
            active_keys: self.active_keys + 1,
            texts: Rc::clone(&self.texts),
        }
    }
    pub(crate) fn release(&mut self, amount: usize) { self.key_bytes -= amount; }
    pub(crate) fn reserve(&mut self, amount: usize) -> PyResult<()> {
        self.key_bytes = self.key_bytes.checked_add(amount)
            .filter(|total| *total <= crate::wire::MAX_KEY_CACHE_BYTES)
            .ok_or_else(budget_error)?;
        Ok(())
    }
    pub(crate) fn wire_bytes(&mut self, bytes: usize) -> PyResult<()> {
        self.reserve(bytes.checked_mul(self.active_keys).ok_or_else(budget_error)?)
    }
    pub(crate) fn header(&mut self, value: u64) -> PyResult<()> {
        self.wire_bytes(header_len(value))
    }
    pub(crate) fn scalar(&mut self, cbor: CBOR) -> PyResult<CBOR> {
        self.wire_bytes(encoded_len(&cbor)?)?;
        Ok(cbor)
    }
    pub(crate) fn bytes(&mut self, length: usize) -> PyResult<()> {
        self.wire_bytes(add(header_len(length as u64), length)?)
    }

    pub(crate) fn text(&mut self, text: &Bound<'_, PyString>) -> PyResult<CBOR> {
        if !self.in_key() { return crate::scalars::encode_text(text); }
        let identity = text.as_ptr() as usize;
        let cached = self.texts.borrow().values.get(&identity)
            .filter(|(source, _)| source.bind(text.py()).is(text))
            .map(|(_, cbor)| cbor.clone());
        if let Some(cbor) = cached {
            self.wire_bytes(encoded_len(&cbor)?)?;
            return Ok(cbor);
        }
        let value = text.to_str().map_err(|_| CBORError::new_err(
            "Python string contains surrogate code points that cannot be encoded as CBOR UTF-8 text"))?;
        let normalized = if value.is_ascii() {
            self.bytes(value.len())?;
            value.to_owned()
        } else {
            let mut normalized = String::new();
            self.header(0)?;
            for ch in value.nfc() {
                let old_length = normalized.len();
                let new_length = add(old_length, ch.len_utf8())?;
                self.wire_bytes(ch.len_utf8() + header_len(new_length as u64)
                    - header_len(old_length as u64))?;
                normalized.push(ch);
            }
            normalized
        };
        let cbor: CBOR = CBORCase::Text(normalized).into();
        let size = encoded_len(&cbor)?;
        if size <= TEXT_REUSE_CACHE_BYTES {
            let mut cache = self.texts.borrow_mut();
            if cache.bytes.saturating_add(size) > TEXT_REUSE_CACHE_BYTES {
                cache.values.clear();
                cache.bytes = 0;
            }
            cache
                .values
                .insert(identity, (text.clone().unbind(), cbor.clone()));
            cache.bytes += size;
        }
        Ok(cbor)
    }

    /// Charge every expanded wire occurrence before cloning retained caches.
    pub(crate) fn reserve_snapshot(&mut self, map: &Map, depth: u32) -> PyResult<()> {
        if depth >= MAX_DEPTH { return Err(depth_err()); }
        self.header(map.len() as u64)?;
        for (key, value) in map.iter() {
            self.active_keys += 1;
            let result = self.reserve_subtree(key, depth + 1);
            self.active_keys -= 1;
            result?;
            self.reserve_subtree(value, depth + 1)?;
        }
        Ok(())
    }

    fn reserve_subtree(&mut self, cbor: &CBOR, depth: u32) -> PyResult<()> {
        if depth > MAX_DEPTH { return Err(depth_err()); }
        match cbor.as_case() {
            CBORCase::Map(map) => self.reserve_snapshot(map, depth),
            CBORCase::Array(items) => {
                if depth >= MAX_DEPTH { return Err(depth_err()); }
                self.header(items.len() as u64)?;
                for item in items { self.reserve_subtree(item, depth + 1)?; }
                Ok(())
            }
            CBORCase::Tagged(tag, item) => {
                if depth >= MAX_DEPTH { return Err(depth_err()); }
                self.header(tag.value())?;
                self.reserve_subtree(item, depth + 1)
            }
            _ => self.wire_bytes(encoded_len(cbor)?),
        }
    }
}

pub(crate) fn header_len(value: u64) -> usize {
    match value { 0..=23 => 1, 24..=255 => 2, 256..=65535 => 3,
        65536..=4294967295 => 5, _ => 9 }
}

fn add(a: usize, b: usize) -> PyResult<usize> {
    a.checked_add(b).ok_or_else(budget_error)
}

/// Compute wire length without creating another full encoded copy of a key.
fn encoded_len(cbor: &CBOR) -> PyResult<usize> {
    match cbor.as_case() {
        CBORCase::Unsigned(n) | CBORCase::Negative(n) => Ok(header_len(*n)),
        CBORCase::ByteString(bytes) => add(header_len(bytes.len() as u64), bytes.len()),
        CBORCase::Text(text) => add(header_len(text.len() as u64), text.len()),
        CBORCase::Tagged(tag, item) => add(header_len(tag.value()), encoded_len(item)?),
        CBORCase::Array(items) => {
            let mut size = header_len(items.len() as u64);
            for item in items { size = add(size, encoded_len(item)?)?; }
            Ok(size)
        }
        CBORCase::Map(map) => {
            let mut size = header_len(map.len() as u64);
            for (key, value) in map.iter() {
                size = add(size, encoded_len(key)?)?;
                size = add(size, encoded_len(value)?)?;
            }
            Ok(size)
        }
        CBORCase::Simple(_) => Ok(cbor.to_cbor_data().len()),
    }
}
