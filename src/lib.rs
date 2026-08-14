//! PyO3 bindings exposing Blockchain Commons' `dcbor` (deterministic CBOR)
//! Rust crate to Python. All encoding/decoding is delegated to the real
//! `dcbor` crate; this module only converts between Python objects and
//! `dcbor::CBOR` values.

use dcbor::{ByteString, CBOR, CBORCase, Date, Map, Simple, Tag};
use pyo3::create_exception;
use pyo3::prelude::*;
use pyo3::types::{
    PyBool, PyByteArray, PyBytes, PyDict, PyFloat, PyInt, PyList, PyString,
    PyTuple,
};
use pyo3::IntoPyObjectExt;

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

/// Read a CBOR header's "argument" value (the length/count/tag-value/simple
/// -value encoded by the low 5 bits of the initial byte, per RFC 8949
/// §3), advancing `pos` past any following bytes it consumes. Used only
/// for the iterative pre-scan below -- it does not validate canonicality.
fn read_arg(info: u8, data: &[u8], pos: &mut usize) -> Result<u64, ()> {
    match info {
        0..=23 => Ok(info as u64),
        24 => {
            let b = *data.get(*pos).ok_or(())?;
            *pos += 1;
            Ok(b as u64)
        }
        25 => {
            let b = data.get(*pos..*pos + 2).ok_or(())?;
            *pos += 2;
            Ok(u16::from_be_bytes([b[0], b[1]]) as u64)
        }
        26 => {
            let b = data.get(*pos..*pos + 4).ok_or(())?;
            *pos += 4;
            Ok(u32::from_be_bytes([b[0], b[1], b[2], b[3]]) as u64)
        }
        27 => {
            let b = data.get(*pos..*pos + 8).ok_or(())?;
            *pos += 8;
            Ok(u64::from_be_bytes(b.try_into().map_err(|_| ())?))
        }
        _ => Err(()),
    }
}

/// Iteratively pre-scan raw dCBOR bytes to bound the maximum container
/// nesting depth (arrays, maps, tags) *before* handing the data to the
/// real recursive decoder in the `dcbor` crate. The crate's own decoder
/// recurses once per nesting level with no depth limit, so adversarial
/// input (e.g. hundreds of thousands of nested single-element arrays)
/// can exhaust the stack and crash the process outright -- a crash can't
/// be caught as a Python exception, so it must be prevented before it
/// starts. This function does not fully validate the input; malformed
/// data that isn't caught here is still rejected by the real decoder
/// afterward. Any parse failure here is treated as "not too deep" and
/// left for the real decoder to diagnose properly.
fn check_max_depth(data: &[u8]) -> PyResult<()> {
    let mut pos: usize = 0;
    let mut stack: Vec<u64> = Vec::new();

    loop {
        let Some(&byte) = data.get(pos) else { return Ok(()) };
        pos += 1;
        let major = byte >> 5;
        let info = byte & 0x1f;
        let Ok(value) = read_arg(info, data, &mut pos) else { return Ok(()) };

        match major {
            0 | 1 | 7 => {
                // Leaf: no nested content, nothing more to consume here.
            }
            2 | 3 => {
                let len = value as usize;
                match pos.checked_add(len) {
                    Some(end) if end <= data.len() => pos = end,
                    _ => return Ok(()),
                }
            }
            4 | 5 | 6 => {
                let remaining = match major {
                    4 => value,
                    5 => match value.checked_mul(2) {
                        Some(n) => n,
                        None => return Ok(()),
                    },
                    _ => 1, // tag: exactly one nested item follows
                };
                if (stack.len() as u32) + 1 > MAX_DEPTH {
                    return Err(depth_err());
                }
                if remaining > 0 {
                    stack.push(remaining);
                }
                continue;
            }
            _ => return Ok(()),
        }

        // Just finished a leaf item: close out any container frames it
        // completed, popping ancestors whose count has now reached zero.
        loop {
            match stack.last_mut() {
                None => return Ok(()), // finished the single top-level item
                Some(top) => {
                    *top -= 1;
                    if *top == 0 {
                        stack.pop();
                        continue;
                    }
                    break;
                }
            }
        }
    }
}

/// A CBOR tagged value (major type 6): a semantic tag number plus an
/// inner value. Returned by `loads()` for tags dcbor-py does not map to a
/// richer Python type (e.g. datetimes), and accepted by `dumps()` to
/// produce arbitrary tagged CBOR.
#[pyclass(module = "dcbor", name = "CBORTag", skip_from_py_object)]
pub struct PyCborTag {
    #[pyo3(get, set)]
    pub tag: u64,
    #[pyo3(get, set)]
    pub value: Py<PyAny>,
}

