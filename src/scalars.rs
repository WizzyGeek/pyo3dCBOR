//! Checked Python scalar conversions; date handling deliberately bypasses
//! `dcbor::Date`, whose constructor panics for unsupported timestamps.
use dcbor::{CBORCase, Simple, Tag, CBOR};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString, PyTuple};
use pyo3::IntoPyObjectExt;
use unicode_normalization::UnicodeNormalization;

use crate::CBORError;

fn date_error(err: PyErr) -> PyErr {
    CBORError::new_err(format!("cannot convert CBOR epoch datetime: {err}"))
}

pub(crate) fn encode_text(text: &Bound<'_, PyString>) -> PyResult<CBOR> {
    // to_str reads Python's actual Unicode storage, including on subclasses.
    // CBOR text is UTF-8: surrogate code points have no valid representation.
    let value = text.to_str().map_err(|_| {
        CBORError::new_err("Python string contains surrogate code points that cannot be encoded as CBOR UTF-8 text")
    })?;
    // Upstream normalizes only when serializing. Store canonical text here
    // so cache-budget lengths match the actual wire bytes, even when NFC
    // expands or contracts the original UTF-8 representation.
    let normalized = if value.is_ascii() {
        value.to_owned()
    } else {
        value.nfc().collect()
    };
    Ok(CBORCase::Text(normalized).into())
}

pub(crate) fn encode_datetime(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
) -> PyResult<Option<CBOR>> {
    // Exact builtin containers cannot be datetime instances. Avoid importing
    // datetime for the common recursive-container path while preserving the
    // existing instance checks for subclasses and custom objects.
    if obj.is_exact_instance_of::<PyList>()
        || obj.is_exact_instance_of::<PyTuple>()
        || obj.is_exact_instance_of::<PyDict>()
    {
        return Ok(None);
    }
    let datetime_mod = py.import("datetime")?;
    if !obj.is_instance(&datetime_mod.getattr("datetime")?)? {
        return Ok(None);
    }
    // A tzinfo object may itself return None, making the datetime naive.
    if obj.call_method0("utcoffset").map_err(date_error)?.is_none() {
        return Err(CBORError::new_err(
            "naive datetime.datetime cannot be encoded deterministically; attach a timezone (e.g. datetime.timezone.utc) first",
        ));
    }
    let seconds: f64 = obj
        .call_method0("timestamp")
        .map_err(date_error)?
        .extract()
        .map_err(date_error)?;
    if !seconds.is_finite() {
        return Err(CBORError::new_err("datetime timestamp must be finite"));
    }
    // Direct numeric CBOR preserves negative fractions and applies dCBOR's
    // canonical integer reduction without the upstream Date constructor.
    Ok(Some(CBORCase::Tagged(Tag::with_value(1), CBOR::from(seconds)).into()))
}

pub(crate) fn decode_datetime(
    py: Python<'_>,
    cbor: &CBOR,
) -> PyResult<Option<Py<PyAny>>> {
    let CBORCase::Tagged(tag, value) = cbor.as_case() else {
        return Ok(None);
    };
    if tag.value() != 1 {
        return Ok(None);
    }
    let timestamp = match value.as_case() {
        CBORCase::Unsigned(n) => n.into_py_any(py)?,
        CBORCase::Negative(n) => (-1i128 - (*n as i128)).into_py_any(py)?,
        CBORCase::Simple(Simple::Float(n)) => {
            if !n.is_finite() {
                return Err(CBORError::new_err("CBOR epoch timestamp must be finite"));
            }
            n.into_py_any(py)?
        }
        // Preserve arbitrary nonnumeric tag 1 values as CBORTag objects.
        _ => return Ok(None),
    };
    let datetime_mod = py.import("datetime")?;
    let utc = datetime_mod.getattr("timezone")?.getattr("utc")?;
    let result = datetime_mod
        .getattr("datetime")?
        .call_method1("fromtimestamp", (timestamp, utc))
        .map_err(date_error)?;
    Ok(Some(result.unbind()))
}
