import_stdlib!();

use half::f16;

use super::varint::{EncodeVarInt, MajorType};
use crate::{CBOR, CBORCase, Error, ExactFrom, Result, Simple};

/// # Floating Point Number Support in dCBOR
///
/// dCBOR provides canonical encoding for floating point values through
/// implementation of the `From<T>` and `TryFrom<CBOR>` traits for `f16`, `f32`,
/// and `f64` types.
///
/// Per the dCBOR specification, the canonical encoding rules ensure
/// deterministic representation:
///
/// - Numeric reduction: Floating point values with zero fractional part in
///   range [-2^63, 2^64-1] are automatically encoded as integers (e.g., 42.0
///   becomes 42)
/// - Values are encoded in the smallest possible representation that preserves
///   their value
/// - All NaN values are canonicalized to a single representation: 0xf97e00
/// - Positive/negative infinity are canonicalized to half-precision
///   representations
///
/// ## Example
///
/// ```
/// use dcbor::prelude::*;
///
/// // Create CBOR from floating point values using `into()`
/// let cbor_integer: CBOR = 42.0.into();  // Numeric reduction: encoded as integer 42
/// let cbor_float: CBOR = 3.14159.into();  // Encoded as floating point
/// let cbor_nan: CBOR = f64::NAN.into();  // Canonicalized to 0xf97e00
///
/// // Convert back to floating point
/// let value_integer: f64 = cbor_integer.try_into().unwrap();
/// assert_eq!(value_integer, 42.0);
///
/// // Maps can use numeric keys with automatic reduction
/// let mut map = Map::new();
/// map.insert(1.0, "integer key");    // 1.0 becomes 1
/// map.insert(2, "another key");      // Integer directly
///
/// // Verify numeric reduction in maps
/// let key_value: String = map.extract::<i32, String>(1).unwrap();
/// assert_eq!(key_value, "integer key");
/// ```
static CBOR_NAN: [u8; 3] = [0xf9, 0x7e, 0x00];

/// Draft-18 numeric reduction is restricted to [-2^63, 2^64).
/// Compute negative CBOR magnitudes in integer arithmetic, since subtracting
/// one from a large f32/f64 first can round away the subtraction.
fn reduced_integer(n: f64) -> Option<CBOR> {
    if n < -9_223_372_036_854_775_808.0 || n >= 18_446_744_073_709_551_616.0 {
        return None;
    }
    let integer = i128::exact_from_f64(n)?;
    if integer < 0 {
        Some(CBORCase::Negative((-1 - integer) as u64).into())
    } else {
        Some((integer as u64).into())
    }
}

/// Convert a CBOR major-type-1 argument to its signed integer value before
/// checking whether a floating-point type can represent it exactly.
///
/// Checking the encoded argument first is incorrect: the represented value is
/// `-1 - argument`, and those adjacent integers can have different exactness at
/// a floating-point precision boundary.
fn negative_integer(n: u64) -> i128 {
    -1 - i128::from(n)
}

fn exact_f64_from_negative(n: u64) -> Option<f64> {
    let integer = negative_integer(n);
    let value = integer as f64;
    (value as i128 == integer).then_some(value)
}

fn exact_f32_from_negative(n: u64) -> Option<f32> {
    let integer = negative_integer(n);
    let value = integer as f32;
    (value as i128 == integer).then_some(value)
}

impl From<f64> for CBOR {
    fn from(value: f64) -> Self {
        reduced_integer(value)
            .unwrap_or_else(|| CBORCase::Simple(Simple::Float(value)).into())
    }
}

pub(crate) fn f64_cbor_data(value: f64) -> Vec<u8> {
    if let Some(integer) = reduced_integer(value) {
        return integer.to_cbor_data();
    }
    let narrow = value as f32;
    if narrow as f64 == value {
        return f32_cbor_data(narrow);
    }
    if value.is_nan() {
        return CBOR_NAN.to_vec();
    }
    value.to_bits().encode_int(MajorType::Simple)
}

pub(crate) fn validate_canonical_f64(n: f64) -> Result<()> {
    if n == (n as f32 as f64) || reduced_integer(n).is_some() || n.is_nan() {
        return Err(Error::NonCanonicalNumeric);
    }
    Ok(())
}

