//! Borrowed CBOR wire parsing and an iterative canonicality/resource scan.
//!
//! The scanner validates the complete input before Python objects are built.
//! It keeps only a depth-bounded frame stack and compares map-key slices in the
//! original immutable input, so canonical key checking does not copy key bytes.

use crate::{depth_err, direct_wire::FloatEncoding, CBORError, MAX_DEPTH};
use half::f16;
use pyo3::prelude::*;
use std::cmp::Ordering;
use std::ops::Range;
use unicode_normalization::is_nfc;

/// Maximum aggregate size of encoded map keys, including nested map keys.
pub(crate) const MAX_KEY_CACHE_BYTES: usize = 16 * 1024 * 1024;

/// Parsed CBOR head. `argument` carries unsigned values, lengths, tags, or
/// the raw bit pattern for major-type-7 floats, according to `major` and AI.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct Header {
    pub(crate) major: u8,
    pub(crate) additional_info: u8,
    pub(crate) argument: u64,
    pub(crate) start: usize,
    pub(crate) head_end: usize,
}

/// A small borrowed cursor over an immutable CBOR byte range.
#[derive(Clone, Copy, Debug)]
pub(crate) struct Cursor<'a> {
    data: &'a [u8],
    position: usize,
    end: usize,
}

impl<'a> Cursor<'a> {
    pub(crate) fn new(data: &'a [u8]) -> Self {
        Self {
            data,
            position: 0,
            end: data.len(),
        }
    }

    pub(crate) fn with_range(data: &'a [u8], range: Range<usize>) -> PyResult<Self> {
        if range.start > range.end || range.end > data.len() {
            return Err(invalid_data());
        }
        Ok(Self {
            data,
            position: range.start,
            end: range.end,
        })
    }

    pub(crate) fn position(&self) -> usize {
        self.position
    }

    pub(crate) fn read_header(&mut self) -> PyResult<Header> {
        let start = self.position;
        let initial = *self.data.get(self.position).filter(|_| self.position < self.end)
            .ok_or_else(invalid_data)?;
        self.position += 1;
        let major = initial >> 5;
        let additional_info = initial & 0x1f;
        let argument = match additional_info {
            value @ 0..=23 => u64::from(value),
            24 => u64::from(self.read_u8()?),
            25 => u64::from(self.read_u16()?),
            26 => u64::from(self.read_u32()?),
            27 => self.read_u64()?,
            _ => return Err(invalid_data()),
        };
        Ok(Header {
            major,
            additional_info,
            argument,
            start,
            head_end: self.position,
        })
    }

    pub(crate) fn read_payload(&mut self, length: u64) -> PyResult<&'a [u8]> {
        let length = usize::try_from(length).map_err(|_| invalid_data())?;
        let end = self.position.checked_add(length)
            .filter(|end| *end <= self.end)
            .ok_or_else(invalid_data)?;
        let payload = &self.data[self.position..end];
        self.position = end;
        Ok(payload)
    }

    pub(crate) fn span(&self, start: usize, end: usize) -> PyResult<&'a [u8]> {
        if start > end || end > self.end {
            return Err(invalid_data());
        }
        self.data.get(start..end).ok_or_else(invalid_data)
    }

    pub(crate) fn finish(&self) -> PyResult<()> {
        if self.position == self.end {
            Ok(())
        } else {
            Err(invalid_data())
        }
    }

    fn read_u8(&mut self) -> PyResult<u8> {
        let byte = *self.data.get(self.position).filter(|_| self.position < self.end)
            .ok_or_else(invalid_data)?;
        self.position += 1;
        Ok(byte)
    }

    fn read_u16(&mut self) -> PyResult<u16> {
        let bytes = self.read_payload(2)?;
        Ok(u16::from_be_bytes([bytes[0], bytes[1]]))
    }

    fn read_u32(&mut self) -> PyResult<u32> {
        let bytes = self.read_payload(4)?;
        Ok(u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
    }

    fn read_u64(&mut self) -> PyResult<u64> {
        let bytes = self.read_payload(8)?;
        Ok(u64::from_be_bytes([
            bytes[0], bytes[1], bytes[2], bytes[3],
            bytes[4], bytes[5], bytes[6], bytes[7],
        ]))
    }
}

/// A lazy view of the encoded entries in a preflight-validated map.
///
/// It yields key/value byte ranges in input order, retaining neither decoded
/// objects nor an entry-range vector. `next_entry` uses a reusable stack to
/// skip nested values iteratively.
pub(crate) struct MapCursor<'a> {
    cursor: Cursor<'a>,
    length: u64,
    remaining: u64,
    skip_stack: Vec<u64>,
    finished: bool,
}

