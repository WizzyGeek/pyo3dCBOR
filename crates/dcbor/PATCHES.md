# Local dcbor 0.25.2 patch

This directory vendors the published `dcbor` 0.25.2 crate from crates.io,
corresponding to upstream revision
`c76a15a3729b5753824d0b08b95a08d7c7d8998d` in
<https://github.com/BlockchainCommons/bc-dcbor-rust>.
The original BSD-2-Clause-Patent license is retained in `LICENSE.md`.

The parent depends on this directory directly so source distributions include
the patched codec. Its package file list excludes the registry-generated
`Cargo.toml.orig` and `.cargo_vcs_info.json` inputs to allow Cargo to repackage
the crate; the upstream revision is recorded above.

The upstream runtime source modifications are:

### `src/float.rs`

- Float-to-integer reduction uses the draft-18 section 2.5 interval
  `[-2^63, 2^64)`, with an integral-value requirement. Integral floating
  values below `-2^63` remain floats and use their shortest exact float
  width. The separate major-type-1 integer API remains unchanged.
- All half-, single-, and double-precision construction, serialization,
  and canonical numeric validation paths share this reduction policy.
- Negative CBOR integer magnitudes are calculated in integer arithmetic,
  avoiding rounded `-1 - n` arithmetic in single precision.
- Validators recognize integral values across the full reduction interval,
  including positive values above the signed integer range, and reject
  their noncanonical floating encodings.
- Negative integer extraction to `f32` and `f64` now forms the represented
  `-1 - n` integer before checking exactness. This fixes the inherited `f32`
  sign error and accepts signed values that are exact even when their encoded
  major-type-1 magnitude is not, including `-(2^53 + 2)` for `f64`.
- Existing shortest-width float rules, signed-zero reduction, canonical
  NaN, and half-precision infinity encodings are preserved.

### `src/cbor.rs`

- ASCII text serialization copies the already-normalized bytes directly,
  avoiding an unnecessary Unicode normalization allocation. Non-ASCII text
  still follows the original NFC normalization path.

Regression coverage for these rules is in the parent project's independent
`tests/test_spec_conformance.py` and `tests/test_wire_safety.py`. The upstream
Rust tests and examples are retained for reference and compatibility checks.
Four numeric float fixtures in `tests/encode.rs` now expect literal preferred
floating encodings below `-2^63`, with matching float debug and diagnostic
representations. Their old integer expectations contradicted draft-18 section
2.5. Explicit major-type-1 integer fixtures remain unchanged.
Direct integer-extraction regressions cover small negative values, the binary32
and binary64 consecutive-integer boundaries, and the explicit `-2^64` endpoint.
Text serialization fixtures cover empty and control-containing ASCII as well as
NFC contraction and expansion.
