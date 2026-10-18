# FEAT_004 memory-access research

This note records bounded API research for the planned direct Python-to-dCBOR
writer. It does not change accepted values or prescribe an unsafe fast path.
The repository pins PyO3 0.29.2, builds per-interpreter wheels with
`extension-module` (no `abi3` feature), and targets regular CPython 3.9–3.14.

## Payload access matrix

| Value | Public PyO3 path | What the view represents | Copy and canonicalization boundary |
| --- | --- | --- | --- |
| `bytes` | `PyBytesMethods::as_bytes()` | Borrowed immutable payload bytes; the Python object remains the owner. | `Vec::extend_from_slice` copies payload once into the Rust wire buffer. Returning with current `PyBytes::new(py, &data)` copies the complete wire buffer again into Python-owned bytes. |
| `bytearray` | `to_vec()` is safe; `as_bytes()` is `unsafe`. | Mutable payload; the source must be protected against mutation during either copy. PyO3's `to_vec()` uses `with_critical_section` and returns an owned vector. | For current GIL-enabled wheels, a scoped `unsafe { as_bytes() }` plus immediate `wire.extend_from_slice()` can copy once into the Rust wire buffer when the caller proves no Python execution, mutation, or GIL release occurs. `to_vec()` then append uses two payload copies. Both paths still copy the full wire buffer into returned Python bytes. |
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

PyO3 0.29.2 implements safe `to_vec()` as `with_critical_section(self, ||
unsafe { self.as_bytes() }.to_vec())`. Its safety comments say the bound object
holds the GIL, the free-threaded build uses a critical section, and the copy
does not call back into Python or mutate the slice. Critical sections are a
no-op with the GIL and use a per-object lock in free-threaded Python. The
current release matrix targets regular CPython 3.9–3.14 only.

For that matrix, a direct writer may prefer one short caller-verified borrow:
hold the GIL, acquire `unsafe { bytearray.as_bytes() }`, and immediately copy
with `wire.extend_from_slice(slice)`. Keep the slice scope free of Python/PyO3
calls, callbacks or re-entry, mutation, and GIL release/detach. The copy is a
Rust slice operation; do not recurse or retain the view. This unsafe block is
a specific caller safety proof, not a blanket prohibition. If the proof cannot
hold, `to_vec()` provides an owned payload copy, with the extra append copy.
Callback-capable paths such as custom `__index__` and datetime
`utcoffset()`/`timestamp()` must stay outside the borrow scope. Both routes
still incur the final complete Rust-wire-to-Python-bytes copy.

The current Python API accepts bytes and bytearray as byte strings. Preserve
that boundary; do not broaden it to arbitrary buffer exporters as an encoder
optimization. Generic buffer consumers must interpret `itemsize`, `format`,
`shape`, `strides`, optional indirection, and release each acquired view.

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
- CPython 3.14 docs: [Unicode](https://docs.python.org/3.14/c-api/unicode.html), [stable ABI](https://docs.python.org/3.14/c-api/stable.html), [buffer protocol](https://docs.python.org/3.14/c-api/buffer.html), [critical-section API](https://docs.python.org/3.14/c-api/init.html#python-critical-section-api)
