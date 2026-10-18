//! PyO3 bindings exposing Blockchain Commons' `dcbor` (deterministic CBOR)
//! Rust crate to Python. The bindings preserve map key identity, preflight
//! structural and resource limits, and leave numeric canonicality to the
//! patched decoder.

use dcbor::{ByteString, CBOR, CBORCase, Map, Simple, Tag};
use pyo3::create_exception;
use pyo3::prelude::*;
use pyo3::types::{
    PyBool, PyByteArray, PyBytes, PyDict, PyFloat, PyInt, PyList, PyString,
    PyTuple,
};
use pyo3::IntoPyObjectExt;

mod encode;
mod direct_encode;
mod direct_wire;
mod python_types;
mod key_conversion;
mod scalars;
mod wire;

use python_types::{PyCborMap, PyCborTag};

create_exception!(_dcbor, CBORError, pyo3::exceptions::PyException);

fn cbor_err(e: dcbor::Error) -> PyErr { CBORError::new_err(e.to_string()) }

/// Maximum recursion depth for nested containers, on both the encode and
/// decode paths. Guards against stack exhaustion from adversarial input
/// (deeply nested Python structures, or deeply nested dCBOR bytes handed
/// to `loads`/`diagnostic`).
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

fn python_integer_to_cbor(obj: &Bound<'_, PyAny>) -> PyResult<CBOR> {
    let (major, argument) = python_integer_parts(obj)?;
    Ok(if major == 1 {
        CBOR::from(CBORCase::Negative(argument))
    } else {
        CBOR::from(argument)
    })
}

/// Convert a Python object into a `dcbor::CBOR` value.
fn py_to_cbor(py: Python<'_>, obj: &Bound<'_, PyAny>, depth: u32) -> PyResult<CBOR> {
    py_to_cbor_with_budget(py, obj, depth, &mut encode::EncodeBudget::default())
}

fn py_to_cbor_key_with_budget(
    py: Python<'_>, obj: &Bound<'_, PyAny>, depth: u32,
    budget: &mut encode::EncodeBudget,
) -> PyResult<CBOR> {
    let before = budget.used();
    let mut key_budget = budget.fork_key();
    let key = py_to_cbor_with_budget(py, obj, depth, &mut key_budget)?;
    budget.reserve(key_budget.used() - before)?;
    Ok(key)
}