#[pymethods]
impl PyCborTag {
    #[new]
    fn new(tag: u64, value: Py<PyAny>) -> Self { PyCborTag { tag, value } }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!("CBORTag({}, {})", self.tag, self.value.bind(py).repr()?))
    }

    fn __eq__(&self, py: Python<'_>, other: &PyCborTag) -> PyResult<bool> {
        Ok(self.tag == other.tag
            && self.value.bind(py).eq(other.value.bind(py))?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        let value_hash = self.value.bind(py).hash()?;
        Ok((self.tag as isize).wrapping_mul(1_000_003) ^ value_hash)
    }
}

const TAG_DATE: u64 = 1;

/// Convert a Python object into a `dcbor::CBOR` value.
fn py_to_cbor(py: Python<'_>, obj: &Bound<'_, PyAny>, depth: u32) -> PyResult<CBOR> {
    if depth > MAX_DEPTH {
        return Err(depth_err());
    }
    if obj.is_none() {
        return Ok(CBOR::from(CBORCase::Simple(Simple::Null)));
    }
    if let Ok(b) = obj.cast::<PyBool>() {
        return Ok(CBOR::from(b.is_true()));
    }
    if let Ok(i) = obj.extract::<i64>() {
        return Ok(CBOR::from(i));
    }
    if let Ok(i) = obj.extract::<u64>() {
        return Ok(CBOR::from(i));
    }
    if let Ok(i) = obj.extract::<i128>() {
        // Beyond i64/u64 direct range: dCBOR negatives can reach -(2^64).
        if i < 0 {
            let mag: i128 = -1 - i;
            if let Ok(mag) = u64::try_from(mag) {
                return Ok(CBOR::from(CBORCase::Negative(mag)));
            }
        }
        return Err(CBORError::new_err(
            "integer out of range for dCBOR (must fit in [-2^64, 2^64-1])",
        ));
    }
    if obj.cast::<PyInt>().is_ok() {
        // A Python int that didn't fit in i128 either: still an
        // out-of-range integer, not an unsupported type.
        return Err(CBORError::new_err(
            "integer out of range for dCBOR (must fit in [-2^64, 2^64-1])",
        ));
    }
    if let Ok(f) = obj.cast::<PyFloat>() {
        return Ok(CBOR::from(f.value()));
    }
    if let Ok(s) = obj.cast::<PyString>() {
        return Ok(CBOR::from(s.to_string()));
    }
    if let Ok(b) = obj.cast::<PyBytes>() {
        return Ok(CBOR::from(ByteString::new(b.as_bytes().to_vec())));
    }
    if let Ok(b) = obj.cast::<PyByteArray>() {
        return Ok(CBOR::from(ByteString::new(unsafe { b.as_bytes() }.to_vec())));
    }
    // datetime.datetime -> tag 1 (epoch date). Naive datetimes are
    // rejected rather than silently encoded using the host's local
    // timezone, which would make encoding non-deterministic across
    // machines -- unacceptable for a canonical format.
    {
        let datetime_mod = py.import("datetime")?;
        let datetime_cls = datetime_mod.getattr("datetime")?;
        if obj.is_instance(&datetime_cls)? {
            let tzinfo = obj.getattr("tzinfo")?;
            if tzinfo.is_none() {
                return Err(CBORError::new_err(
                    "naive datetime.datetime (no tzinfo) cannot be encoded \
                     deterministically; attach a timezone (e.g. \
                     datetime.timezone.utc) first",
                ));
            }
            let ts = obj.call_method0("timestamp")?;
            let secs: f64 = ts.extract()?;
            return Ok(CBOR::from(Date::from_timestamp(secs)));
        }
    }
    if let Ok(tag_obj) = obj.extract::<PyRef<'_, PyCborTag>>() {
        let inner = py_to_cbor(py, tag_obj.value.bind(py), depth + 1)?;
        return Ok(CBOR::from(CBORCase::Tagged(
            Tag::with_value(tag_obj.tag),
            inner,
        )));
    }
    if let Ok(list) = obj.cast::<PyList>() {
        let mut items = Vec::with_capacity(list.len());
        for item in list.iter() {
            items.push(py_to_cbor(py, &item, depth + 1)?);
        }
        return Ok(CBOR::from(items));
    }
    if let Ok(tuple) = obj.cast::<PyTuple>() {
        let mut items = Vec::with_capacity(tuple.len());
        for item in tuple.iter() {
            items.push(py_to_cbor(py, &item, depth + 1)?);
        }
        return Ok(CBOR::from(items));
    }
    if let Ok(dict) = obj.cast::<PyDict>() {
        let mut map = Map::new();
        for (k, v) in dict.iter() {
            let key_cbor = py_to_cbor(py, &k, depth + 1)?;
            let val_cbor = py_to_cbor(py, &v, depth + 1)?;
            map.insert(key_cbor, val_cbor);
        }
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
        CBORCase::Map(map) => {
            let dict = PyDict::new(py);
            for (k, v) in map.iter() {
                let key = cbor_to_py(py, k, depth + 1)?;
                let value = cbor_to_py(py, v, depth + 1)?;
                dict.set_item(&key, value).map_err(|e| {
                    if e.is_instance_of::<pyo3::exceptions::PyTypeError>(py) {
                        let type_name = key
                            .bind(py)
                            .get_type()
                            .name()
                            .map(|n| n.to_string())
                            .unwrap_or_else(|_| "?".to_string());
                        CBORError::new_err(format!(
                            "dCBOR map has a key of type '{type_name}' that \
                             has no Python-hashable equivalent (e.g. an \
                             array or map key); cannot represent as a \
                             Python dict"
                        ))
                    } else {
                        e
                    }
                })?;
            }
            dict.into_py_any(py)
        }
        CBORCase::Tagged(tag, item) => {
            if tag.value() == TAG_DATE {
                if let Ok(date) = Date::try_from(cbor.clone()) {
                    let datetime_mod = py.import("datetime")?;
                    let timezone = datetime_mod.getattr("timezone")?;
                    let utc = timezone.getattr("utc")?;
                    let datetime_cls = datetime_mod.getattr("datetime")?;
                    let dt = datetime_cls
                        .call_method1("fromtimestamp", (date.timestamp(), utc))?;
                    return dt.into_py_any(py);
                }
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
/// `float`, `str`, `bytes`/`bytearray`, `list`/`tuple`, `dict`,
/// timezone-aware `datetime.datetime` (encoded as CBOR tag 1), and
/// `dcbor.CBORTag` for arbitrary tagged values.
#[pyfunction]
fn dumps(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyBytes>> {
    let cbor = py_to_cbor(py, obj, 0)?;
    Ok(PyBytes::new(py, &cbor.to_cbor_data()).unbind())
}

/// Decode dCBOR bytes into a Python object.
///
/// Raises `dcbor.CBORError` if `data` is not valid, well-formed dCBOR
/// (including violations of dCBOR's deterministic-encoding rules), or if
/// a decoded map contains a key type with no Python-hashable equivalent.
#[pyfunction]
fn loads(py: Python<'_>, data: &[u8]) -> PyResult<Py<PyAny>> {
    check_max_depth(data)?;
    let cbor = CBOR::try_from_data(data).map_err(cbor_err)?;
    cbor_to_py(py, &cbor, 0)
}

/// Return the CBOR diagnostic-notation string for the given dCBOR bytes.
#[pyfunction(name = "diagnostic")]
fn diagnostic_str(data: &[u8]) -> PyResult<String> {
    check_max_depth(data)?;
    let cbor = CBOR::try_from_data(data).map_err(cbor_err)?;
    Ok(cbor.diagnostic())
}

/// Return a single-line CBOR diagnostic-notation string for the given
/// dCBOR bytes.
#[pyfunction(name = "diagnostic_flat")]
fn diagnostic_flat_str(data: &[u8]) -> PyResult<String> {
    check_max_depth(data)?;
    let cbor = CBOR::try_from_data(data).map_err(cbor_err)?;
    Ok(cbor.diagnostic_flat())
}

/// Validate that `data` is well-formed dCBOR without materializing a
/// Python object; returns the number of bytes consumed.
#[pyfunction]
fn validate(data: &[u8]) -> PyResult<usize> {
    check_max_depth(data)?;
    CBOR::try_from_data(data).map_err(cbor_err)?;
    Ok(data.len())
}

#[pymodule]
fn _dcbor(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__doc__", "Native PyO3 bindings for the dcbor Rust crate.")?;
    m.add("CBORError", py.get_type::<CBORError>())?;
    m.add_class::<PyCborTag>()?;
    m.add_function(wrap_pyfunction!(dumps, m)?)?;
    m.add_function(wrap_pyfunction!(loads, m)?)?;
    m.add_function(wrap_pyfunction!(diagnostic_str, m)?)?;
    m.add_function(wrap_pyfunction!(diagnostic_flat_str, m)?)?;
    m.add_function(wrap_pyfunction!(validate, m)?)?;
    Ok(())
}
