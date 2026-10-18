//! Conversion-scoped accounting for canonical map-key storage.
use crate::CBORError;
use pyo3::prelude::*;

pub(crate) struct EncodeBudget {
    key_bytes: usize,
    /// Each byte in the current subtree is retained in every enclosing key.
    active_keys: usize,
}

impl Default for EncodeBudget {
    fn default() -> Self {
        Self { key_bytes: 0, active_keys: 0 }
    }
}

pub(crate) fn budget_error() -> PyErr {
    CBORError::new_err("encoded map key cache exceeds the maximum supported size")
}

impl EncodeBudget {
    pub(crate) fn used(&self) -> usize { self.key_bytes }

    pub(crate) fn fork_key(&self) -> Self {
        Self { key_bytes: self.key_bytes, active_keys: self.active_keys + 1 }
    }

    pub(crate) fn release(&mut self, amount: usize) {
        self.key_bytes -= amount;
    }

    pub(crate) fn reserve(&mut self, amount: usize) -> PyResult<()> {
        self.key_bytes = self.key_bytes.checked_add(amount)
            .filter(|total| *total <= crate::wire::MAX_KEY_CACHE_BYTES)
            .ok_or_else(budget_error)?;
        Ok(())
    }

    pub(crate) fn wire_bytes(&mut self, bytes: usize) -> PyResult<()> {
        self.reserve(bytes.checked_mul(self.active_keys).ok_or_else(budget_error)?)
    }

    pub(crate) fn header(&mut self, value: u64) -> PyResult<()> {
        self.wire_bytes(crate::direct_wire::header_len(value))
    }

    pub(crate) fn bytes(&mut self, length: usize) -> PyResult<()> {
        let head = crate::direct_wire::header_len(length as u64);
        self.wire_bytes(head.checked_add(length).ok_or_else(budget_error)?)
    }

    /// Charge a mutable bytearray payload without constructing a Python error.
    /// The caller performs this under the same object guard as the borrowed
    /// slice acquisition and immediate native copy.
    pub(crate) fn try_payload_bytes(&mut self, length: usize) -> bool {
        let Some(wire_length) = crate::direct_wire::header_len(length as u64).checked_add(length) else {
            return false;
        };
        let Some(amount) = wire_length.checked_mul(self.active_keys) else {
            return false;
        };
        let Some(total) = self.key_bytes.checked_add(amount)
            .filter(|total| *total <= crate::wire::MAX_KEY_CACHE_BYTES)
        else {
            return false;
        };
        self.key_bytes = total;
        true
    }

    /// Account for an immutable encoded snapshot before appending its bytes.
    /// `nested_key_bytes` represents key storage within the snapshot itself;
    /// `wire_bytes` additionally charges its full encoding in each enclosing
    /// key context.
    pub(crate) fn reserve_snapshot(
        &mut self,
        encoded_len: usize,
        nested_key_bytes: usize,
    ) -> PyResult<()> {
        self.wire_bytes(encoded_len)?;
        self.reserve(nested_key_bytes)
    }
}