fn py_to_cbor_with_budget(
    py: Python<'_>, obj: &Bound<'_, PyAny>, depth: u32,
    budget: &mut encode::EncodeBudget,
) -> PyResult<CBOR> {
    if depth > MAX_DEPTH {
        return Err(depth_err());
    }
    if obj.is_none() {
        return budget.scalar(CBOR::from(CBORCase::Simple(Simple::Null)));
    }
    if let Ok(b) = obj.cast::<PyBool>() {
        return budget.scalar(CBOR::from(b.is_true()));
    }
    // Exact builtin nonintegers cannot implement Python's integer protocol.
    // Keep probing subclasses and custom objects so their `__index__`
    // behavior, including its precedence over their builtin base, is
    // unchanged. Convert arbitrary objects through that protocol only once;
    // the width probes below used to invoke stateful `__index__` methods
    // repeatedly.
    let needs_integer_probe = obj.cast::<PyInt>().is_ok()
        || !(obj.is_exact_instance_of::<PyFloat>()
            || obj.is_exact_instance_of::<PyString>()
            || obj.is_exact_instance_of::<PyBytes>()
            || obj.is_exact_instance_of::<PyByteArray>()
            || obj.is_exact_instance_of::<PyList>()
            || obj.is_exact_instance_of::<PyTuple>()
            || obj.is_exact_instance_of::<PyDict>());
    if needs_integer_probe {
        // Preserve the direct path for int instances. For other objects,
        // PyNumber_Index applies Python's integer protocol once and returns
        // a genuine Python int. Its error is intentionally discarded here:
        // historically failed `__index__` hooks fell through to the normal
        // "not dCBOR serializable" error, which callers already observe.
        if obj.cast::<PyInt>().is_ok() {
            return budget.scalar(python_integer_to_cbor(obj)?);
        }
        let indexed = unsafe {
            Bound::<PyAny>::from_owned_ptr_or_err(
                py,
                pyo3::ffi::PyNumber_Index(obj.as_ptr()),
            )
        };
        if let Ok(indexed) = indexed {
            return budget.scalar(python_integer_to_cbor(&indexed)?);
        }
    }
    if let Ok(f) = obj.cast::<PyFloat>() {
        return budget.scalar(CBOR::from(f.value()));
    }
    if let Ok(s) = obj.cast::<PyString>() {
        return budget.text(s);
    }
    if let Ok(b) = obj.cast::<PyBytes>() {
        budget.bytes(b.as_bytes().len())?;
        return Ok(CBOR::from(ByteString::new(b.as_bytes().to_vec())));
    }
    if let Ok(b) = obj.cast::<PyByteArray>() {
        budget.bytes(b.len())?;
        return Ok(CBOR::from(ByteString::new(unsafe { b.as_bytes() }.to_vec())));
    }
    if let Some(value) = scalars::encode_datetime(py, obj)? {
        // Datetime contributes an implicit tag just like explicit CBORTag.
        if depth == MAX_DEPTH {
            return Err(depth_err());
        }
        return budget.scalar(value);
    }
    if let Ok(tag_obj) = obj.extract::<PyRef<'_, PyCborTag>>() {
        if depth == MAX_DEPTH {
            return Err(depth_err());
        }
        budget.header(tag_obj.tag)?;
        let inner = py_to_cbor_with_budget(py, tag_obj.value.bind(py), depth + 1, budget)?;
        return Ok(CBOR::from(CBORCase::Tagged(
            Tag::with_value(tag_obj.tag),
            inner,
        )));
    }
    if let Ok(list) = obj.cast::<PyList>() {
        if depth == MAX_DEPTH {
            return Err(depth_err());
        }
        budget.header(list.len() as u64)?;
        let mut items = if budget.in_key() { Vec::new() } else { Vec::with_capacity(list.len()) };
        for item in list.iter() {
            items.push(py_to_cbor_with_budget(py, &item, depth + 1, budget)?);
        }
        return Ok(CBOR::from(items));
    }
    if let Ok(tuple) = obj.cast::<PyTuple>() {
        if depth == MAX_DEPTH {
            return Err(depth_err());
        }
        budget.header(tuple.len() as u64)?;
        let mut items = if budget.in_key() { Vec::new() } else { Vec::with_capacity(tuple.len()) };
        for item in tuple.iter() {
            items.push(py_to_cbor_with_budget(py, &item, depth + 1, budget)?);
        }
        return Ok(CBOR::from(items));
    }
    if let Ok(map) = obj.extract::<PyRef<'_, PyCborMap>>() {
        return map.to_cbor_with_budget(depth, budget);
    }
    if let Ok(dict) = obj.cast::<PyDict>() {
        if depth == MAX_DEPTH {
            return Err(depth_err());
        }
        // Retain candidate entries ourselves until replacement is resolved.
        // Upstream Map has no remove operation; delaying insertion lets an old
        // value and its cache be dropped before converting its replacement.
        let mut entries = std::collections::BTreeMap::<Vec<u8>, (CBOR, CBOR, usize)>::new();
        budget.header(0)?;
        for (k, v) in dict.iter() {
            // Canonical identity is known only after conversion. Convert once
            // with an independently bounded key context, preserving callbacks.
            let candidate_base = budget.used();
            let mut candidate_budget = budget.fork_key();
            let key_cbor = py_to_cbor_with_budget(py, &k, depth + 1, &mut candidate_budget)?;
            let candidate_cost = candidate_budget.used() - candidate_base;
            let encoded = key_cbor.to_cbor_data();
            let old_count = entries.len();
            if let Some((old_key, old_value, old_cost)) = entries.remove(&encoded) {
                drop((old_key, old_value));
                budget.release(old_cost);
            } else {
                budget.wire_bytes(encode::header_len((old_count + 1) as u64)
                    - encode::header_len(old_count as u64))?;
            }
            let before = budget.used();
            budget.reserve(candidate_cost)?;
            let val_cbor = py_to_cbor_with_budget(py, &v, depth + 1, budget)?;
            let cost = budget.used() - before;
            entries.insert(encoded, (key_cbor, val_cbor, cost));
        }
        let mut map = Map::new();
        for (_, (key, value, _)) in entries { map.insert(key, value); }

        return Ok(CBOR::from(map));
    }
    Err(CBORError::new_err(format!(
        "object of type '{}' is not dCBOR serializable",
        obj.get_type().name()?
    )))
}

