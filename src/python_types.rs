//! Python representations which cannot be expressed losslessly by builtin dicts.
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyList, PyString};
use pyo3::{IntoPyObjectExt, PyTraverseError, PyVisit};
use std::ops::Range;

use crate::{CBORError, MAX_DEPTH};

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
    fn new(tag: u64, value: Py<PyAny>) -> Self { Self { tag, value } }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let value = self.value.bind(py);
        if value.is_instance_of::<PyString>()
            || value.is_instance_of::<pyo3::types::PyInt>()
            || value.is_none()
        {
            Ok(format!("CBORTag({}, {})", self.tag, value.repr()?))
        } else {
            Ok(format!("CBORTag({}, <{}>)", self.tag, value.get_type().name()?))
        }
    }

    fn __eq__(&self, py: Python<'_>, other: &Self) -> PyResult<bool> {
        if std::ptr::eq(self, other) { return Ok(true); }
        unsafe {
            if pyo3::ffi::Py_EnterRecursiveCall(c" in CBORTag comparison".as_ptr()) != 0 {
                return Err(PyErr::fetch(py));
            }
        }
        let result = (|| Ok(self.tag == other.tag && self.value.bind(py).eq(other.value.bind(py))?))();
        unsafe { pyo3::ffi::Py_LeaveRecursiveCall(); }
        result
    }

    #[classattr]
    const __hash__: Option<Py<PyAny>> = None;

    fn __traverse__(&self, visit: PyVisit<'_>) -> Result<(), PyTraverseError> {
        visit.call(&self.value)
    }

    fn __clear__(&mut self, py: Python<'_>) { self.value = py.None(); }
}

/// Immutable encoded snapshot. It retains one bytes owner and a map span;
/// keys and values are decoded afresh by the accessors.
#[pyclass(module = "dcbor", name = "CBORMap", frozen, skip_from_py_object)]
pub struct PyCborMap {
    owner: Py<PyBytes>,
    start: usize,
    end: usize,
    len: usize,
    nested_key_cache_bytes: usize,
}

#[pymethods]
impl PyCborMap {
    #[new]
    fn new(py: Python<'_>, pairs: &Bound<'_, PyAny>) -> PyResult<Self> {
        use crate::direct_wire;
        let mut budget = crate::encode::EncodeBudget::default();
        let mut entries = std::collections::BTreeMap::<Vec<u8>, Vec<u8>>::new();

        for pair in pairs.try_iter()? {
            let pair = pair?;
            // Read at most three items: arbitrary and potentially infinite
            // iterators must not be exhausted just to validate a pair.
            let pair = pair.try_iter()?.take(3).collect::<PyResult<Vec<_>>>()?;
            if pair.len() != 2 {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "CBORMap entries must be key/value pairs",
                ));
            }

            let before_key = budget.used();
            let mut key_budget = budget.fork_key();
            let mut key_wire = Vec::new();
            crate::direct_encode::encode_into(
                py, &pair[0], 1, &mut key_wire, &mut key_budget,
            )?;
            let key_cost = key_budget.used() - before_key;
            budget.reserve(key_cost)?;
            if entries.contains_key(&key_wire) {
                return Err(CBORError::new_err("duplicate canonical CBOR map key"));
            }

