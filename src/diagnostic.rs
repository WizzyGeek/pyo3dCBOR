//! Borrowed-wire CBOR diagnostic formatting for the Python binding.
//!
//! The formatter accepts only fully preflighted canonical dCBOR. It reads
//! scalar payloads from the input slice and writes directly into its returned
//! `String`, without constructing an intermediate CBOR tree.

use std::fmt::{self, Write as FmtWrite};

use half::f16;
use pyo3::prelude::*;

use crate::wire::{self, Cursor, Header};

const LINE_BREAK_THRESHOLD: usize = 20;
const CAPPED_LENGTH: usize = LINE_BREAK_THRESHOLD + 1;

#[derive(Clone, Copy, Default)]
struct FormatStats {
    is_group: bool,
    contains_group: bool,
    total_strings_len: usize,
    greatest_strings_len: usize,
}

/// Return default CBOR diagnostic notation, optionally flattened to one line.
///
/// Validation runs before formatting so malformed or noncanonical inputs fail
/// with the same wire error path as the decoder, and the formatter can safely
/// borrow text and byte-string spans from `data`.
pub(crate) fn format(data: &[u8], flat: bool) -> PyResult<String> {
    wire::preflight(data)?;

    let mut cursor = Cursor::new(data);
    let mut output = String::new();
    if flat {
        write_single_item(&mut cursor, &mut output)?;
    } else {
        write_pretty_item(&mut cursor, &mut output, 0, "")?;
    }
    cursor.finish()?;
    Ok(output)
}

fn capped_add(left: usize, right: usize) -> usize {
    left.saturating_add(right).min(CAPPED_LENGTH)
}

fn stats_for_scalar(length: usize) -> FormatStats {
    let length = length.min(CAPPED_LENGTH);
    FormatStats {
        total_strings_len: length,
        greatest_strings_len: length,
        ..FormatStats::default()
    }
}

fn merge_child(parent: &mut FormatStats, child: FormatStats) {
    parent.contains_group |= child.is_group;
    parent.total_strings_len =
        capped_add(parent.total_strings_len, child.total_strings_len);
    parent.greatest_strings_len =
        parent.greatest_strings_len.max(child.total_strings_len);
}

/// Measure one item without retaining per-item metadata. The caller uses a
/// cloned cursor, so rendering remains a single forward pass over the input.
fn measure_item(cursor: &mut Cursor<'_>) -> PyResult<FormatStats> {
    let header = cursor.read_header()?;
    match header.major {
        0 => Ok(stats_for_scalar(decimal_len_u64(header.argument))),
        1 => {
            let value = -1i128 - i128::from(header.argument);
            Ok(stats_for_scalar(decimal_len_i128(value)))
        }
        2 => {
            let bytes = cursor.read_payload(header.argument)?;
            let length = capped_add(3, capped_mul_2(bytes.len()));
            Ok(stats_for_scalar(length))
        }
        3 => {
            let bytes = cursor.read_payload(header.argument)?;
            std::str::from_utf8(bytes).map_err(|_| wire::invalid_data())?;
            let quote_count = bytes.iter().filter(|&&byte| byte == b'"').count();
            let length = capped_add(2, capped_add(bytes.len(), quote_count));
            Ok(stats_for_scalar(length))
        }
        4 | 5 | 6 => {
            let child_count = match header.major {
                4 => header.argument,
                5 => header
                    .argument
                    .checked_mul(2)
                    .ok_or_else(wire::invalid_data)?,
                _ => 1,
            };
            let mut stats = FormatStats {
                is_group: true,
                ..FormatStats::default()
            };
            for _ in 0..child_count {
                let child = measure_item(cursor)?;
                merge_child(&mut stats, child);
            }
            Ok(stats)
        }
        7 => Ok(stats_for_scalar(simple_display_len(&header)?)),
        _ => Err(wire::invalid_data()),
    }
}

fn capped_mul_2(value: usize) -> usize {
    value.saturating_mul(2).min(CAPPED_LENGTH)
}

fn decimal_len_u64(value: u64) -> usize {
    let mut value = value;
    let mut length = 1;
    while value >= 10 {
        value /= 10;
        length += 1;
    }
    length
}

fn decimal_len_i128(value: i128) -> usize {
    if value < 0 {
        1 + decimal_len_u128(value.unsigned_abs())
    } else {
        decimal_len_u128(value as u128)
    }
}

fn decimal_len_u128(value: u128) -> usize {
    let mut value = value;
    let mut length = 1;
    while value >= 10 {
        value /= 10;
        length += 1;
    }
    length
}

struct LengthWriter(usize);

impl FmtWrite for LengthWriter {
    fn write_str(&mut self, value: &str) -> fmt::Result {
        self.0 = capped_add(self.0, value.len());
        Ok(())
    }
}

fn float_value(header: &Header) -> PyResult<f64> {
    match header.additional_info {
        25 => Ok(f16::from_bits(header.argument as u16).to_f64()),
        26 => Ok(f32::from_bits(header.argument as u32) as f64),
        27 => Ok(f64::from_bits(header.argument)),
        _ => Err(wire::invalid_data()),
    }
}

fn simple_display_len(header: &Header) -> PyResult<usize> {
    match header.additional_info {
        20 => Ok(5), // false
        21 => Ok(4), // true
        22 => Ok(4), // null
        25..=27 => {
            let value = float_value(header)?;
            let length = if value.is_nan() {
                3
            } else if value.is_infinite() {
                if value.is_sign_positive() { 8 } else { 9 }
            } else {
                let mut counter = LengthWriter(0);
                write!(&mut counter, "{value:?}").expect("length writer is infallible");
                counter.0
            };
            Ok(length)
        }
        _ => Err(wire::invalid_data()),
    }
}

