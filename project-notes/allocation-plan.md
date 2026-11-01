# Allocation follow-up plan

The allocation table is a **PRE-REBUILD installed-extension baseline**,
collected at source HEAD `36e0933` with imported extension SHA-256
`a753794ab7ff6366c8d11470829834eb7628759b74ccb0e86df2c37bc40603f8`. It does
not describe the final build or measure a speedup. This note also records
source behavior and queues the next allocation work. Those source observations
remain current: the later index fix did not change `validate()`,
`map_to_python()`, or `CBORMap.__iter__()`.

## Current behavior

- `validate()` in `src/lib.rs` runs the iterative wire preflight and then calls
  `CBOR::try_from_data`. That call builds the Rust `CBOR` tree; the tree is
  dropped when validation returns. It avoids creating Python containers, but
  it is not a tree-free validation path.
- `map_to_python()` in `src/python_types.rs` converts every key and value before
  checking whether the current key forces `CBORMap`. Once fallback is set, the
  converted values are dropped. This eager traversal also preserves decoder
  errors: an unsupported numeric tag-1 date in a later key or value still
  raises `CBORError`. `tests/test_scalars.py` and
  `tests/test_key_identity.py` cover these cases and date-key round trips.
- `CBORMap.__iter__()` calls `keys()` and returns that new list's iterator.
  Creating an iterator converts all keys to Python objects, even if the caller
  consumes only the first one. `keys()`, `values()`, and `items()` also return
  newly decoded lists by design.
- `CBORMap` is not a `collections.abc.Mapping`. Adding that base needs a
  deliberate equality decision: the ABC's default `__eq__` compares
  `dict(self.items())`, which collapses distinct canonical keys such as `1`
  and `True`. `CBORMap` currently has its own canonical-byte equality method;
  that override must remain in force. The type also supports unhashable array
  and map keys, and its `keys()`/`items()` methods return lists rather than
  mapping views. Keep the current API until equality and view semantics are
  deliberately specified.
- `CBORTag.__repr__()` in `src/python_types.rs` deliberately summarizes
  container values by type name to avoid recursive formatting. Expanding it is
  optional API work and has no demonstrated allocation benefit.

## Historical pre-rebuild installed-extension baseline

The PM collected these measurements before rebuilding the installed extension
for the index fix. The final installed extension has SHA-256
`0cf305e9b25f460a20cf87f6e6a4c6c8966d849ca404a45caed539f448239735`; it was
not measured for this table. These results therefore must not be read as
results for the final build or as a before/after speedup comparison.

The measurement command at the time was:

```sh
.venv/bin/python benchmarks/allocation_review.py \
  --output /tmp/allocation_review.json --rounds 9 --target-ms 25
```

The script used bounded defaults: a 16,384-integer array and a 1,024-entry
fallback map with one-item array keys and eight-integer list values. The
recorded environment was CPython 3.14.7 on Linux x86-64. Timings include the
Python call and destruction of each returned result; they are medians of nine
samples, with GC disabled only during timed loops.

| Operation | Input | Median time | Sample min–max | `tracemalloc` current / peak |
| --- | ---: | ---: | ---: | ---: |
| `validate()` on integer array | 48,875 wire bytes | 2,535.8 µs | 2,508.2–2,707.4 µs | 32 / 32 B |
| `loads()` on integer array | 48,875 wire bytes | 3,850.1 µs | 3,735.6–4,233.7 µs | 652,696 / 652,696 B |
| `loads()` on fallback map | 13,035 wire bytes; 1,024 entries | 4,304.9 µs | 4,261.6–4,432.2 µs | 304 / 480 B |
| `iter(mapping)` | same fallback map | 217.8 µs | 211.1–227.5 µs | 123,665 / 123,665 B |
| `next(iter(mapping))` | same fallback map | 212.8 µs | 211.3–217.0 µs | 7,921 / 123,665 B |

These are baselines only, with no candidate implementation for comparison. No
CPU affinity was set. A second nine-sample invocation put the validation
median at 2,887.9 µs and the integer-array `loads()` median at 4,213.2 µs, so
the small single-machine timing differences should not be treated as stable
performance estimates. The map
iteration measurements consistently show that requesting an iterator or its
first key reaches the full 123,665-byte Python-traced peak.

`tracemalloc` reports Python-managed memory only. It misses the Rust `CBOR`
tree, encoded-key cache, cloned Rust map storage, and allocator-retained native
memory. In addition, peak traced bytes measure the largest live Python
allocation set, not the cumulative number of short-lived objects. Thus the
480-byte peak for fallback-map `loads()` does not mean that only 480 bytes of
Python allocation work occurred: the loop creates and drops decoded keys and
values for all 1,024 entries. Do not present these figures as total allocation
or as evidence that a proposed change reduces total allocation. A Rust-side
allocator counter or a separate native heap profiler is needed for that claim.

## Prioritized follow-ups

1. **Avoid materializing discarded objects after fallback is known.** Add a
   conversion-validation traversal for the remainder of a map after an
   unhashable key or Python-equal canonical-key collision has selected
   `CBORMap`. It must still visit every descendant and preserve unsupported
   date errors, key-date round-trip checks, depth errors, and key identity.
   Keep the ordinary-dict path unchanged until a benchmark shows the fallback
   branch is worthwhile. Compare the 1,024-entry baseline above with candidate
   timings, Python peak and cumulative allocation evidence. This is the
   smallest focused implementation with a directly confirmed discarded-work
   path.
2. **Give `validate()` a validation-only Rust decode path.** Reuse the codec's
   parsing and validation rules while suppressing construction of the owned
   `CBOR` tree. The existing `wire::preflight` is not sufficient by itself: it
   checks structure, depth, and key-cache bounds but delegates full canonical
   checks such as UTF-8/NFC and map ordering to the decoder. Verify all current
   `validate()` rejection vectors and exact consumed-length behavior, then
   measure native peak/live allocation and time against the 48,875-byte
   baseline.
3. **Stream `CBORMap` iteration for callers who consume only part of a map.**
   Preserve canonical key order and keep `keys()`, `values()`, and `items()`
   returning fresh lists. A candidate iterator must retain the immutable map
   safely and avoid converting unvisited keys. Avoid an index implementation
   that repeatedly calls `.nth(index)` over the Rust map, which would make a
   full traversal quadratic. Measure iterator creation, first-key consumption,
   and full iteration before deciding whether the extra iterator machinery is
   worthwhile.
4. **Defer `Mapping` inheritance and broader tag representations.** Neither
   resolves the measured allocation paths. Revisit `Mapping` only with an
   explicit decision for encoded-key equality, unhashable keys, and view
   return types. Revisit `CBORTag` repr only for a separate user-facing API
   request.

No low-risk immediate source fix is justified by these measurements alone.
The confirmed savings require preserving eager date validation while changing
where conversion happens, and the Rust-tree estimate needs native allocation
instrumentation before making a total-memory promise.