            let mut value_wire = Vec::new();
            crate::direct_encode::encode_into(
                py, &pair[1], 1, &mut value_wire, &mut budget,
            )?;
            entries.insert(key_wire, value_wire);
        }

        let mut encoded = Vec::new();
        direct_wire::write_header(5, entries.len() as u64, &mut encoded);
        for (key, value) in entries {
            encoded.extend_from_slice(&key);
            encoded.extend_from_slice(&value);
        }
        let nested_key_cache_bytes = crate::wire::preflight_key_cache_bytes(&encoded, 0)?;
        debug_assert_eq!(nested_key_cache_bytes, budget.used());
        Self::from_owned_wire(py, encoded, nested_key_cache_bytes)
    }

    fn __len__(&self) -> usize { self.len }

    fn __getitem__(&self, py: Python<'_>, key: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let encoded_key = encode_lookup_key(py, key)?;
        let owner = self.owner.bind(py);
        let data = owner.as_bytes();
        let mut cursor = crate::wire::MapCursor::new(data, self.start..self.end)?;
        while let Some((key_span, value_span)) = cursor.next_entry()? {
            if data.get(key_span) == Some(encoded_key.as_slice()) {
                return crate::direct_decode::decode_range(
                    py, owner, value_span, 1, false,
                );
            }
        }
        Err(pyo3::exceptions::PyKeyError::new_err(key.clone().unbind()))
    }

    fn __contains__(&self, py: Python<'_>, key: &Bound<'_, PyAny>) -> PyResult<bool> {
        let encoded_key = encode_lookup_key(py, key)?;
        let owner = self.owner.bind(py);
        let data = owner.as_bytes();
        let mut cursor = crate::wire::MapCursor::new(data, self.start..self.end)?;
        while let Some((key_span, _)) = cursor.next_entry()? {
            if data.get(key_span) == Some(encoded_key.as_slice()) {
                return Ok(true);
            }
        }
        Ok(false)
    }

    #[pyo3(signature = (key, default=None))]
    fn get(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        default: Option<Py<PyAny>>,
    ) -> PyResult<Py<PyAny>> {
        match self.__getitem__(py, key) {
            Err(error) if error.is_instance_of::<pyo3::exceptions::PyKeyError>(py) => {
                Ok(default.unwrap_or_else(|| py.None()))
            }
            result => result,
        }
    }

    fn keys(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let owner = self.owner.bind(py);
        let data = owner.as_bytes();
        let mut cursor = crate::wire::MapCursor::new(data, self.start..self.end)?;
        let result = PyList::empty(py);
        while let Some((key, _)) = cursor.next_entry()? {
            result.append(crate::key_conversion::decode_key(py, owner, key, 1)?)?;
        }
        result.into_py_any(py)
    }

    fn values(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let owner = self.owner.bind(py);
        let data = owner.as_bytes();
        let mut cursor = crate::wire::MapCursor::new(data, self.start..self.end)?;
        let result = PyList::empty(py);
        while let Some((_, value)) = cursor.next_entry()? {
            result.append(crate::direct_decode::decode_range(py, owner, value, 1, false)?)?;
        }
        result.into_py_any(py)
    }

    fn items(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let owner = self.owner.bind(py);
        let data = owner.as_bytes();
        let mut cursor = crate::wire::MapCursor::new(data, self.start..self.end)?;
        let result = PyList::empty(py);
        while let Some((key, value)) = cursor.next_entry()? {
            let key = crate::key_conversion::decode_key(py, owner, key, 1)?;
            let value = crate::direct_decode::decode_range(py, owner, value, 1, false)?;
            result.append((key, value))?;
        }
        result.into_py_any(py)
    }

    fn __iter__(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.keys(py)?.bind(py).call_method0("__iter__")?.into_py_any(py)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let notation = crate::diagnostic::format(self.encoded_span(py), true)?;
        Ok(format!("CBORMap({notation})"))
    }

    fn __eq__(&self, py: Python<'_>, other: &Self) -> bool {
        self.encoded_span(py) == other.encoded_span(py)
    }

    #[classattr]
    const __hash__: Option<Py<PyAny>> = None;
}

impl PyCborMap {
    pub(crate) fn from_encoded(
        owner: &Bound<'_, PyBytes>,
        span: Range<usize>,
        depth: u32,
    ) -> PyResult<Self> {
        let data = owner.as_bytes();
        let encoded = data.get(span.clone()).ok_or_else(crate::wire::malformed_error)?;
        let nested_key_cache_bytes = crate::wire::preflight_key_cache_bytes(encoded, depth)?;
        let cursor = crate::wire::MapCursor::new(data, span.clone())?;
        let len = usize::try_from(cursor.len()).map_err(|_| crate::wire::malformed_error())?;
        Ok(Self {
            owner: owner.clone().unbind(),
            start: span.start,
            end: span.end,
            len,
            nested_key_cache_bytes,
        })
    }

    fn from_owned_wire(
        py: Python<'_>,
        encoded: Vec<u8>,
        nested_key_cache_bytes: usize,
    ) -> PyResult<Self> {
        let owner = PyBytes::new(py, &encoded);
        let data = owner.as_bytes();
        let cursor = crate::wire::MapCursor::new(data, 0..data.len())?;
        let len = usize::try_from(cursor.len()).map_err(|_| crate::wire::malformed_error())?;
        Ok(Self {
            owner: owner.unbind(),
            start: 0,
            end: encoded.len(),
            len,
            nested_key_cache_bytes,
        })
    }

    pub(crate) fn append_encoded(
        &self,
        py: Python<'_>,
        depth: u32,
        out: &mut Vec<u8>,
        budget: &mut crate::encode::EncodeBudget,
    ) -> PyResult<()> {
        if depth >= MAX_DEPTH { return Err(crate::depth_err()); }
        let encoded = self.encoded_span(py);
        // Recheck at the current insertion depth before charging or appending.
        let nested_keys = crate::wire::preflight_key_cache_bytes(encoded, depth)?;
        debug_assert_eq!(nested_keys, self.nested_key_cache_bytes);
        budget.reserve_snapshot(encoded.len(), nested_keys)?;
        out.extend_from_slice(encoded);
        Ok(())
    }

    fn encoded_span<'py>(&'py self, py: Python<'py>) -> &'py [u8] {
        &self.owner.bind(py).as_bytes()[self.start..self.end]
    }
}

pub(crate) fn map_from_encoded(
    py: Python<'_>,
    owner: &Bound<'_, PyBytes>,
    span: Range<usize>,
    depth: u32,
) -> PyResult<Py<PyAny>> {
    PyCborMap::from_encoded(owner, span, depth)?.into_py_any(py)
}

fn encode_lookup_key(py: Python<'_>, key: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    let budget = crate::encode::EncodeBudget::default();
    let mut key_budget = budget.fork_key();
    let mut encoded = Vec::new();
    crate::direct_encode::encode_into(py, key, 1, &mut encoded, &mut key_budget)?;
    Ok(encoded)
}
