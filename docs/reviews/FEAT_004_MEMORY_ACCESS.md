# FEAT_004 memory-access research

This note records bounded API research for the planned direct Python-to-dCBOR
writer. It does not change accepted values.
The repository pins PyO3 0.29.2, builds per-interpreter wheels with
`extension-module` (no `abi3` feature), and targets regular CPython 3.9–3.14.
Free-threaded builds are an optional CPython capability starting with 3.13.

## Payload access matrix

| Value | Public PyO3 path | What the view represents | Copy and canonicalization boundary |
| --- | --- | --- | --- |
| `bytes` | `PyBytesMethods::as_bytes()` | Borrowed immutable payload bytes; the Python object remains the owner. | `Vec::extend_from_slice` copies payload once into the Rust wire buffer. Returning with current `PyBytes::new(py, &data)` copies the complete wire buffer again into Python-owned bytes. |
| `bytearray` | `to_vec()` is safe; `as_bytes()` is `unsafe`. | Mutable payload; protect it against mutation during either copy. PyO3's `to_vec()` uses `with_critical_section` and returns an owned vector. | Under `with_critical_section`, a scoped `unsafe { as_bytes() }` plus immediate `wire.extend_from_slice()` copies once into the Rust wire buffer. `to_vec()` then append uses two payload copies. Both paths still copy the full wire buffer into returned Python bytes. |
| `str` | `PyStringMethods::to_str()` | Borrowed Rust UTF-8 view; PyO3 calls `PyUnicode_AsUTF8AndSize` in this full-API build. | CPython may create and cache UTF-8 on demand; this is not guaranteed allocation-free. dCBOR requires UTF-8 NFC, so normalize when needed, reject lone surrogates, then append normalized bytes. Final Python bytes construction copies the wire buffer. |
| `list` / `tuple` | `PyListMethods::iter()` / `PyTupleMethods::iter()` | Iteration yields references to Python objects. A CPython list’s contiguous storage is an array of object pointers, not inline integer/float payloads. | Visit and encode each value; there is no bulk payload copy. A direct writer can avoid intermediate CBOR nodes, but still traverses each object. |
| `bool`, `int`, `float`, `None` | PyO3 typed checks, `extract`, and `PyFloatMethods::value()` | Semantic Python value, not a wire-ready byte slice. | Integers may be arbitrary precision and are range-checked; floats are native `f64` and need dCBOR width/reduction rules. Encode canonical headers/payload bytes explicitly. |
| Other buffer exporters | Not currently accepted by `dumps()` dispatch. | Buffer layouts may be multidimensional, strided, formatted, or multi-byte. | Do not add `memoryview`, `array.array`, or other exporters implicitly. If separately approved, define format, contiguity, byte order, and lifetime semantics first. |

The Python object pointer identifies an object with interpreter metadata and
ownership rules; it is not a pointer to a portable, directly serializable
payload. Do not cast builtins to presumed `PyObject`/`PyListObject` layouts,
copy object headers, or reinterpret refcounts/type pointers as data. CPython
documents stable ABI guarantees separately from implementation layouts.

## Lifetimes and compatibility

`PyBytesMethods::as_bytes()` is safe because `bytes` is immutable and its
borrow is tied to the live PyO3 reference. `PyStringMethods::to_str()` returns
UTF-8 and errors on unpaired surrogates. PEP 393 permits 1-, 2-, or 4-byte
internal Unicode storage; CPython’s UTF-8 representation is created lazily and
cached. PyO3’s `unsafe PyStringMethods::data()` exposes storage-specific data
and documents a C-bitfield/target assumption; it is not justified for this
cross-platform wheel matrix without measured need and target validation.

The direct writer borrows ASCII/already-NFC text and charges transformed NFC
output before growing its normalized `String`. The locked
`unicode-normalization` iterator can buffer a long non-starter run before it
yields characters, so output-byte charging does not bound all normalization
scratch. The old `EncodeBudget::text` path has the same iterator behavior;
compare old and new peak memory on adversarial combining runs and do not claim
the 16 MiB key-cache policy limits every normalization allocation.

PyO3 0.29.2 implements safe `to_vec()` as `with_critical_section(self, ||
unsafe { self.as_bytes() }.to_vec())`. Use the same public
`pyo3::sync::critical_section::with_critical_section` API around a borrowed
`as_bytes()` view and its immediate copy into the Rust output buffer. The
caller must have an attached Python thread state; inside the closure, do only
the `as_bytes()` access and native copy, with no other Python/PyO3 calls,
callbacks or re-entry, mutation, GIL release, or detach, and do not retain the
view. The guard is a no-op in GIL-enabled builds and protects the bytearray
with a per-object critical section in free-threaded builds.
Free-threaded CPython is an optional build capability since 3.13, not a 3.15
version boundary. This unsafe block has a specific caller safety proof; if
that proof cannot hold, use `to_vec()`, which adds an owned intermediate
payload copy before appending. Callback-capable paths such as custom
`__index__` and datetime `utcoffset()`/`timestamp()` must stay outside the
borrow scope. Both routes still incur the final complete
Rust-wire-to-Python-bytes copy.

