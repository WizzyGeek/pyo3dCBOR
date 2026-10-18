//! Borrowed CBOR wire-to-Python decoding.
//!
//! The complete input is validated before this module allocates Python
//! objects. Decoding then walks the original bytes directly, copying only
//! payloads that must become owned Python bytes or strings. Lossless maps
//! retain the original `PyBytes` and a byte span instead of building a CBOR
//! object tree.

use half::f16;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};
use pyo3::IntoPyObjectExt;
use std::ops::Range;

use crate::python_types::PyCborTag;
use crate::wire::{self, Cursor, Header};
use crate::{depth_err, CBORError, MAX_DEPTH};

/// Validate an entire immutable bytes object, then decode it directly from
/// its storage. The caller retains ownership of `owner` while this function
/// runs; any lossless-map result takes its own reference before returning.
pub(crate) fn decode(
    py: Python<'_>,
    owner: &Bound<'_, PyBytes>,
) -> PyResult<Py<PyAny>> {
    let data = owner.as_bytes();
    wire::preflight(data)?;
    decode_preflighted_range(py, owner, 0..data.len(), 0, false)
}

/// Decode one byte range from an immutable owner. This is used by CBORMap's
/// accessors, whose source was already validated when its snapshot was made.
/// Revalidating the requested range also keeps this helper safe when called
/// independently by future native code.
pub(crate) fn decode_range(
    py: Python<'_>,
    owner: &Bound<'_, PyBytes>,
    range: Range<usize>,
    depth: u32,
    key_context: bool,
) -> PyResult<Py<PyAny>> {
    let data = owner.as_bytes();
    let encoded = data.get(range.clone()).ok_or_else(wire::invalid_data)?;
    wire::preflight_at_depth(encoded, depth)?;
    decode_preflighted_range(py, owner, range, depth, key_context)
}

fn decode_preflighted_range(
    py: Python<'_>,
    owner: &Bound<'_, PyBytes>,
    range: Range<usize>,
    depth: u32,
    key_context: bool,
) -> PyResult<Py<PyAny>> {
    let mut cursor = Cursor::with_range(owner.as_bytes(), range)?;
    let value = decode_item(py, owner, &mut cursor, depth, key_context)?;
    cursor.finish()?;
    Ok(value)
}

fn decode_item(
    py: Python<'_>,
    owner: &Bound<'_, PyBytes>,
    cursor: &mut Cursor<'_>,
    depth: u32,
    key_context: bool,
) -> PyResult<Py<PyAny>> {
    if depth > MAX_DEPTH {
        return Err(depth_err());
    }

    let header = cursor.read_header()?;
    match header.major {
        0 => header.argument.into_py_any(py),
        1 => (-1i128 - i128::from(header.argument)).into_py_any(py),
        2 => {
            let payload = cursor.read_payload(header.argument)?;
            PyBytes::new(py, payload).into_py_any(py)
        }
        3 => {
            let payload = cursor.read_payload(header.argument)?;
            let text = std::str::from_utf8(payload).map_err(|error| {
                CBORError::new_err(format!("invalid UTF‑8 string: {error}"))
            })?;
            pyo3::types::PyString::new(py, text).into_py_any(py)
        }
        4 => decode_array(py, owner, cursor, header, depth, key_context),
        5 => decode_map(py, owner, cursor, header, depth, key_context),
        6 => decode_tag(py, owner, cursor, header, depth, key_context),
        7 => decode_simple(py, header),
        _ => Err(wire::invalid_data()),
    }
}

fn decode_array(
    py: Python<'_>,
    owner: &Bound<'_, PyBytes>,
    cursor: &mut Cursor<'_>,
    header: Header,
    depth: u32,
    key_context: bool,
) -> PyResult<Py<PyAny>> {
    if depth == MAX_DEPTH {
        return Err(depth_err());
    }

    let result = PyList::empty(py);
    for _ in 0..header.argument {
        result.append(decode_item(
            py,
            owner,
            cursor,
            depth + 1,
            key_context,
        )?)?;
    }
    result.into_py_any(py)
}

fn decode_map(
    py: Python<'_>,
    owner: &Bound<'_, PyBytes>,
    cursor: &mut Cursor<'_>,
    header: Header,
    depth: u32,
    key_context: bool,
) -> PyResult<Py<PyAny>> {
    if depth == MAX_DEPTH {
        return Err(depth_err());
    }

    let start = header.start;
    let mut fallback = key_context;
    let result = if fallback {
        None
    } else {
        Some(PyDict::new(py))
    };

    for _ in 0..header.argument {
        // Keys always decode in key context so nested values preserve their
        // encoded datetime precision, while arrays stay unhashable lists.
        let key = decode_item(py, owner, cursor, depth + 1, true)?;
        // When the map itself is nested inside a map key, its values are part
        // of that key's lossless identity too.
        let value = decode_item(py, owner, cursor, depth + 1, key_context)?;

        if !fallback {
            let dict = result.as_ref().expect("non-fallback map has a dict");
            let before = dict.len();
            match dict.set_item(key.bind(py), value.bind(py)) {
                Ok(()) if dict.len() == before + 1 => (),
                Ok(()) => fallback = true,
                Err(error) if error.is_instance_of::<pyo3::exceptions::PyTypeError>(py) => {
                    fallback = true;
                }
                Err(error) => return Err(error),
            }
        }
    }

    if fallback {
        let end = cursor.position();
        crate::python_types::map_from_encoded(py, owner, start..end, depth)
    } else {
        result.expect("ordinary map retains its dict").into_py_any(py)
    }
}

fn decode_tag(
    py: Python<'_>,
    owner: &Bound<'_, PyBytes>,
    cursor: &mut Cursor<'_>,
    header: Header,
    depth: u32,
    key_context: bool,
) -> PyResult<Py<PyAny>> {
    if depth == MAX_DEPTH {
        return Err(depth_err());
    }

    let numeric_datetime = if header.argument == 1 {
        let mut probe = *cursor;
        let child = probe.read_header()?;
        child.major == 0
            || child.major == 1
            || (child.major == 7 && matches!(child.additional_info, 25..=27))
    } else {
        false
    };

    let value = decode_item(py, owner, cursor, depth + 1, key_context)?;
    if numeric_datetime {
        let datetime = crate::scalars::decode_datetime_timestamp(py, value.bind(py))?;
        if key_context {
            let mut encoded = Vec::new();
            crate::direct_encode::encode_into(
                py,
                datetime.bind(py),
                depth,
                &mut encoded,
                &mut crate::encode::EncodeBudget::default(),
            )?;
            if cursor.span(header.start, cursor.position())? != encoded.as_slice() {
                return PyCborTag {
                    tag: header.argument,
                    value,
                }
                .into_py_any(py);
            }
        }
        Ok(datetime)
    } else {
        PyCborTag {
            tag: header.argument,
            value,
        }
        .into_py_any(py)
    }
}

fn decode_simple(py: Python<'_>, header: Header) -> PyResult<Py<PyAny>> {
    match header.additional_info {
        20 => false.into_py_any(py),
        21 => true.into_py_any(py),
        22 => Ok(py.None()),
        25 => f16::from_bits(header.argument as u16)
            .to_f64()
            .into_py_any(py),
        26 => (f32::from_bits(header.argument as u32) as f64).into_py_any(py),
        27 => f64::from_bits(header.argument).into_py_any(py),
        _ => Err(CBORError::new_err(
            "an invalid CBOR simple value was encountered",
        )),
    }
}
