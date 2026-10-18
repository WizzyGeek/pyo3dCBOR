//! Key-context decoding preserves the original identity of lossless CBOR keys.
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use std::ops::Range;

pub(crate) fn decode_key(
    py: Python<'_>,
    source: &Bound<'_, PyBytes>,
    span: Range<usize>,
    depth: u32,
) -> PyResult<Py<PyAny>> {
    crate::direct_decode::decode_range(py, source, span, depth, true)
}
