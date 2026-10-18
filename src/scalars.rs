//! Checked Python scalar conversions for timezone-aware epoch datetimes.
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyFloat, PyInt, PyList, PyTuple};

use crate::CBORError;

fn date_error(err: PyErr) -> PyErr {
    CBORError::new_err(format!("cannot convert CBOR epoch datetime: {err}"))
}

pub(crate) fn datetime_timestamp(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
) -> PyResult<Option<f64>> {
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
    Ok(Some(seconds))
}

/// Convert a native Python integer or float timestamp into a UTC datetime.
///
/// Keeping the timestamp as a Python scalar lets `datetime.timedelta` apply
/// its normal range and microsecond-rounding behavior without first building
/// a vendor CBOR value or coercing large integers through an `f64`.
pub(crate) fn decode_datetime_timestamp(
    py: Python<'_>,
    timestamp: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    if let Ok(value) = timestamp.cast::<PyFloat>() {
        if !value.value().is_finite() {
            return Err(CBORError::new_err("CBOR epoch timestamp must be finite"));
        }
    } else if timestamp.cast::<PyInt>().is_err() {
        return Err(CBORError::new_err("CBOR epoch timestamp must be numeric"));
    }

    let datetime_mod = py.import("datetime")?;
    let utc = datetime_mod.getattr("timezone")?.getattr("utc")?;
    let datetime = datetime_mod.getattr("datetime")?;
    let epoch_kwargs = PyDict::new(py);
    epoch_kwargs.set_item("tzinfo", &utc)?;
    let epoch = datetime
        .call((1970, 1, 1), Some(&epoch_kwargs))
        .map_err(date_error)?;
    let delta_kwargs = PyDict::new(py);
    delta_kwargs.set_item("seconds", timestamp)?;
    let delta = datetime_mod
        .getattr("timedelta")?
        .call((), Some(&delta_kwargs))
        .map_err(date_error)?;
    epoch
        .call_method1("__add__", (delta,))
        .map(|value| value.unbind())
        .map_err(date_error)
}
