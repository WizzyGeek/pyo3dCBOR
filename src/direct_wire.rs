//! Small canonical dCBOR wire primitives for the direct Python encoder.
//!
//! These helpers append into a caller-owned buffer. They deliberately avoid
//! constructing `dcbor::CBOR` values or allocating a temporary `Vec` per
//! scalar. Float selection follows the patched vendored dCBOR float encoder.

use half::f16;
use std::io::{self, Write};

/// The canonical wire representation selected for an f64 input.
///
/// Keeping the selected form lets callers use `encoded_len` for accounting
/// and then emit the exact same representation with either writer method.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum FloatEncoding {
    ReducedInteger { major: u8, argument: u64 },
    Half(u16),
    Single(u32),
    Double(u64),
}

impl FloatEncoding {
    /// Select the canonical dCBOR representation for an f64 value.
    pub(crate) fn from_f64(value: f64) -> Self {
        // Draft-18 numeric reduction applies to [-2^63, 2^64). Keep this
        // separate from the explicit Python integer range [-2^64, 2^64-1].
        if value >= -9_223_372_036_854_775_808.0
            && value < 18_446_744_073_709_551_616.0
            && value.fract() == 0.0
        {
            // Bounds and the integral check make this cast exact. Negative
            // CBOR arguments encode -1 - n, which is computed as an integer
            // to avoid floating-point rounding at large magnitudes.
            let integer = value as i128;
            if integer < 0 {
                return Self::ReducedInteger {
                    major: 1,
                    argument: (-1 - integer) as u64,
                };
            }
            return Self::ReducedInteger {
                major: 0,
                argument: integer as u64,
            };
        }

        // Canonicalize all NaN signs and payloads before choosing a width.
        if value.is_nan() {
            return Self::Half(0x7e00);
        }

        let as_f32 = value as f32;
        if as_f32 as f64 == value {
            let as_f16 = f16::from_f32(as_f32);
            if as_f16.to_f32() == as_f32 {
                return Self::Half(as_f16.to_bits());
            }
            return Self::Single(as_f32.to_bits());
        }

        Self::Double(value.to_bits())
    }

    /// Number of wire bytes this representation will append.
    pub(crate) fn encoded_len(self) -> usize {
        match self {
            Self::ReducedInteger { argument, .. } => header_len(argument),
            Self::Half(_) => 3,
            Self::Single(_) => 5,
            Self::Double(_) => 9,
        }
    }

    /// Append the selected canonical wire representation.
    pub(crate) fn write_to(self, out: &mut Vec<u8>) {
        self.write_to_writer(out)
            .expect("writing canonical dCBOR bytes into Vec cannot fail");
    }

    /// Write the selected canonical representation to any byte writer.
    pub(crate) fn write_to_writer<W: Write + ?Sized>(
        self,
        out: &mut W,
    ) -> io::Result<()> {
        match self {
            Self::ReducedInteger { major, argument } => {
                write_header_to(major, argument, out)
            }
            Self::Half(bits) => out.write_all(&[
                0xf9,
                (bits >> 8) as u8,
                bits as u8,
            ]),
            Self::Single(bits) => out.write_all(&[
                0xfa,
                (bits >> 24) as u8,
                (bits >> 16) as u8,
                (bits >> 8) as u8,
                bits as u8,
            ]),
            Self::Double(bits) => out.write_all(&[
                0xfb,
                (bits >> 56) as u8,
                (bits >> 48) as u8,
                (bits >> 40) as u8,
                (bits >> 32) as u8,
                (bits >> 24) as u8,
                (bits >> 16) as u8,
                (bits >> 8) as u8,
                bits as u8,
            ]),
        }
    }
}

/// Return the canonical CBOR head length for an unsigned argument.
pub(crate) fn header_len(value: u64) -> usize {
    if value <= 23 {
        1
    } else if value <= u8::MAX as u64 {
        2
    } else if value <= u16::MAX as u64 {
        3
    } else if value <= u32::MAX as u64 {
        5
    } else {
        9
    }
}

/// Append a canonical CBOR initial byte and unsigned argument.
///
/// `major` is the three-bit CBOR major type (0 through 7). For ordinary
/// semantic values callers use 0 through 6; floating-point simple headers are
/// emitted directly by `FloatEncoding`.
pub(crate) fn write_header(major: u8, value: u64, out: &mut Vec<u8>) {
    write_header_to(major, value, out)
        .expect("writing canonical CBOR header into Vec cannot fail");
}

