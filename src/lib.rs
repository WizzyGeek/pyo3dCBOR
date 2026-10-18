//! Native Python bindings for deterministic CBOR (dCBOR).
//!
//! Encoding writes canonical bytes directly from Python values. Decoding and
//! diagnostic formatting operate on borrowed input slices after a complete
//! wire validation pass.

use pyo3::create_exception;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes};

mod diagnostic;
mod direct_decode;
mod direct_encode;
mod direct_wire;
mod encode;
mod key_conversion;
mod python_types;
mod scalars;
mod wire;

use python_types::{PyCborMap, PyCborTag};

create_exception!(_dcbor, CBORError, pyo3::exceptions::PyException);

/// Maximum recursion depth for nested containers on encode and decode paths.
const MAX_DEPTH: u32 = 512;

fn depth_err() -> PyErr {
    CBORError::new_err(format!(
        "structure nesting exceeds the maximum supported depth ({MAX_DEPTH})"
    ))
}

pub(crate) fn python_integer_parts(obj: &Bound<'_, PyAny>) -> PyResult<(u8, u64)> {
    // The caller has already established that `obj` is a Python int. Keep
    // the common i64 conversion cheap; every wider value in the dCBOR
    // interval fits in i128, so an i128 extraction overflow means it is out
    // of range.
    if let Ok(value) = obj.extract::<i64>() {
        return Ok(if value < 0 {
            (1, (-1i128 - i128::from(value)) as u64)
        } else {
            (0, value as u64)
        });
    }
    let value = obj.extract::<i128>().map_err(|_| {
        CBORError::new_err(
            "integer out of range for dCBOR (must fit in [-2^64, 2^64-1])",
        )
    })?;
    const MIN: i128 = -(1i128 << 64);
    const MAX: i128 = (1i128 << 64) - 1;
    if !(MIN..=MAX).contains(&value) {
        return Err(CBORError::new_err(
            "integer out of range for dCBOR (must fit in [-2^64, 2^64-1])",
        ));
    }

    if value < 0 {
        let magnitude = (-1i128 - value) as u64;
        Ok((1, magnitude))
    } else {
        Ok((0, value as u64))
    }
}

/// Encode a Python object as deterministic CBOR (dCBOR) bytes.
///
/// Supported types: `None`, `bool`, `int` (fitting in [-2**64, 2**64-1]),
/// `float`, `str`, `bytes`/`bytearray`, `list`/`tuple`, `dict`/`CBORMap`,
/// timezone-aware `datetime.datetime` (encoded as CBOR tag 1), and
/// `dcbor.CBORTag` for arbitrary tagged values.
#[pyfunction]
fn dumps(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyBytes>> {
    let mut data = Vec::new();
    direct_encode::encode_into(
        py,
        obj,
        0,
        &mut data,
        &mut encode::EncodeBudget::default(),
    )?;
    wire::preflight_trusted_output(&data)?;
    Ok(PyBytes::new(py, &data).unbind())
}

/// Decode dCBOR bytes into a Python object.
///
/// The decoder retains this immutable bytes object for CBORMap snapshots and
/// borrows all wire spans from it.
#[pyfunction]
fn loads(py: Python<'_>, data: &Bound<'_, PyBytes>) -> PyResult<Py<PyAny>> {
    direct_decode::decode(py, data)
}

/// Read a binary file object's contents once and decode its returned bytes.
#[pyfunction]
fn load(py: Python<'_>, file: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let data = file.call_method0("read")?;
    let data = data.cast::<PyBytes>()?;
    direct_decode::decode(py, data)
}

/// Return CBOR diagnostic notation for the given dCBOR bytes.
#[pyfunction(name = "diagnostic")]
fn diagnostic_str(data: &[u8]) -> PyResult<String> {
    diagnostic::format(data, false)
}

/// Return single-line CBOR diagnostic notation for the given dCBOR bytes.
#[pyfunction(name = "diagnostic_flat")]
fn diagnostic_flat_str(data: &[u8]) -> PyResult<String> {
    diagnostic::format(data, true)
}

/// Validate that `data` is well-formed dCBOR without materializing a Python
/// object; returns the number of bytes consumed.
#[pyfunction]
fn validate(data: &[u8]) -> PyResult<usize> {
    wire::preflight(data)?;
    Ok(data.len())
}

#[pymodule]
fn _dcbor(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__doc__", "Native PyO3 bindings for deterministic CBOR.")?;
    m.add("CBORError", py.get_type::<CBORError>())?;
    m.add_class::<PyCborTag>()?;
    m.add_class::<PyCborMap>()?;
    m.add_function(wrap_pyfunction!(dumps, m)?)?;
    m.add_function(wrap_pyfunction!(loads, m)?)?;
    m.add_function(wrap_pyfunction!(load, m)?)?;
    m.add_function(wrap_pyfunction!(diagnostic_str, m)?)?;
    m.add_function(wrap_pyfunction!(diagnostic_flat_str, m)?)?;
    m.add_function(wrap_pyfunction!(validate, m)?)?;
    Ok(())
}