fn write_pretty_item(
    cursor: &mut Cursor<'_>,
    output: &mut String,
    level: usize,
    separator: &str,
) -> PyResult<()> {
    let mut probe = cursor.clone();
    let header = probe.read_header()?;
    if !matches!(header.major, 4..=6) {
        let header = cursor.read_header()?;
        write_indent(output, level);
        write_scalar(cursor, output, &header)?;
        output.push_str(separator);
        return Ok(());
    }

    let mut measure_cursor = cursor.clone();
    let stats = measure_item(&mut measure_cursor)?;
    let header = cursor.read_header()?;
    let multiline = stats.contains_group
        || stats.total_strings_len > LINE_BREAK_THRESHOLD
        || stats.greatest_strings_len > LINE_BREAK_THRESHOLD;
    if !multiline {
        write_indent(output, level);
        write_single_group(cursor, output, &header)?;
        output.push_str(separator);
        return Ok(());
    }

    write_indent(output, level);
    write_group_begin(output, &header)?;
    let child_count = group_child_count(&header)?;
    for index in 0..child_count {
        output.push('\n');
        write_pretty_item(
            cursor,
            output,
            level + 1,
            child_separator(header.major, index, child_count),
        )?;
    }
    output.push('\n');
    write_indent(output, level);
    write_group_end(output, &header)?;
    output.push_str(separator);
    Ok(())
}

fn group_child_count(header: &Header) -> PyResult<u64> {
    match header.major {
        4 => Ok(header.argument),
        5 => header
            .argument
            .checked_mul(2)
            .ok_or_else(wire::invalid_data),
        6 => Ok(1),
        _ => Err(wire::invalid_data()),
    }
}

fn child_separator(major: u8, index: u64, child_count: u64) -> &'static str {
    if index + 1 == child_count {
        ""
    } else if major == 5 && index & 1 == 0 {
        ":"
    } else {
        ","
    }
}

fn write_indent(output: &mut String, level: usize) {
    for _ in 0..level * 4 {
        output.push(' ');
    }
}

fn write_group_begin(output: &mut String, header: &Header) -> PyResult<()> {
    match header.major {
        4 => output.push('['),
        5 => output.push('{'),
        6 => {
            write!(output, "{}(", header.argument)
                .expect("writing into String is infallible");
        }
        _ => return Err(wire::invalid_data()),
    }
    Ok(())
}

fn write_group_end(output: &mut String, header: &Header) -> PyResult<()> {
    match header.major {
        4 => output.push(']'),
        5 => output.push('}'),
        6 => output.push(')'),
        _ => return Err(wire::invalid_data()),
    }
    Ok(())
}

fn write_single_item(cursor: &mut Cursor<'_>, output: &mut String) -> PyResult<()> {
    let header = cursor.read_header()?;
    match header.major {
        4 | 5 | 6 => write_single_group(cursor, output, &header),
        _ => write_scalar(cursor, output, &header),
    }
}

fn write_single_group(
    cursor: &mut Cursor<'_>,
    output: &mut String,
    header: &Header,
) -> PyResult<()> {
    write_group_begin(output, header)?;
    let child_count = group_child_count(header)?;
    for index in 0..child_count {
        if index != 0 {
            output.push_str(if header.major == 5 && index & 1 == 0 {
                ", "
            } else if header.major == 5 {
                ": "
            } else {
                ", "
            });
        }
        write_single_item(cursor, output)?;
    }
    write_group_end(output, header)
}

fn write_scalar(
    cursor: &mut Cursor<'_>,
    output: &mut String,
    header: &Header,
) -> PyResult<()> {
    match header.major {
        0 => write!(output, "{}", header.argument)
            .expect("writing into String is infallible"),
        1 => write!(output, "{}", -1i128 - i128::from(header.argument))
            .expect("writing into String is infallible"),
        2 => write_bytes(cursor, output, header.argument)?,
        3 => write_text(cursor, output, header.argument)?,
        7 => write_simple(output, header)?,
        _ => return Err(wire::invalid_data()),
    }
    Ok(())
}

fn write_bytes(cursor: &mut Cursor<'_>, output: &mut String, length: u64) -> PyResult<()> {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let bytes = cursor.read_payload(length)?;
    output.push_str("h'");
    for &byte in bytes {
        output.push(HEX[(byte >> 4) as usize] as char);
        output.push(HEX[(byte & 0x0f) as usize] as char);
    }
    output.push('\'');
    Ok(())
}

fn write_text(cursor: &mut Cursor<'_>, output: &mut String, length: u64) -> PyResult<()> {
    let bytes = cursor.read_payload(length)?;
    let text = std::str::from_utf8(bytes).map_err(|_| wire::invalid_data())?;
    output.push('"');
    for character in text.chars() {
        if character == '"' {
            output.push_str("\\\"");
        } else {
            output.push(character);
        }
    }
    output.push('"');
    Ok(())
}

fn write_simple(output: &mut String, header: &Header) -> PyResult<()> {
    match header.additional_info {
        20 => output.push_str("false"),
        21 => output.push_str("true"),
        22 => output.push_str("null"),
        25..=27 => write_float(output, float_value(header)?),
        _ => return Err(wire::invalid_data()),
    }
    Ok(())
}

fn write_float(output: &mut String, value: f64) {
    if value.is_nan() {
        output.push_str("NaN");
    } else if value.is_infinite() {
        output.push_str(if value.is_sign_positive() {
            "Infinity"
        } else {
            "-Infinity"
        });
    } else {
        write!(output, "{value:?}").expect("writing into String is infallible");
    }
}
