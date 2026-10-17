> Disclaimer: This is AI generated, tested and verified code (not assisted,
this was done with minimal oversight!)
Credits to claude (build) and codex (review and fixes)

# dcbor

Python bindings for [Blockchain Commons' `dcbor`](https://github.com/BlockchainCommons/bc-dcbor-rust)
Rust crate — a deterministic CBOR ("dCBOR") encoder/decoder implementing the
constraints of the dCBOR specification (RFC 8949 §4.2.1 plus the dCBOR
application profile): canonical shortest-form integers, floating-point
numeric reduction, NFC-normalized strings, lexicographically ordered map
keys, and rejection of non-canonical encodings on decode.

Core encoding/decoding runs in the Rust crate via [PyO3](https://pyo3.rs/).
The bindings convert Python values and check wire-level numeric canonicality,
nesting depth, and aggregate encoded map-key storage before decoding.
The published `dcbor` 0.25.2 codec is included with a narrow numeric-reduction
patch; its source, license, provenance, and changes are in
[`crates/dcbor`](crates/dcbor/PATCHES.md).

## Install (from source)

```sh
pip install maturin
maturin develop --release   # or: maturin build --release && pip install target/wheels/*.whl
```

## Usage

```python
import dcbor

data = dcbor.dumps({"b": 2, "a": [1, 2, 3], "c": None})
assert dcbor.loads(data) == {"a": [1, 2, 3], "b": 2, "c": None}

print(dcbor.diagnostic(data))
# {"a": [1, 2, 3], "b": 2, "c": null}
```

### Supported types

| Python                 | dCBOR                          |
|------------------------|---------------------------------|
| `None`                 | simple value `null`             |
| `bool`                 | simple value `true`/`false`     |
| `int`                  | major type 0/1 (unsigned/negative, must fit `[-2**64, 2**64-1]`) |
| `float`                | preferred-width float; integral values in `[-2**63, 2**64)` reduce to integers |
| `str`                  | major type 3 text string (NFC-normalized; lone surrogates rejected) |
| `bytes` / `bytearray`  | major type 2 byte string        |
| `list` / `tuple`       | major type 4 array              |
| `dict` / `dcbor.CBORMap` | major type 5 map (keys sorted into canonical order automatically) |
| `datetime.datetime`    | tag 1 (epoch date/time)         |
| `dcbor.CBORTag`        | arbitrary tag (major type 6)    |

`loads()` maps numeric tag 1 values to aware UTC `datetime.datetime` values.
Nonfinite timestamps and dates outside Python's supported range raise
`CBORError`. Other tags, including nonnumeric tag 1 values, decode to `CBORTag`.
`datetime.datetime` values passed to `dumps()` must be timezone-aware —
naive datetimes are rejected with `CBORError` rather than silently encoded
using the host machine's local timezone, which would make the encoding
depend on where it runs (unacceptable for a *deterministic* format).

Maps normally decode to `dict`. When keys are unhashable or distinct CBOR
keys compare equal in Python (such as `1` and `True`), they decode to
`CBORMap`, a read-only snapshot with lookups based on canonical key encodings:

```python
mapping = dcbor.CBORMap([(1, "integer"), (True, "boolean")])
assert mapping[1] == "integer"
assert mapping[True] == "boolean"
assert dcbor.dumps(dcbor.loads(dcbor.dumps(mapping))) == dcbor.dumps(mapping)
```

`CBORMap` supports indexing, membership, iteration, `len()`, `get()`,
`keys()`, `values()`, and `items()`. Returned containers are fresh decoded
values; changing them does not modify the snapshot. Its constructor accepts
key/value pairs and rejects duplicate canonical keys. Converting it to a
Python `dict` can lose distinctions such as `1` versus `True`.

Map-key conversion preserves canonical encoding throughout composite keys.
Numeric date keys become `datetime` only when that conversion round-trips
exactly; otherwise they retain their original `CBORTag` representation.
Thus keys returned by iteration, `keys()`, and `items()` remain usable for
membership checks and lookup, including sub-microsecond date keys.

`CBORTag` remains mutable and is unhashable. Tagged map keys use `CBORMap`.
Strings are read from their actual Unicode contents, without calling a
subclass's `__str__`. Lone surrogates raise `CBORError` because they cannot be
represented as valid CBOR UTF-8 text; they are never silently replaced.

### Numeric compatibility target

Floating-point reduction follows
[draft-mcnally-deterministic-cbor-18 §2.5](https://www.ietf.org/archive/id/draft-mcnally-deterministic-cbor-18.html#section-2.5).
For example, `-float(2**64)` stays a float (`fadf800000`), while an explicit
Python integer `-(2**64)` keeps its integer encoding (`3bffffffffffffffff`).
Float values below `-2**63` are preserved through decoding, diagnostics, and
map-key serialization as well as encoding.

For compatibility, explicit integers retain the documented full CBOR range
`[-2**64, 2**64-1]`. The draft's Appendix A rejects some large negative integer
encodings without an equally explicit prohibition in its normative integer
rules. This binding preserves its existing integer API while that ambiguity
remains; it does not claim strict agreement with those Appendix A rejection
vectors. `CBORMap` can preserve a large negative integer and the numerically
equal, separately encoded float as distinct keys.

### Errors

Malformed or non-canonical dCBOR raises `dcbor.CBORError` (a subclass of
`Exception`) on `loads()`/`diagnostic()`/`validate()`. Values that can't be
represented in dCBOR (unsupported Python types, out-of-range integers) raise
`dcbor.CBORError` from `dumps()`.

### Known limitations

- **Map representation.** Arrays, maps, and mutable tags can be keys in
  `CBORMap`, which preserves their encoded identity without Python hashing.
- **NFC string collisions.** dCBOR text strings are normalized to Unicode
  NFC before encoding. Two distinct Python strings that normalize to the
  same NFC form (e.g. `"é"` composed vs. `"e"` + combining acute) encode
  identically, so as dict keys the later one silently overwrites the
  earlier one — the same behavior the underlying Rust crate has.
- **Nesting depth is capped at 512 levels** (arrays/maps/tags, on both
  `dumps()` and `loads()`) to prevent stack-exhaustion crashes on
  adversarial input; deeper structures raise `CBORError` rather than
  crashing the process.
- **Encoded map-key storage is capped at 16 MiB in aggregate.** Keys nested
  inside other keys count at every level, matching the upstream decoder's
  cached copies. Inputs exceeding this budget raise `CBORError` before
  recursive decoding. Encoding reserves the same budget during conversion,
  before caching keys or descending into their values, across nested maps
  and repeated shared objects. Text is normalized before accounting so the
  budget includes its canonical UTF-8 bytes and encoded length headers.
  This bounds key-cache amplification, not
  total input size or all process memory.
- **Datetime precision.** Fractional epoch timestamps use floating-point
  seconds. Microseconds far from the Unix epoch may lose precision, and
  decoded timestamps are limited to Python's datetime resolution and range.
- **Interpreter coverage.** CI targets regular CPython 3.9–3.14. Free-threaded
  CPython and alternative interpreters are not currently in the build matrix.
  Local verification has used CPython 3.14; cross-platform results are reported
  by GitHub Actions.

## Development

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install maturin pytest
maturin develop
pytest
```

## CI and releases

The [GitHub Actions workflow](.github/workflows/ci.yml) runs on pull requests,
pushes to `master`/`main`, `v*` tags, and manual dispatches. Its stages are:

1. Check that Python and Cargo package versions agree. On tags, also require
   an exact `vX.Y.Z` match before starting builds.
2. Build the extension and run the full test suite on CPython 3.9–3.14.
3. Create an sdist and verify it installs and passes tests.
4. Build release wheels **from that sdist**, then install and test every wheel
   in an isolated environment using [cibuildwheel](https://cibuildwheel.pypa.io/).
5. Check distribution metadata, require all 42 wheels, and generate `SHA256SUMS`.
6. For version-tag pushes, publish a GitHub Release containing the tested wheels,
   source archive, and checksums. Ordinary CI runs retain downloadable artifacts.

| Platform | Architecture | Build environment | Python versions |
| --- | --- | --- | --- |
| Linux glibc 2.28+ | x86_64, aarch64 | manylinux_2_28 Docker images | 3.9–3.14 |
| Linux musl 1.2+ | x86_64, aarch64 | musllinux_1_2 Docker images | 3.9–3.14 |
| macOS 11+ | Intel, Apple Silicon | Native GitHub macOS runner images | 3.9–3.14 |
| Windows | x64 | Windows 2022 runner image with MSVC | 3.9–3.14 |

ARM builds run on native ARM runners. Linux packaging images are selected by
cibuildwheel; macOS and Windows use native runner images because their toolchains
require those operating systems. Rust is pinned to 1.90.0 in the workflow and Linux
container setup. Update both together. Dependabot checks action updates weekly.
Compiler jobs are limited to two, and at most three wheel jobs run concurrently.

The patched `crates/dcbor` sources and license must be committed with the project.
Do not replace them with the unpatched registry crate. The sdist includes this
dependency and the Python tests so packaging failures are caught before release.

To release, update `version` in both `pyproject.toml` and `Cargo.toml`, refresh
`Cargo.lock` with `cargo check`, commit and push the tested changes, then push
the matching tag:

```sh
git tag v0.1.0
git push origin v0.1.0
```

The release job uses GitHub's built-in `GITHUB_TOKEN` with `contents: write`;
no personal token or PyPI credentials are needed. Releases are published to
GitHub Releases. PyPI publication is not configured. Release tags support stable
versions only; an existing release causes publication to fail instead of
overwriting its assets. To retry after publication succeeded, manage that release
explicitly rather than rerunning its publishing step.

For a lightweight local check on an 8 GB machine:

```sh
CARGO_BUILD_JOBS=2 maturin develop --release --locked
python -m pytest -q
maturin sdist --out dist
```

Leave the full platform matrix to Actions. The final `release-bundle` artifact
is retained for 30 days, with individual build artifacts retained for 14 days.

## License

BSD-2-Clause-Patent, matching the upstream `dcbor` Rust crate.
