//! Python representations which cannot be expressed losslessly by builtin dicts.
use dcbor::{CBOR, Map};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use pyo3::{IntoPyObjectExt, PyTraverseError, PyVisit};
use crate::{cbor_to_py, py_to_cbor, CBORError};
use crate::key_conversion::cbor_key_to_py;

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
        // Keeping a simple nonrecursive summary avoids invoking arbitrary recursive
        // Python formatting while retaining a useful value for ordinary scalars.
        let value = self.value.bind(py);
        if value.is_instance_of::<pyo3::types::PyString>()
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
        // Rust rich comparisons recurse outside the interpreter's usual guard.
        // Use CPython's recursion accounting before comparing referenced values.
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

/// Immutable encoded snapshot; decoded keys and values are fresh Python objects.
#[pyclass(module = "dcbor", name = "CBORMap", frozen, skip_from_py_object)]
pub struct PyCborMap {
    pub map: Map,
}

#[pymethods]
impl PyCborMap {
    #[new]
    fn new(py: Python<'_>, pairs: &Bound<'_, PyAny>) -> PyResult<Self> {
        let mut map = Map::new();
        let mut seen = std::collections::HashSet::new();
        let mut budget = crate::encode::EncodeBudget::default();
        for pair in pairs.try_iter()? {
            let pair = pair?;
            // A third item already proves this is not a pair. Never exhaust
            // arbitrary iterators: they may be infinite or allocate without bound.
            let pair = PyTuple::new(py, pair.try_iter()?.take(3).collect::<PyResult<Vec<_>>>()?)?;
            if pair.len() != 2 {
                return Err(pyo3::exceptions::PyValueError::new_err("CBORMap entries must be key/value pairs"));
            }
            let key = crate::py_to_cbor_key_with_budget(py, &pair.get_item(0)?, 1, &mut budget)?;
            let encoded = key.to_cbor_data();
            if !seen.insert(encoded) {
                return Err(CBORError::new_err("duplicate canonical CBOR map key"));
            }
            let value = crate::py_to_cbor_with_budget(py, &pair.get_item(1)?, 1, &mut budget)?;
            map.insert(key, value);
        }
        let snapshot = Self { map };
        Ok(snapshot)
    }

    fn __len__(&self) -> usize { self.map.len() }

    fn __getitem__(&self, py: Python<'_>, key: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let canonical_key = py_to_cbor(py, key, 1)?;
        match self.map.get::<CBOR, CBOR>(canonical_key) {
            Some(value) => cbor_to_py(py, &value, 1),
            None => Err(pyo3::exceptions::PyKeyError::new_err(key.clone().unbind())),
        }
    }

    fn __contains__(&self, py: Python<'_>, key: &Bound<'_, PyAny>) -> PyResult<bool> {
        let canonical_key = py_to_cbor(py, key, 1)?;
        Ok(self.map.contains_key(canonical_key))
    }

    #[pyo3(signature = (key, default=None))]
    fn get(&self, py: Python<'_>, key: &Bound<'_, PyAny>, default: Option<Py<PyAny>>) -> PyResult<Py<PyAny>> {
        match self.__getitem__(py, key) {
            Err(e) if e.is_instance_of::<pyo3::exceptions::PyKeyError>(py) => Ok(default.unwrap_or_else(|| py.None())),
            result => result,
        }
    }

    fn keys(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let result = PyList::empty(py);
        for (k, _) in self.map.iter() { result.append(cbor_key_to_py(py, k, 1)?)?; }
        result.into_py_any(py)
    }

    fn values(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let result = PyList::empty(py);
        for (_, v) in self.map.iter() { result.append(cbor_to_py(py, v, 1)?)?; }
        result.into_py_any(py)
    }

    fn items(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let result = PyList::empty(py);
        for (k, v) in self.map.iter() {
            result.append((cbor_key_to_py(py, k, 1)?, cbor_to_py(py, v, 1)?))?;
        }
        result.into_py_any(py)
    }

    fn __iter__(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.keys(py)?.bind(py).call_method0("__iter__")?.into_py_any(py)
    }

    fn __repr__(&self) -> String { format!("CBORMap({})", CBOR::from(self.map.clone()).diagnostic_flat()) }

    fn __eq__(&self, other: &Self) -> bool {
        CBOR::from(self.map.clone()).to_cbor_data() == CBOR::from(other.map.clone()).to_cbor_data()
    }

    #[classattr]
    const __hash__: Option<Py<PyAny>> = None;
}

impl PyCborMap {
    pub(crate) fn to_cbor_with_budget(
        &self, depth: u32, budget: &mut crate::encode::EncodeBudget,
    ) -> PyResult<CBOR> {
        budget.reserve_snapshot(&self.map, depth)?;
        Ok(CBOR::from(self.map.clone()))
    }

}

pub fn map_to_python(py: Python<'_>, map: &Map, depth: u32) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    let mut fallback = false;
    for (k, v) in map.iter() {
        // Validate every conversion even when an earlier key requires fallback.
        let key = cbor_key_to_py(py, k, depth + 1)?;
        let value = cbor_to_py(py, v, depth + 1)?;
        if fallback { continue; }
        let key = key.bind(py);
        if let Err(error) = key.hash() {
            if error.is_instance_of::<pyo3::exceptions::PyTypeError>(py) {
                fallback = true;
                continue;
            }
            return Err(error);
        }
        if dict.contains(key)? {
            fallback = true;
        } else {
            dict.set_item(key, value)?;
        }
    }
    if fallback {
        PyCborMap { map: map.clone() }.into_py_any(py)
    } else {
        dict.into_py_any(py)
    }
}