impl<'a> MapCursor<'a> {
    pub(crate) fn new(data: &'a [u8], range: Range<usize>) -> PyResult<Self> {
        let mut cursor = Cursor::with_range(data, range)?;
        let header = cursor.read_header()?;
        if header.major != 5 {
            return Err(invalid_data());
        }
        Ok(Self {
            cursor,
            length: header.argument,
            remaining: header.argument,
            skip_stack: Vec::new(),
            finished: false,
        })
    }

    pub(crate) fn len(&self) -> u64 {
        self.length
    }

    pub(crate) fn next_entry(
        &mut self,
    ) -> PyResult<Option<(Range<usize>, Range<usize>)>> {
        if self.remaining == 0 {
            if !self.finished {
                self.cursor.finish()?;
                self.finished = true;
            }
            return Ok(None);
        }

        let key_start = self.cursor.position();
        self.skip_item()?;
        let key_end = self.cursor.position();
        let value_start = key_end;
        self.skip_item()?;
        let value_end = self.cursor.position();
        self.remaining -= 1;
        Ok(Some((key_start..key_end, value_start..value_end)))
    }

    fn skip_item(&mut self) -> PyResult<()> {
        self.skip_stack.clear();
        self.skip_stack.push(1);
        while let Some(remaining) = self.skip_stack.last().copied() {
            if remaining == 0 {
                self.skip_stack.pop();
                continue;
            }
            if let Some(last) = self.skip_stack.last_mut() {
                *last -= 1;
            }

            let header = self.cursor.read_header()?;
            let children = match header.major {
                2 | 3 => {
                    self.cursor.read_payload(header.argument)?;
                    0
                }
                4 => header.argument,
                5 => header.argument.checked_mul(2).ok_or_else(|| {
                    CBORError::new_err("map item count exceeds the maximum supported range")
                })?,
                6 => 1,
                _ => 0,
            };
            if children != 0 {
                self.skip_stack.push(children);
            }
        }
        Ok(())
    }
}

struct Frame {
    remaining: u64,
    is_map: bool,
    child_start: usize,
    previous_key: Option<Range<usize>>,
}

/// Error constructor shared by the scanner, decoder, and diagnostic formatter.
pub(crate) fn invalid_data() -> PyErr {
    CBORError::new_err("invalid or truncated CBOR data")
}

/// Compatibility name used by snapshot construction and decoding helpers.
pub(crate) fn malformed_error() -> PyErr {
    invalid_data()
}

fn noncanonical_numeric() -> PyErr {
    CBORError::new_err("a CBOR numeric value was encoded in non-canonical form")
}

fn invalid_simple() -> PyErr {
    CBORError::new_err("an invalid CBOR simple value was encountered")
}

fn check_argument_minimality(header: Header) -> PyResult<()> {
    let nonminimal = match header.additional_info {
        24 => header.argument < 24,
        25 if header.major != 7 => header.argument <= u8::MAX as u64,
        26 if header.major != 7 => header.argument <= u16::MAX as u64,
        27 if header.major != 7 => header.argument <= u32::MAX as u64,
        _ => false,
    };
    if nonminimal {
        Err(noncanonical_numeric())
    } else {
        Ok(())
    }
}

fn check_float(header: Header) -> PyResult<()> {
    let valid = match header.additional_info {
        25 => {
            let bits = header.argument as u16;
            FloatEncoding::from_f64(f16::from_bits(bits).to_f64())
                == FloatEncoding::Half(bits)
        }
        26 => {
            let bits = header.argument as u32;
            FloatEncoding::from_f64(f32::from_bits(bits) as f64)
                == FloatEncoding::Single(bits)
        }
        27 => {
            let bits = header.argument;
            FloatEncoding::from_f64(f64::from_bits(bits))
                == FloatEncoding::Double(bits)
        }
        _ => false,
    };
    if valid {
        Ok(())
    } else {
        Err(noncanonical_numeric())
    }
}

fn check_simple_or_float(header: Header) -> PyResult<()> {
    match header.additional_info {
        20..=22 => Ok(()),
        25..=27 => check_float(header),
        24 => {
            check_argument_minimality(header)?;
            Err(invalid_simple())
        }
        _ => Err(invalid_simple()),
    }
}

