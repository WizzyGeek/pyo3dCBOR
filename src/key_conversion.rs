//! Decode map keys without changing their canonical CBOR encoding.
//!
//! Datetime is a convenient scalar representation but cannot express every
//! floating-point epoch timestamp. A key must retain its encoded identity, so
//! retain a tag whenever its datetime conversion would change the bytes.
use dcbor::{CBORCase, CBOR};
use pyo3::prelude::*;
use pyo3::types::PyList;
use pyo3::IntoPyObjectExt;

use crate::python_types::{PyCborMap, PyCborTag};
use crate::{cbor_to_py, depth_err, py_to_cbor, MAX_DEPTH};

pub(crate) fn cbor_key_to_py(
    py: Python<'_>,
    cbor: &CBOR,
    depth: u32,
) -> PyResult<Py<PyAny>> {
    if depth > MAX_DEPTH {
        return Err(depth_err());
    }
    match cbor.as_case() {
        CBORCase::Array(items) => {
            let list = PyList::empty(py);
            for item in items {
                list.append(cbor_key_to_py(py, item, depth + 1)?)?;
            }
            list.into_py_any(py)
        }
        CBORCase::Map(map) => {
            // The entire map is part of the outer key: even its values must
            // preserve their bytes. Keep the original snapshot, but eagerly
            // validate every descendant so invalid date tags fail at loads().
            for (key, value) in map.iter() {
                cbor_key_to_py(py, key, depth + 1)?;
                cbor_key_to_py(py, value, depth + 1)?;
            }
            PyCborMap { map: map.clone() }.into_py_any(py)
        }
        CBORCase::Tagged(tag, value) => {
            // decode_datetime also performs the supported-range checks. Its
            // errors must propagate even when a CBORTag could preserve bytes.
            if let Some(candidate) = crate::scalars::decode_datetime(py, cbor)? {
                let encoded = py_to_cbor(py, candidate.bind(py), depth)?;
                if encoded.to_cbor_data() == cbor.to_cbor_data() {
                    return Ok(candidate);
                }
            }
            PyCborTag {
                tag: tag.value(),
                value: cbor_key_to_py(py, value, depth + 1)?,
            }
            .into_py_any(py)
        }
        _ => cbor_to_py(py, cbor, depth),
    }
}