/// Write a canonical CBOR initial byte and unsigned argument to any writer.
///
/// A fixed stack buffer keeps this helper allocation-free and gives the
/// writer one `write_all` call per header. `write_all` propagates I/O failures
/// and handles writers that accept only a prefix at a time.
pub(crate) fn write_header_to<W: Write + ?Sized>(
    major: u8,
    value: u64,
    out: &mut W,
) -> io::Result<()> {
    debug_assert!(major <= 7, "CBOR major type must fit in three bits");
    let major_bits = major << 5;
    let mut bytes = [0u8; 9];
    let len;
    if value <= 23 {
        bytes[0] = major_bits | value as u8;
        len = 1;
    } else if value <= u8::MAX as u64 {
        bytes[0] = major_bits | 24;
        bytes[1] = value as u8;
        len = 2;
    } else if value <= u16::MAX as u64 {
        bytes[0] = major_bits | 25;
        bytes[1..3].copy_from_slice(&(value as u16).to_be_bytes());
        len = 3;
    } else if value <= u32::MAX as u64 {
        bytes[0] = major_bits | 26;
        bytes[1..5].copy_from_slice(&(value as u32).to_be_bytes());
        len = 5;
    } else {
        bytes[0] = major_bits | 27;
        bytes[1..9].copy_from_slice(&value.to_be_bytes());
        len = 9;
    }
    out.write_all(&bytes[..len])
}

#[cfg(test)]
mod tests {
    use super::{header_len, write_header, write_header_to, FloatEncoding};
    use half::f16;
    use std::io::{self, Write};

    fn encoded(value: f64) -> Vec<u8> {
        let representation = FloatEncoding::from_f64(value);
        let mut bytes = Vec::with_capacity(representation.encoded_len());
        representation.write_to(&mut bytes);
        assert_eq!(bytes.len(), representation.encoded_len());
        bytes
    }

    #[test]
    fn headers_use_preferred_argument_widths() {
        let cases = [
            (0, 1, vec![0x00]),
            (23, 1, vec![0x17]),
            (24, 2, vec![0x18, 0x18]),
            (255, 2, vec![0x18, 0xff]),
            (256, 3, vec![0x19, 0x01, 0x00]),
            (65_535, 3, vec![0x19, 0xff, 0xff]),
            (65_536, 5, vec![0x1a, 0x00, 0x01, 0x00, 0x00]),
            (
                u32::MAX as u64,
                5,
                vec![0x1a, 0xff, 0xff, 0xff, 0xff],
            ),
            (
                u32::MAX as u64 + 1,
                9,
                vec![0x1b, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00],
            ),
        ];

        for (value, expected_len, expected_bytes) in cases {
            assert_eq!(header_len(value), expected_len);
            let mut bytes = Vec::new();
            write_header(0, value, &mut bytes);
            assert_eq!(bytes, expected_bytes);
        }
    }

    #[test]
    fn floats_match_patched_dcbor_canonical_vectors() {
        let cases = [
            (0.0, vec![0x00]),
            (-0.0, vec![0x00]),
            (1.5, vec![0xf9, 0x3e, 0x00]),
            (
                f16::from_bits(0x3555).to_f64(),
                vec![0xf9, 0x35, 0x55],
            ),
            (65_504.0, vec![0x19, 0xff, 0xe0]),
            (2_345_678.25, vec![0xfa, 0x4a, 0x0f, 0x2b, 0x39]),
            (
                1.2,
                vec![0xfb, 0x3f, 0xf3, 0x33, 0x33, 0x33, 0x33, 0x33, 0x33],
            ),
            (
                -9_223_372_036_854_775_808.0,
                vec![0x3b, 0x7f, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff],
            ),
            (
                18_446_744_073_709_549_568.0,
                vec![0x1b, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xf8, 0x00],
            ),
            (18_446_744_073_709_551_616.0, vec![0xfa, 0x5f, 0x80, 0x00, 0x00]),
            (f64::INFINITY, vec![0xf9, 0x7c, 0x00]),
            (f64::NEG_INFINITY, vec![0xf9, 0xfc, 0x00]),
            (f64::NAN, vec![0xf9, 0x7e, 0x00]),
            (f64::from_bits(0xfff0_0000_0000_0001), vec![0xf9, 0x7e, 0x00]),
        ];

        for (value, expected) in cases {
            assert_eq!(encoded(value), expected, "value {value:?}");
        }
    }

    struct FailingWriter;

    impl Write for FailingWriter {
        fn write(&mut self, _buffer: &[u8]) -> io::Result<usize> {
            Err(io::ErrorKind::BrokenPipe.into())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    #[test]
    fn generic_writers_propagate_io_errors() {
        let mut writer = FailingWriter;
        let error = write_header_to(0, 24, &mut writer).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::BrokenPipe);

        let error = FloatEncoding::from_f64(1.5)
            .write_to_writer(&mut writer)
            .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::BrokenPipe);
    }
}
