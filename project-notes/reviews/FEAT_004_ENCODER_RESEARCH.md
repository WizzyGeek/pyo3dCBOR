# FEAT_004 direct encoder research

**Historical design note:** FEAT_004 is complete. This research informed the
accepted implementation; it is not a list of pending implementation work.
See the current [encoding architecture and PM acceptance record](../encoding.md).
Research snapshot: 2026-10-18. Development version `0.1.1` was bumped
separately before encoder implementation; this note makes no runtime changes.

## Findings

Before FEAT_004, `dumps()` constructed a full owned `dcbor::CBOR` tree before
serializing it. The tree was an implementation convenience; the accepted
direct output path avoids it for ordinary Python values, while maps still need
temporary encoded entries because output order depends on each final encoded
key.

There is structural evidence of repeated allocation/copying in that path:

- [`src/lib.rs`](../../src/lib.rs#L68) converts one Python object into `CBOR`;
  its dict branch at line 194 retains CBOR keys and values in a `BTreeMap`
  keyed by separately serialized key bytes. `dumps()` at line 274 then calls
  `py_to_cbor`, `to_cbor_data`, and wire preflight in sequence.
- The former vendored source at `crates/dcbor/src/cbor.rs:321` returned a
  fresh `Vec<u8>` from every recursive `to_cbor_data()` call. Arrays and tags
  extended their parent vector with child vectors. Text was normalized again
  at serialization time; ASCII already had a direct append fast path. This
  source was removed with FEAT_006.
- The former vendored `crates/dcbor/src/map.rs:123` stored each key's encoded
  bytes in a `BTreeMap`. `Map::insert()` at line 141 serialized each key to
  populate that cache. `Map::cbor_data()` at line 222 cloned cached key
  vectors, serialized every value to a new vector, collected all pairs, then
  appended them to a final vector. This source was removed with FEAT_006.
- [`src/encode.rs`](../../src/encode.rs#L1) and [`src/wire.rs`](../../src/wire.rs#L5)
  enforce a 16 MiB encoded map-key-cache limit, including recursively expanded
  nested key representations. This limit describes retained key caches, not
  arbitrary value bytes, final output size, or all temporary scratch space.

These are source-level allocation opportunities. They do not establish an
expected end-to-end speedup.

## Measurement limits

An earlier Rust/Python comparison used Rust values prepared before timing,
while Python `dcbor.dumps()` included conversion from Python values. That
whole-operation comparison cannot isolate FFI overhead or quantify the gain
from removing the tree. The [profile report](../../benchmarks/profile/README.md)
times the Python binding on 10/100/1,000/10,000-entry maps and float/Unicode
cases; it is useful for choosing workloads, not for assigning causality.
[`project-notes/reviews/PERF_REVIEW.md`](PERF_REVIEW.md) also labels earlier experiments
historical and warns that later key-budget/text-cache changes require fresh
measurement.

## Transferable implementation techniques

1. **One output buffer for ordinary items.** The official Python `cbor2` 6.x
   Rust extension has a recursive encoder writing to an internal `Vec`; its
   writer uses `push`/append operations rather than constructing a generic
   CBOR node for every value. Its canonical map path first encodes sortable
   keys, sorts entries, and then emits them. This is a useful direct-PyO3
   precedent, though its canonical mode uses encoded-length-first ordering and
   must not be copied for dCBOR's bytewise key order. Source:
   <https://github.com/agronholm/cbor2/blob/master/rust/encoder.rs>
   and ordering documentation:
   <https://github.com/agronholm/cbor2/blob/master/docs/versionhistory.rst>.

2. **Small fixed header writes.** The Rust `ldclabs/cbor2` changelog documents
   replacing runtime-sized scratch slices with a fixed-size array for each
   argument width in its low-level header encoder. The reported motivation is
   to let the writer use direct stores instead of a general copy. Its
   caller-buffer `to_slice` API is another relevant pattern, but it implements
   generic RFC 8949 CBOR rather than this project's dCBOR Python semantics.
   Source: <https://github.com/ldclabs/cbor2/blob/main/CHANGELOG.md> and
   <https://github.com/ldclabs/cbor2>.

3. **Reuse dCBOR rules.** Blockchain Commons defines bytewise map order, NFC,
   numeric reduction, shortest float widths, canonical NaN, and permitted
   simple values. Its tree serializer is not a direct-writer example; the
   vendored source remains the local behavior reference. Upstream:
   <https://github.com/BlockchainCommons/bc-dcbor-rust/blob/master/src/cbor.rs>,
   <https://github.com/BlockchainCommons/bc-dcbor-rust/blob/master/src/map.rs>,
   and profile overview:
   <https://github.com/BlockchainCommons/bc-dcbor-rust>.

`serde_ipld_dagcbor` is a `to_writer` example for restricted DAG-CBOR via
cbor4ii; `cbrrr` is this repo's native Python comparator, not a Rust writer
reference. See <https://github.com/ipld/serde_ipld_dagcbor>,
<https://github.com/DavidBuchanan314/dag-cbrrr>,
[`benchmarks/wire_size/README.md`](../../benchmarks/wire_size/README.md).

## Historical minimum viable architecture plan

Implement a per-call recursive `encode_into(py, object, sink, context)` for
scalars, arrays, tags, and datetime tag 1. Write into one reusable buffer and
reuse/factor existing dCBOR header and numeric rules to avoid semantic drift.

For each dict, stage key and value wire bytes in Python iteration order, once
each, until all keys are known. Keep entry offsets/lengths, resolve canonical
collisions, sort bytewise by encoded key, then append sorted spans. A monotonic
arena would retain bytes for replaced entries; use reclaimable per-entry buffers
or compact/rewind the staged region before encoding a replacement value, as the
current path drops replaced CBOR before converting that value. Add a
collision-heavy case. This stages wire bytes, not a generic CBOR tree, but
nested maps can still copy contents. A key-first pass could avoid staging values
but changes visible key/value callback order for stateful conversions.

Encode `CBORMap` from its frozen Rust `Map` snapshot (already in canonical
order). Do not round-trip its keys/values through `keys()`/`items()`: fresh
Python decoding can change representation and lose encoded key/tag identity.

Use borrowed Python string/byte views under the GIL and copy bodies directly to
the writer or map arena. ASCII is already NFC; normalize non-ASCII before key
sorting, reject surrogates, and avoid an extra normalized `String` when the
source is already NFC if an allocation-free check is available.

Preserve the current 16 MiB map-key-cache accounting with checked arithmetic
and recursive key context. Do not turn it into a general scratch/output cap.
Keep a specialized `CBORMap` path if changing its existing immutable Rust
snapshot representation would expand the feature beyond direct `dumps()`.

## Future sink-based output

A later file/socket API could reuse canonical scalar and header emitters over
`std::io::Write`, with the current `Vec<u8>` path as an adapter. This feature
still returns Python `bytes`; it does not stream or provide end-to-end
zero-copy output. Traversal would need to stage each dict entry until encoded
keys can be sorted, and stage callback-mutated list bodies until the final
visited count is known; the API must define short writes, I/O errors, and
partial-output behavior. Copy bytearray payloads into Rust-owned staging
before any Python writer callback or blocking I/O/GIL release; never retain a
raw bytearray slice across those boundaries.

## Compatibility guardrails

- Preserve conversion order and one-call `__index__`, datetime errors/ranges,
  depth 512, integer range, surrogate rejection, and booleans before integers.
- Preserve NFC-before-sort, bytewise map order, dict last-wins canonical
  collisions, and `CBORMap` duplicate rejection/snapshot identity.
- Preserve shortest integers/floats, integer-reducible floats, negative zero,
  canonical NaN, and permitted simple values.
- Preserve nested encoded-key budget semantics; compare exact bytes/errors
  against old `dumps()` before switching the public path.

## Historical suggested implementation phases and ownership

This archived phase list records the original proposal, not current work. The
feature is complete; see the [encoding record](../encoding.md) and the
[BUG_005 historical record](mixed_profile_decode_history.md).

1. **Requirements/spec owner:** freeze wire/rejection vectors for numeric
   boundaries, floats, NFC/surrogates, map order/collisions, depth and budgets.
2. **Rust codec owner:** factor append-to-buffer header, scalar, normalization
   and float helpers shared with the tree serializer where practical.
3. **Binding owner:** prototype scalar/list/tag writes, then map staging; retain
   old `dumps()` as parity oracle and ordered one-time conversions.
4. **Parity reviewer:** check bytes, errors, callbacks, budget behavior,
   collision-heavy maps, and frozen `CBORMap` identity separately.
5. **Benchmark owner:** pair current release build/binary fingerprints on
   scalars/lists, 10–10,000-key maps in three orders, nested/large byte values,
   and NFC/decomposed/expanding text. Report bytes and allocation evidence;
   measure speedup against the matched previous Python encoder; keep any
   non-matched prepared-tree observations separate from that comparison.

No source modifications, builds, tests, benchmark runs, installs, or commits
were made as part of this research.
