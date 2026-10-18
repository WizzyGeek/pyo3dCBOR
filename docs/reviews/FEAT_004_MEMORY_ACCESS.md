# FEAT_004 memory-access research

This note records bounded API research for the planned direct Python-to-dCBOR
writer. It does not change accepted values or prescribe an unsafe fast path.
The repository pins PyO3 0.29.2, builds per-interpreter wheels with
`extension-module` (no `abi3` feature), and targets regular CPython 3.9–3.14.

## Payload access matrix

| Value | Public PyO3 path | What the view represents | Copy and canonicalization boundary |
| --- | --- | --- | --- |
| `bytes` | `PyBytesMethods::as_bytes()` | Borrowed immutable payload bytes; the Python object remains the owner. | `Vec::extend_from_slice` copies payload once into the Rust wire buffer. Returning with current `PyBytes::new(py, &data)` copies the complete wire buffer again into Python-owned bytes. |
| `bytearray` | `to_vec()` is safe; `as_bytes()` is `unsafe`. | Mutable payload; a borrowed pointer/slice can be invalidated by mutation or resize. | Safe `to_vec()` then append makes a temporary payload copy and a second copy into the Rust wire buffer; returning Python bytes copies the complete wire buffer again. Do not retain a borrow across Python execution. |
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

PyO3 marks bytearray `as_bytes()` unsafe because Python code can mutate or
resize the object and invalidate the view. A normal CPython GIL prevents other
threads from running Python concurrently, but does not prevent same-thread
re-entry through callbacks. The encoder already calls user `__index__` for
custom integer-like objects and calls datetime `utcoffset()` / `timestamp()`.
Any borrowed mutable payload must not span such calls, recursion, exception
handling that can run Python, or GIL release. This note does not recommend a
new unsafe buffer strategy; the safe high-level `to_vec()` path has the extra
copy described above.

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

PyO3 API details were cross-checked against the locked 0.29.2 crate sources in
`pyo3-0.29.2/src/types/{bytes,bytearray,string}.rs`; the links below use the
canonical generated Rustdoc path form.

- [PyO3 0.29.2 byte methods](https://docs.rs/pyo3/0.29.2/pyo3/types/trait.PyBytesMethods.html)
- [PyO3 0.29.2 bytearray methods](https://docs.rs/pyo3/0.29.2/pyo3/types/trait.PyByteArrayMethods.html)
- [PyO3 0.29.2 string methods](https://docs.rs/pyo3/0.29.2/pyo3/types/trait.PyStringMethods.html)
- [CPython Unicode C API](https://docs.python.org/3.14/c-api/unicode.html)
- [CPython stable ABI](https://docs.python.org/3.14/c-api/stable.html)
- [CPython buffer protocol](https://docs.python.org/3.14/c-api/buffer.html)
