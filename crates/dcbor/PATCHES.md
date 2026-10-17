# Local dcbor 0.25.2 patch

Maintainer: **WizzyGeek** ([@WizzyGeek](https://github.com/WizzyGeek)), the
owner of [this repository](https://github.com/WizzyGeek/pyo3dCBOR), is
responsible for refreshing this vendor, reviewing upstream changes, and
maintaining the local patch.

This directory vendors the published `dcbor` 0.25.2 crate from crates.io,
corresponding to upstream revision
`c76a15a3729b5753824d0b08b95a08d7c7d8998d` in
<https://github.com/BlockchainCommons/bc-dcbor-rust>.
The crates.io archive SHA-256 is
`fcf662b6347d10dd5ab7370287b76923eb88818d46434de8c424b091523f5e54`.
The original BSD-2-Clause-Patent license is retained in `LICENSE.md`.

The parent depends on this directory directly so source distributions include
the patched codec. Its package file list excludes the registry-generated
`Cargo.toml.orig` and `.cargo_vcs_info.json` inputs to allow Cargo to repackage
the crate; the upstream revision and archive checksum are recorded above. The
vendored `Cargo.lock` is kept under version control for its standalone locked
test job. These local packaging changes, as well as the runtime/test changes,
are recorded in [`local.patch`](local.patch). The Python source archive omits
the upstream `README.md`, which contains unrelated fundraising material, and
`SECURITY-REVIEW.md`; it retains the license and local patch provenance.

The checked vendor scope is the crate manifest and lockfile, `.gitignore`, the
license, and every file under `src/`, `tests/`, and `examples/`. Upstream project
process documents and registry metadata are not part of this maintained scope.

## Refresh and verification

The repeatable, non-destructive check downloads the pinned archive only when
it is not already in Cargo's registry cache, checks its checksum and upstream
revision, applies `local.patch` to a temporary extraction, and compares the
maintained vendor scope with this directory. It then runs the Rust crate tests with a
temporary Cargo target directory, leaving the vendored sources and lockfile
untouched:

```sh
python3 scripts/vendor_dcbor.py verify --tests
```

To review the complete local diff against the pinned crates.io archive without
writing files:

```sh
python3 scripts/vendor_dcbor.py diff
```

When changing a local patch, edit the vendored files, inspect the diff, then
regenerate only the patch artifact and rerun verification:

```sh
python3 scripts/vendor_dcbor.py diff
python3 scripts/vendor_dcbor.py update-patch
python3 scripts/vendor_dcbor.py verify --tests
```

For an upstream refresh, select and review a new crates.io release and its
matching upstream Git revision, then update the version, archive checksum,
revision, and archive URL pins in `scripts/vendor_dcbor.py`. Refresh the vendor
tree from that archive, reapply the retained local changes, regenerate
`local.patch`, and run the verification command above. Keep the refresh in a
reviewable change so upstream drift and project-specific patch changes can be
checked independently.

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