fn check_supported_simple(header: Header) -> PyResult<()> {
    match header.additional_info {
        20..=22 | 25..=27 => Ok(()),
        _ => Err(invalid_simple()),
    }
}

/// Validate one complete dCBOR item before decoding or formatting it.
pub(crate) fn preflight(data: &[u8]) -> PyResult<()> {
    preflight_at_depth(data, 0)
}

pub(crate) fn preflight_at_depth(data: &[u8], depth: u32) -> PyResult<()> {
    preflight_key_cache_bytes(data, depth).map(|_| ())
}

/// Validate a complete item and return the aggregate encoded map-key cost.
///
/// Canonical map keys are compared as borrowed slices into `data`; no raw key
/// bytes are retained or copied by the scanner.
pub(crate) fn preflight_key_cache_bytes(data: &[u8], depth: u32) -> PyResult<usize> {
    preflight_with_mode(data, depth, true)
}

/// Check structure and resource bounds for bytes written by the trusted
/// direct encoder. Its writer already guarantees canonical ordering, numeric
/// widths, UTF-8, and NFC, so those repeated checks are unnecessary here.
pub(crate) fn preflight_trusted_output(data: &[u8]) -> PyResult<()> {
    preflight_with_mode(data, 0, false).map(|_| ())
}

fn preflight_with_mode(
    data: &[u8],
    depth: u32,
    canonical: bool,
) -> PyResult<usize> {
    if depth > MAX_DEPTH {
        return Err(depth_err());
    }

    let mut cursor = Cursor::new(data);
    let mut stack: Vec<Frame> = Vec::new();
    let mut key_cache_bytes = 0usize;

    loop {
        let header = cursor.read_header()?;
        if canonical {
            check_argument_minimality(header)?;
        }

        match header.major {
            0 | 1 => (),
            2 => {
                cursor.read_payload(header.argument)?;
            }
            3 => {
                let payload = cursor.read_payload(header.argument)?;
                if canonical {
                    let text = std::str::from_utf8(payload).map_err(|error| {
                        CBORError::new_err(format!("invalid UTF‑8 string: {error}"))
                    })?;
                    if !is_nfc(text) {
                        return Err(CBORError::new_err(
                            "a CBOR string was not encoded in Unicode Canonical Normalization Form C",
                        ));
                    }
                }
            }
            4 | 5 | 6 => {
                let remaining = match header.major {
                    4 => header.argument,
                    5 => header.argument.checked_mul(2).ok_or_else(|| {
                        CBORError::new_err(
                            "map item count exceeds the maximum supported range",
                        )
                    })?,
                    _ => 1,
                };
                if stack.len().saturating_add(depth as usize) >= MAX_DEPTH as usize {
                    return Err(depth_err());
                }
                if remaining != 0 {
                    stack.push(Frame {
                        remaining,
                        is_map: header.major == 5,
                        child_start: cursor.position(),
                        previous_key: None,
                    });
                    continue;
                }
            }
            7 => {
                if canonical {
                    check_simple_or_float(header)?;
                } else {
                    check_supported_simple(header)?;
                }
            }
            _ => return Err(invalid_data()),
        }

        loop {
            let Some(frame) = stack.last_mut() else {
                cursor.finish()?;
                return Ok(key_cache_bytes);
            };

            if frame.is_map && frame.remaining % 2 == 0 {
                let current = frame.child_start..cursor.position();
                if canonical {
                    if let Some(previous) = &frame.previous_key {
                        match data[previous.clone()].cmp(&data[current.clone()]) {
                            Ordering::Equal => {
                                return Err(CBORError::new_err(
                                    "the decoded CBOR map has a duplicate key",
                                ));
                            }
                            Ordering::Greater => {
                                return Err(CBORError::new_err(
                                    "the decoded CBOR map has keys that are not in canonical order",
                                ));
                            }
                            Ordering::Less => (),
                        }
                    }
                    frame.previous_key = Some(current.clone());
                }
                let key_length = current.end - current.start;
                key_cache_bytes = key_cache_bytes
                    .checked_add(key_length)
                    .filter(|total| *total <= MAX_KEY_CACHE_BYTES)
                    .ok_or_else(|| {
                        CBORError::new_err(format!(
                            "encoded map key cache exceeds the maximum supported size ({MAX_KEY_CACHE_BYTES} bytes)"
                        ))
                    })?;
            }

            frame.remaining -= 1;
            if frame.remaining == 0 {
                stack.pop();
            } else {
                frame.child_start = cursor.position();
                break;
            }
        }
    }
}
