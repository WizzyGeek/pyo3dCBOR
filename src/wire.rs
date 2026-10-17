//! Iterative wire checks performed before entering the recursive upstream decoder.
use crate::{depth_err, CBORError, MAX_DEPTH};
use pyo3::prelude::*;

/// Maximum sum of encoded map-key lengths, including keys inside other keys.
/// The upstream Map retains an encoded copy of every key. Bounding this sum
/// prevents a small nested input from requesting unbounded duplicate storage.
pub(crate) const MAX_KEY_CACHE_BYTES: usize = 16 * 1024 * 1024;

struct Frame {
    remaining: u64,
    is_map: bool,
    child_start: usize,
}

fn malformed() -> PyErr {
    CBORError::new_err("invalid or truncated CBOR data")
}

fn argument(info: u8, data: &[u8], pos: &mut usize) -> PyResult<u64> {
    let width = match info {
        0..=23 => return Ok(u64::from(info)),
        24 => 1,
        25 => 2,
        26 => 4,
        27 => 8,
        _ => return Err(malformed()),
    };
    let end = pos.checked_add(width).ok_or_else(malformed)?;
    let bytes = data.get(*pos..end).ok_or_else(malformed)?;
    let mut value = 0u64;
    for byte in bytes { value = (value << 8) | u64::from(*byte); }
    *pos = end;
    Ok(value)
}

pub(crate) fn preflight(data: &[u8]) -> PyResult<()> {
    preflight_at_depth(data, 0)
}

pub(crate) fn preflight_at_depth(data: &[u8], depth: u32) -> PyResult<()> {
    preflight_key_cache_bytes(data, depth).map(|_| ())
}

/// Validate an encoded subtree and return its aggregate nested key-cache cost.
pub(crate) fn preflight_key_cache_bytes(data: &[u8], depth: u32) -> PyResult<usize> {
    if depth > MAX_DEPTH { return Err(depth_err()); }
    let mut pos = 0usize;
    let mut stack: Vec<Frame> = Vec::new();
    let mut key_cache_bytes = 0usize;
    loop {
        let byte = *data.get(pos).ok_or_else(malformed)?;
        pos += 1;
        let major = byte >> 5;
        let info = byte & 31;
        let value = argument(info, data, &mut pos)?;
        match major {
            // Numeric canonicality for major type 7 is enforced by the
            // patched decoder after this structural/resource scan succeeds.
            0 | 1 | 7 => (),
            2 | 3 => {
                let length = usize::try_from(value).map_err(|_| malformed())?;
                pos = pos.checked_add(length).filter(|end| *end <= data.len())
                    .ok_or_else(malformed)?;
            }
            4 | 5 | 6 => {
                let remaining = match major {
                    4 => value,
                    5 => value.checked_mul(2).ok_or_else(|| CBORError::new_err(
                        "map item count exceeds the maximum supported range"))?,
                    _ => 1,
                };
                if stack.len() + depth as usize >= MAX_DEPTH as usize { return Err(depth_err()); }
                if remaining != 0 {
                    stack.push(Frame { remaining, is_map: major == 5, child_start: pos });
                    continue;
                }
            }
            _ => return Err(malformed()),
        }
        loop {
            let Some(frame) = stack.last_mut() else {
                return if pos == data.len() { Ok(key_cache_bytes) } else { Err(malformed()) };
            };
            // Map frames begin with an even item count: the just-completed
            // direct child is a key exactly when that count is even.
            if frame.is_map && frame.remaining % 2 == 0 {
                key_cache_bytes = key_cache_bytes.checked_add(pos - frame.child_start)
                    .filter(|total| *total <= MAX_KEY_CACHE_BYTES)
                    .ok_or_else(|| CBORError::new_err(format!(
                        "encoded map key cache exceeds the maximum supported size ({MAX_KEY_CACHE_BYTES} bytes)")))?;
            }
            frame.remaining -= 1;
            if frame.remaining == 0 {
                stack.pop();
            } else {
                frame.child_start = pos;
                break;
            }
        }
    }
}