The current Python API accepts bytes and bytearray as byte strings. Preserve
that boundary; do not broaden it to arbitrary buffer exporters as an encoder
optimization. Generic buffer consumers must interpret `itemsize`, `format`,
`shape`, `strides`, optional indirection, and release each acquired view.

## Integer width and representation

CPython stores `int` magnitude as a contiguous array of base-2**15 or base-2**30
digits. `sys.int_info.bits_per_digit` reports bits per digit, so the digit base
is `2**sys.int_info.bits_per_digit`. For the explicit dCBOR interval
`[-2**64, 2**64 - 1]`, 30-bit builds can accept any
value with at most two digits, must inspect sign and magnitude for three
digits, and can reject four or more immediately. On 15-bit builds the
corresponding thresholds are at most four, five requiring inspection, and six
or more rejecting. The negative endpoint `-2**64` is valid even though its
absolute magnitude has bit length 65; `2**64` and `-2**64 - 1` are invalid.
Do not conflate this rule with float-to-integer reduction. The current encoder
uses PyO3 native `i64`/`i128` extraction followed by a Rust range check, so
actual integer values do not need Python rich comparisons. PyO3 0.29.2 has a
digit-count cutoff in one CPython 3.14, non-limited-API, 30-bit `i128` path,
but it is not a dCBOR-specific threshold. CPython's public `PyLong_Export` and
`PyLong_GetNativeLayout` APIs are available from 3.14; earlier versions expose
no equivalent public digit view. Treat a tighter count-based rejection as an
unmeasured optimization hypothesis, and do not read private integer layouts
or use private digit-count APIs across the 3.9–3.14 support range.

## Measurement boundary

Cache locality is a plausible benefit of removing the owned recursive CBOR
graph, not an established root cause. Python container traversal still visits
Python objects and may pointer-chase; the final Rust output is sequential, but
`PyBytes::new(py, &data)` currently makes another full-output copy. Do not
describe `extend_from_slice` as zero-copy for the API or as proof of a cache
miss reduction.

Compare matched end-to-end `dumps()` cases for large bytes/bytearray payloads,
ASCII and non-ASCII NFC text, non-NFC text, shallow scalar lists, nested lists,
repeated references versus distinct objects, and key-heavy maps. Include
working sets below and above relevant cache sizes where practical. Record
correct output hashes and error parity, Python nodes visited, Rust allocations
and peak/live native bytes, normalization bytes allocated, source payload
bytes copied into the Rust wire buffer, map-key staging bytes, final wire
length, and the final Python-bytes copy. `tracemalloc` alone omits Rust tree and
buffer allocations. Use CPU cache counters (for example cycles, instructions,
cache references, cache misses) on controlled Linux runs where available; keep
those counters separate from wall-time attribution. The existing prepared-tree
Rust-core benchmark remains a separate comparison.

## Primary references

PyO3 API declarations were checked against the locked crate source under
`pyo3-0.29.2/src/types/{bytes,bytearray,string}.rs`; `to_vec()` protection was
verified in `pyo3-0.29.2/src/types/bytearray.rs` and
`pyo3-0.29.2/src/sync/critical_section.rs`.

- PyO3 0.29.2 docs: [bytes](https://docs.rs/pyo3/0.29.2/pyo3/types/trait.PyBytesMethods.html), [bytearray](https://docs.rs/pyo3/0.29.2/pyo3/types/trait.PyByteArrayMethods.html), [strings](https://docs.rs/pyo3/0.29.2/pyo3/types/trait.PyStringMethods.html)
- PyO3 0.29.2 [critical-section API](https://docs.rs/pyo3/0.29.2/pyo3/sync/critical_section/index.html)
- CPython integer sources: [3.9 layout](https://github.com/python/cpython/blob/3.9/Include/longintrepr.h), [3.14 layout and export API](https://github.com/python/cpython/blob/3.14/Include/cpython/longintrepr.h), [`sys.int_info`](https://docs.python.org/3.14/library/sys.html#sys.int_info), [integer C API](https://docs.python.org/3.14/c-api/long.html)
- CPython 3.14 docs: [Unicode](https://docs.python.org/3.14/c-api/unicode.html), [stable ABI](https://docs.python.org/3.14/c-api/stable.html), [buffer protocol](https://docs.python.org/3.14/c-api/buffer.html), [critical-section API](https://docs.python.org/3.14/c-api/init.html#python-critical-section-api), [free-threaded Python](https://docs.python.org/3.14/howto/free-threading-python.html)