impl TryFrom<CBOR> for f64 {
    type Error = Error;

    fn try_from(cbor: CBOR) -> Result<Self> {
        match cbor.into_case() {
            CBORCase::Unsigned(n) => {
                if let Some(f) = f64::exact_from_u64(n) {
                    Ok(f)
                } else {
                    Err(Error::OutOfRange)
                }
            }
            CBORCase::Negative(n) => {
                if let Some(f) = exact_f64_from_negative(n) {
                    Ok(f)
                } else {
                    Err(Error::OutOfRange)
                }
            }
            CBORCase::Simple(Simple::Float(n)) => Ok(n),
            _ => Err(Error::WrongType),
        }
    }
}

impl From<f32> for CBOR {
    fn from(value: f32) -> Self {
        CBOR::from(value as f64)
    }
}

pub(crate) fn f32_cbor_data(value: f32) -> Vec<u8> {
    if let Some(integer) = reduced_integer(value as f64) {
        return integer.to_cbor_data();
    }
    let narrow = f16::from_f32(value);
    if narrow.to_f32() == value {
        return f16_cbor_data(narrow);
    }
    if value.is_nan() {
        return CBOR_NAN.to_vec();
    }
    value.to_bits().encode_int(MajorType::Simple)
}

pub(crate) fn validate_canonical_f32(n: f32) -> Result<()> {
    if n == f16::from_f32(n).to_f32()
        || reduced_integer(n as f64).is_some()
        || n.is_nan()
    {
        return Err(Error::NonCanonicalNumeric);
    }
    Ok(())
}

impl TryFrom<CBOR> for f32 {
    type Error = Error;

    fn try_from(cbor: CBOR) -> Result<Self> {
        match cbor.into_case() {
            CBORCase::Unsigned(n) => {
                if let Some(f) = f32::exact_from_u64(n) {
                    Ok(f)
                } else {
                    Err(Error::OutOfRange)
                }
            }
            CBORCase::Negative(n) => {
                if let Some(f) = exact_f32_from_negative(n) {
                    Ok(f)
                } else {
                    Err(Error::OutOfRange)
                }
            }
            CBORCase::Simple(Simple::Float(n)) => {
                if let Some(f) = f32::exact_from_f64(n) {
                    Ok(f)
                } else {
                    Err(Error::OutOfRange)
                }
            }
            _ => Err(Error::WrongType),
        }
    }
}

impl From<f16> for CBOR {
    fn from(value: f16) -> Self {
        CBOR::from(value.to_f64())
    }
}

pub(crate) fn f16_cbor_data(value: f16) -> Vec<u8> {
    if let Some(integer) = reduced_integer(value.to_f64()) {
        return integer.to_cbor_data();
    }
    if value.is_nan() {
        return CBOR_NAN.to_vec();
    }
    value.to_bits().encode_int(MajorType::Simple)
}

impl TryFrom<CBOR> for f16 {
    type Error = Error;

    fn try_from(cbor: CBOR) -> Result<Self> {
        match cbor.into_case() {
            CBORCase::Unsigned(n) => {
                if let Some(f) = f16::exact_from_u64(n) {
                    Ok(f)
                } else {
                    Err(Error::OutOfRange)
                }
            }
            CBORCase::Negative(n) => {
                if let Some(f) = f64::exact_from_u64(n) {
                    if let Some(b) = f16::exact_from_f64(-1f64 - f) {
                        Ok(b)
                    } else {
                        Err(Error::OutOfRange)
                    }
                } else {
                    Err(Error::OutOfRange)
                }
            }
            CBORCase::Simple(Simple::Float(n)) => {
                if let Some(f) = f16::exact_from_f64(n) {
                    Ok(f)
                } else {
                    Err(Error::OutOfRange)
                }
            }
            _ => Err(Error::WrongType),
        }
    }
}

pub(crate) fn validate_canonical_f16(n: f16) -> Result<()> {
    let f = n.to_f64();
    if reduced_integer(f).is_some() || (n.is_nan() && n.to_bits() != 0x7e00) {
        return Err(Error::NonCanonicalNumeric);
    }
    Ok(())
}