/// Convert a `dcbor::CBOR` value into a Python object.
fn cbor_to_py(py: Python<'_>, cbor: &CBOR, depth: u32) -> PyResult<Py<PyAny>> {
    if depth > MAX_DEPTH {
        return Err(depth_err());
    }
    match cbor.as_case() {
        CBORCase::Unsigned(n) => n.into_py_any(py),
        CBORCase::Negative(n) => {
            let value = -1i128 - (*n as i128);
            value.into_py_any(py)
        }
        CBORCase::ByteString(b) => PyBytes::new(py, b).into_py_any(py),
        CBORCase::Text(s) => s.into_py_any(py),
        CBORCase::Array(items) => {
            let list = PyList::empty(py);
            for item in items {
                list.append(cbor_to_py(py, item, depth + 1)?)?;
            }
            list.into_py_any(py)
        }
        CBORCase::Map(map) => python_types::map_to_python(py, map, depth),
        CBORCase::Tagged(tag, item) => {
            if let Some(value) = scalars::decode_datetime(py, cbor)? {
                return Ok(value);
            }
            let inner = cbor_to_py(py, item, depth + 1)?;
            let tagged = PyCborTag { tag: tag.value(), value: inner };
            tagged.into_py_any(py)
        }
        CBORCase::Simple(s) => match s {
            Simple::True => true.into_py_any(py),
            Simple::False => false.into_py_any(py),
            Simple::Null => Ok(py.None()),
            Simple::Float(f) => f.into_py_any(py),
        },
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
    wire::preflight(&data)?;
    Ok(PyBytes::new(py, &data).unbind())
}

/// Decode dCBOR bytes into a Python object.
///
/// Raises `dcbor.CBORError` for malformed or noncanonical data, unsupported
/// numeric dates, excessive depth, or excessive encoded map-key storage.
/// Maps requiring keys that Python dicts cannot distinguish use `CBORMap`.
#[pyfunction]
fn loads(py: Python<'_>, data: &[u8]) -> PyResult<Py<PyAny>> {
    wire::preflight(data)?;
    let cbor = CBOR::try_from_data(data).map_err(cbor_err)?;
    cbor_to_py(py, &cbor, 0)
}

/// Return the CBOR diagnostic-notation string for the given dCBOR bytes.
#[pyfunction(name = "diagnostic")]
fn diagnostic_str(data: &[u8]) -> PyResult<String> {
    wire::preflight(data)?;
    let cbor = CBOR::try_from_data(data).map_err(cbor_err)?;
    Ok(cbor.diagnostic())
}

/// Return a single-line CBOR diagnostic-notation string for the given
/// dCBOR bytes.
#[pyfunction(name = "diagnostic_flat")]
fn diagnostic_flat_str(data: &[u8]) -> PyResult<String> {
    wire::preflight(data)?;
    let cbor = CBOR::try_from_data(data).map_err(cbor_err)?;
    Ok(cbor.diagnostic_flat())
}

/// Validate that `data` is well-formed dCBOR without materializing a
/// Python object; returns the number of bytes consumed.
#[pyfunction]
fn validate(data: &[u8]) -> PyResult<usize> {
    wire::preflight(data)?;
    CBOR::try_from_data(data).map_err(cbor_err)?;
    Ok(data.len())
}

#[pymodule]
fn _dcbor(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__doc__", "Native PyO3 bindings for the dcbor Rust crate.")?;
    m.add("CBORError", py.get_type::<CBORError>())?;
    m.add_class::<PyCborTag>()?;
    m.add_class::<PyCborMap>()?;
    m.add_function(wrap_pyfunction!(dumps, m)?)?;
    m.add_function(wrap_pyfunction!(loads, m)?)?;
    m.add_function(wrap_pyfunction!(diagnostic_str, m)?)?;
    m.add_function(wrap_pyfunction!(diagnostic_flat_str, m)?)?;
    m.add_function(wrap_pyfunction!(validate, m)?)?;
    Ok(())
}
