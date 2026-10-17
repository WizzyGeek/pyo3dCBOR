//! Small native worker used by `benchmarks/rust_core.py`.
//!
//! The worker accepts dCBOR wire bytes created by Python, parses each tree
//! before timing, and measures core encoding and decoding without a Python
//! call in the timed region. It intentionally has no serialization or CLI
//! dependencies beyond the repository's patched `dcbor` crate.

use std::env;
use std::hint::black_box;
use std::process;
use std::time::Instant;

use dcbor::CBOR;

struct Fixture {
    name: String,
    wire: Vec<u8>,
    tree: CBOR,
    encode_ns: f64,
    decode_ns: f64,
}

fn parse_usize(value: Option<String>, flag: &str) -> Result<usize, String> {
    let text = value.ok_or_else(|| format!("missing value for {flag}"))?;
    let parsed = text
        .parse::<usize>()
        .map_err(|_| format!("{flag} must be a non-negative integer"))?;
    Ok(parsed)
}

fn decode_hex(hex: &str) -> Result<Vec<u8>, String> {
    if hex.len() % 2 != 0 {
        return Err("fixture wire hex has an odd number of digits".to_owned());
    }
    let mut bytes = Vec::with_capacity(hex.len() / 2);
    let mut digits = hex.bytes();
    while let (Some(high), Some(low)) = (digits.next(), digits.next()) {
        let high = (high as char)
            .to_digit(16)
            .ok_or_else(|| "fixture wire contains non-hexadecimal digits".to_owned())?;
        let low = (low as char)
            .to_digit(16)
            .ok_or_else(|| "fixture wire contains non-hexadecimal digits".to_owned())?;
        bytes.push(((high << 4) | low) as u8);
    }
    Ok(bytes)
}

fn valid_fixture_name(name: &str) -> bool {
    !name.is_empty()
        && name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-')
}

fn measure_encode(tree: &CBOR, warmup: usize, rounds: usize) -> f64 {
    for _ in 0..warmup {
        black_box(tree.to_cbor_data());
    }
    let start = Instant::now();
    for _ in 0..rounds {
        black_box(black_box(tree).to_cbor_data());
    }
    start.elapsed().as_nanos() as f64 / rounds as f64
}

fn measure_decode(wire: &[u8], warmup: usize, rounds: usize) -> f64 {
    for _ in 0..warmup {
        black_box(CBOR::try_from_data(black_box(wire)).expect("validated fixture"));
    }
    let start = Instant::now();
    for _ in 0..rounds {
        black_box(CBOR::try_from_data(black_box(wire)).expect("validated fixture"));
    }
    start.elapsed().as_nanos() as f64 / rounds as f64
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let mut warmup = None;
    let mut rounds = None;
    let mut order_offset = 0usize;
    let mut fixture_args = Vec::new();

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--warmup" => warmup = Some(parse_usize(args.next(), "--warmup")?),
            "--rounds" => rounds = Some(parse_usize(args.next(), "--rounds")?),
            "--order-offset" => {
                order_offset = parse_usize(args.next(), "--order-offset")?
            }
            "--help" | "-h" => {
                println!(
                    "usage: benchmark-core --warmup N --rounds N [--order-offset N] name=wire_hex ..."
                );
                return Ok(());
            }
            _ if arg.contains('=') => fixture_args.push(arg),
            _ => return Err(format!("unexpected argument {arg:?}")),
        }
    }

    let warmup = warmup.ok_or_else(|| "--warmup is required".to_owned())?;
    let rounds = rounds.ok_or_else(|| "--rounds is required".to_owned())?;
    if rounds == 0 {
        return Err("--rounds must be greater than zero".to_owned());
    }
    if fixture_args.is_empty() {
        return Err("at least one name=wire_hex fixture is required".to_owned());
    }

    let mut fixtures = Vec::with_capacity(fixture_args.len());
    for arg in fixture_args {
        let (name, hex) = arg
            .split_once('=')
            .ok_or_else(|| format!("fixture argument must be name=wire_hex: {arg:?}"))?;
        if !valid_fixture_name(name) {
            return Err(format!("fixture name contains unsupported characters: {name:?}"));
        }
        if fixtures.iter().any(|fixture: &Fixture| fixture.name == name) {
            return Err(format!("duplicate fixture name {name:?}"));
        }
        let wire = decode_hex(hex)?;
        let tree = CBOR::try_from_data(&wire)
            .map_err(|error| format!("could not decode fixture {name}: {error}"))?;
        let reencoded = tree.to_cbor_data();
        if reencoded != wire {
            return Err(format!("Rust re-encoding changed fixture wire bytes for {name}"));
        }
        fixtures.push(Fixture {
            name: name.to_owned(),
            wire,
            tree,
            encode_ns: 0.0,
            decode_ns: 0.0,
        });
    }

    let count = fixtures.len();
    let first = order_offset % count;
    fixtures.rotate_left(first);
    for (index, fixture) in fixtures.iter_mut().enumerate() {
        if (order_offset + index) % 2 == 0 {
            fixture.encode_ns = measure_encode(&fixture.tree, warmup, rounds);
            fixture.decode_ns = measure_decode(&fixture.wire, warmup, rounds);
        } else {
            fixture.decode_ns = measure_decode(&fixture.wire, warmup, rounds);
            fixture.encode_ns = measure_encode(&fixture.tree, warmup, rounds);
        }
    }

    print!("{{\"fixtures\":{{");
    for (index, fixture) in fixtures.iter().enumerate() {
        if index > 0 {
            print!(",");
        }
        print!(
            "\"{}\":{{\"wire_hex\":\"{}\",\"encode_ns_per_operation\":{:.6},\"decode_ns_per_operation\":{:.6}}}",
            fixture.name,
            fixture.wire.iter().map(|byte| format!("{byte:02x}")).collect::<String>(),
            fixture.encode_ns,
            fixture.decode_ns
        );
    }
    println!("}}}}");
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("benchmark-core: {error}");
        process::exit(2);
    }
}
