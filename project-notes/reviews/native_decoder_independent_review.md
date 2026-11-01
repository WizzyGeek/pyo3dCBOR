# Native decoder independent review

The borrowed-wire scanner and decoder were reviewed after the final clean
release build. The scanner checks bounded payload spans before decoding,
minimal integer and length heads, preferred floats (including canonical NaN),
NFC text, bytewise encoded map-key order, duplicate keys, depth 512, and the
16 MiB aggregate encoded-key budget. The direct decoder keeps the immutable
input `PyBytes` alive for map snapshots, creates owned Python bytes and text
from input spans, converts integers through PyO3's native integer path, and
uses no new per-object locks.

## Differential run

Both extensions ran under CPython 3.14.7. The release extension was loaded
from `/tmp/native-decoder-baseline/site`; the new extension was loaded from
`python/dcbor`. Their extension hashes were:

- Release baseline: `36502b893f69ae0c7bf8b159d53099b17c7ec02446c14b5d6a3555a6a278d581`
- Native decoder: `ca06f077c3ca1f2a72270b06d5799bc851a7612dec4728e6407839fe95aa1a94`

The deterministic generator used seed `0xDCB02026` to create 2,800 nested
values, encoded each with the release `dumps()`, and confirmed each wire with
release `validate()`. A further 7,594 small mutations used per-wire seeds
`0xBAD000 + index`: truncation at a random byte boundary, one random bit flip,
and an appended zero byte for each generated wire of at most 96 bytes, plus an
empty input. Both builds ran `loads()`, `diagnostic()`, `diagnostic_flat()`,
and `validate()` on all 10,394 wires.

All 2,800 generated wires were accepted by both builds. The run found no
acceptance differences and no successful-result differences. The mutations
also had identical acceptance results. They produced 388 error-text-only
differences across the four APIs (97 inputs, each rejected by both), caused
by differing invalid-input error precedence/details. For example, when a
mutated input contains both an invalid UTF-8 span and a later truncation, the
new full scan can report the UTF-8 error first. The validly framed invalid
UTF-8 vector `6180` matches the release message exactly. One mixed-error
reproducer from the mutation set is
`82184f830bf5a1696b302d3337303535378282c1184e680580440a95e45ba221c11a3ba29a00820002f5`:
the release reports `invalid or truncated CBOR data`; the new scan reports
`invalid UTF‑8 string: invalid utf-8 sequence of 1 bytes from index 1`.

A separate 35-wire comparison covered tag-1 date keys in direct, array, tag,
map, and nested shapes, including lossy year-1/year-9999 timestamps; invalid
dates in composite keys and ordinary map values; and snapshot dump identity.
It found no differences in errors, decoded values, or re-encoded wire bytes.
