# CBOR codec and format landscape

As of 2026-10-18. This is a source-based landscape, not a ranking. Version and project claims below come from official project repositories, project documentation, or package registries. An implementation appearing in the dCBOR draft's status section is not IETF verification: the draft says that list is unverified and non-exhaustive, and the document remains an Internet-Draft.

## dCBOR-specific implementations

dCBOR is a narrowing profile of CBOR. It requires definite-length items, preferred serialization, bytewise-lexicographic map-key order, duplicate-key rejection, numeric reduction (for example, `2.0` becomes integer `2`), a single NaN form, restricted simple values, and NFC text. A codec offering a generic “canonical” or “deterministic” option does not thereby implement dCBOR. See [draft-18, sections 2 and 4](https://datatracker.ietf.org/doc/html/draft-mcnally-deterministic-cbor-18) and the [Blockchain Commons dCBOR overview](https://developer.blockchaincommons.com/dcbor/).

| Implementation | Language and scope | Activity/version evidence | Notes |
| --- | --- | --- | --- |
| [bc-dcbor-rust](https://github.com/BlockchainCommons/bc-dcbor-rust) | Rust; single-purpose profile codec | README documents `dcbor = "0.25.2"` and a 2026-03-16 release entry | Explicitly describes dCBOR encode and decode validation. It is a profile-specific reference point, so its supported value domain differs from a general CBOR codec. |
| [BCSwiftDCBOR](https://github.com/BlockchainCommons/BCSwiftDCBOR) | Swift; first-party profile codec | Repository labels it Alpha; its [visible commit history](https://github.com/BlockchainCommons/BCSwiftDCBOR/commits/master/) shows last activity in 2024, and GitHub lists no releases | Single-purpose dCBOR implementation, not a generic CBOR alternative. The draft's coverage statement is not a current stability or release-status claim. |
| [bc-dcbor-ts](https://github.com/BlockchainCommons/bc-dcbor-ts) | TypeScript; first-party profile codec | Repository reports `1.0.0-beta.3` (2026-09-14) and Beta status | Repository says it rejects CBOR features excluded by dCBOR. Beta status and the typed-decode API's own beta marking are relevant caveats. |
| [bcts](https://github.com/paritytech/bcts) | TypeScript; Parity Technologies port of Blockchain Commons implementations | Repository identifies its dCBOR package and describes it as a TypeScript port | A separate port from the first-party `bc-dcbor-ts`; the draft lists the first-party project, not this port. Treat as a candidate for interoperability checks, not as a draft-verified implementation. |
| [cbor-dcbor](https://github.com/cabo/cbor-dcbor) | Ruby; proof-of-concept composition | Draft-18 describes it as using `cbor-diag` for CBOR I/O and `cbor-deterministic` for ordering | The draft specifically says dCBOR exclusion checking is not implemented. Do not treat it as a strict validating decoder. |

Draft-18 calls the Rust, Swift, and first-party TypeScript implementations complete, but explicitly warns that its implementation list is unverified and non-exhaustive. Separately, the current [Swift repository README](https://github.com/BlockchainCommons/BCSwiftDCBOR) labels BCSwiftDCBOR Alpha; its [visible commit history](https://github.com/BlockchainCommons/BCSwiftDCBOR/commits/master/) shows last activity in 2024, and [GitHub lists no releases](https://github.com/BlockchainCommons/BCSwiftDCBOR/releases). The [TypeScript repository README](https://github.com/BlockchainCommons/bc-dcbor-ts) reports beta.3 dated 2026-09-14. The draft also records the Ruby exclusion-check gap. The [official implementation index](https://developer.blockchaincommons.com/dcbor/) lists the Rust, Swift, first-party TypeScript, and Ruby projects; its contributor field identifies Leonardo Custodio (Parity) for TypeScript. The separate [Parity repository](https://github.com/paritytech/bcts) describes a broader port. No other or third-party Python dCBOR codec is identified in the sources reviewed.

## Generic CBOR library alternatives

These codecs target general CBOR. Their canonical or deterministic options should be described by their exact ordering and numeric rules; they are not dCBOR-conformance claims.

| Library | Language and API | Version/activity evidence | Encoding options and tradeoffs |
| --- | --- | --- | --- |
| [cbor2](https://github.com/agronholm/cbor2) | Python; `dumps` / `loads` | 6.1.5, released 2026-10-01; Python >=3.10 (PyPy 3.11+) | Has [`canonical=True`](https://cbor2.readthedocs.io/en/stable/api.html#cbor2.dumps), plus options for value sharing, string references, and indefinite containers. Its documented sortable-key order is encoded-length-first, then bytewise, corresponding to legacy canonical order ([RFC 8949 §4.2.3](https://www.rfc-editor.org/rfc/rfc8949.html#section-4.2.3)), not core deterministic bytewise order ([§4.2.1](https://www.rfc-editor.org/rfc/rfc8949.html#section-4.2.1)) or dCBOR. Current project README says its implementation is Rust-based. |
| [cborx](https://pypi.org/project/cborx/) | Python; `dumps` / `loads` | 0.2.5, released 2026-09-24; classified Beta; Python >=3.10 | PyPI describes a pure-Python fallback and optional Cython accelerator for CPython wheels. Its documentation says `canonical=True` uses shortest integers/floats and bytewise ordering of encoded keys. Pin and report the backend; the option is not a dCBOR-conformance claim. |
| [cbor2pure](https://github.com/cffls/cbor2pure) | Python; pure-Python cbor2 fork | 5.8.0, released 2026-02-28; Python >=3.9 | Useful as a pure-Python runtime baseline. It is a fork in the cbor2 family and tracks an older version, so it is not an independent codec design or a same-version backend comparison with cbor2 6.x. |
| [ciborium](https://github.com/enarx/ciborium) | Rust; serde, reader/writer API, dynamic `Value` | 0.2.2 in current docs | Always uses the smallest lossless numeric encoding, per its README. `CanonicalValue` uses length-first then bytewise map-key order (RFC 7049 §3.9 / RFC 8949 §4.2.3), distinct from RFC 8949 §4.2.1 bytewise ordering and from dCBOR. |
| [cbor4ii](https://github.com/quininer/cbor4ii) | Rust; core API and optional serde support | Current docs.rs version 1.2.3 | Core documents RFC 8949 compatibility while omitting some extensions, including datetime and bignum. Its serde model encodes unit as an empty array; this can change wire shape relative to other serde codecs. It also offers zero-copy deserialization. |
| [minicbor](https://github.com/twittner/minicbor) | Rust; type-directed `Encode` / `Decode`, derive; serde support is separate | Current docs.rs version 2.3.0 | Small `no_std`-capable codec with `CborLen`. Its type-directed API and derives may encode application-specific arrays/maps; compare an explicitly matched wire model rather than assuming serde-equivalent output. |

Versions are point-in-time evidence and should be pinned in any measurement. `cbor2pure` remains a pure-Python reference, not an independent codec design; `cbor` 1.0.0 is an older RFC 7049-era package and is omitted from the maintained shortlist. `msgspec-cbor` is a wrapper around `cbor2`, not an independent CBOR codec.

## Python comparators in the reports

The expanded wire-size and latency reports measure these additional formats
and modes on the same eight JSON-compatible fixtures. This table describes
the measured calls, not a format or performance ranking.

| Library | Measured modes | Scope and caveat |
| --- | --- | --- |
| [orjson](https://github.com/ijl/orjson) | Default JSON output; `OPT_SORT_KEYS` JSON output | The option sorts dictionary keys for stable output; it is a JSON serialization option, not a CBOR canonicalization rule. The library serializes NaN and infinities as `null`; the shared fixtures contain finite floats. |
| [msgspec](https://msgspec.dev/usage) | MessagePack default; `order="deterministic"` | The report uses preconstructed `msgspec.msgpack.Encoder` / `Decoder` wrappers and untyped decoding to built-in Python values. It does not measure typed `Struct` decoding or schema-based array encoding. |
| [cbrrr / dag-cbrrr](https://github.com/DavidBuchanan314/dag-cbrrr) | `encode_dag_cbor` / strict `decode_dag_cbor` | A Python binding for strict DAG-CBOR, not dCBOR. The format requires string map keys, minimal integers and lengths, binary64 floats, and tag 42 only. The [DAG-CBOR specification](https://ipld.io/specs/codecs/dag-cbor/spec/) excludes non-finite floats and negative zero; the measured `cbrrr==1.1.0` API rejects NaN/infinities but accepts and emits negative zero. |

These modes answer different questions. `orjson` measures a JSON library and
its sorted-key option. MessagePack is a separate binary format; deterministic
ordering does not define dCBOR semantics. DAG-CBOR is a distinct restricted
CBOR profile. dCBOR's accepted domain and normalization rules differ from
generic CBOR and DAG-CBOR, so the reports use a common finite JSON-compatible
fixture set rather than imply interchangeability. For exact pins and call
details, see the [wire-size](../benchmarks/wire_size/README.md) and
[latency](../benchmarks/latency/README.md) methods.

## CBOR format-level alternatives

Format comparisons answer a different question from codec comparisons. CBOR is a schema-free binary data model with byte strings, semantic tags, and maps whose keys can be any CBOR data item ([RFC 8949](https://www.rfc-editor.org/rfc/rfc8949.html)). The table groups other formats by the distinctions their official specifications make; it is not a ranking, and the rows are not drop-in CBOR codec alternatives.

| Format | Model and schema expectations | Determinism and access semantics | Fit and tradeoffs relative to CBOR |
| --- | --- | --- | --- |
| [JSON](https://www.rfc-editor.org/rfc/rfc8259.html) | Text format; strings, numbers, booleans, null, arrays, and objects whose names are strings | RFC 8259 does not define canonical bytes. The separate [JCS profile (RFC 8785)](https://www.rfc-editor.org/rfc/rfc8785.html) specifies invariant JSON serialization for I-JSON data, including deterministic property sorting. | A familiar text interchange option for JSON-shaped data. Its standard data model has no native byte-string or tag type, and its objects are string-name/value collections. |
| [MessagePack](https://github.com/msgpack/msgpack/blob/master/spec.md) | Schema-free binary object serialization; integers, floats, strings, binary values, arrays, maps, and extension values | The specification says serializers should choose the smallest available representation, but does not define a universal canonical byte order. It describes application profiles that may sort map keys for determinism; profiles must also address other representational choices. | A close schema-free binary alternative for common object-shaped values. Extensions provide application-defined typing; they are not automatically equivalent to CBOR's tag handling or any chosen deterministic profile. |
| [Amazon Ion](https://amazon-ion.github.io/ion-docs/docs/spec.html) | Schema-free, self-describing hierarchical data; interchangeable text and binary representations | Ion structs are unordered, and implementations may reorder fields. The separate [Ion Hash specification](https://amazon-ion.github.io/ion-hash/docs/spec.html) defines hashing semantics for values; that is not a general canonical-byte promise for Ion serialization. | Relevant when a rich type system, typed nulls/annotations, or readable text and binary interchange matter. It includes types such as arbitrary-precision integers, decimal, timestamp, symbols, blobs, and clobs; struct field order is not semantic. |
| [BSON](https://bsonspec.org/spec.html) | Binary documents made from ordered key/value pairs, with a defined set of value types | The BSON specification describes the byte grammar and ordered document elements, but the cited documentation makes no general canonical-byte promise. | A document-oriented, JSON-like model. It differs from CBOR's arbitrary-item map keys and general semantic-tag model. |
| [Protocol Buffers](https://protobuf.dev/programming-guides/encoding/) | Schema-led messages defined in `.proto`; field numbers and wire types appear on the wire, while field names/types require the message definition | Default serialization order is not deterministic. Protobuf documentation further states that deterministic serialization is not canonical or stable across schema, application, build, or library changes. | Suited to applications that define message structures and evolve them with schema-aware code. The schema is needed to interpret fields, so comparisons with schema-free data models represent different workflows. |
| [Apache Avro](https://avro.apache.org/docs/1.12.0/specification/) | Schema-led binary encoding; encoded values omit field names and type information, so readers need the writer schema (and may use a reader schema for resolution) | Avro's Parsing Canonical Form normalizes schemas, not datum bytes. Binary record fields are serialized in schema declaration order; map data order is not a canonical-byte contract. | Suited to schema-managed records and data pipelines. Schema resolution is part of decoding; comparisons should account consistently for schema lookup and use an explicit mapping from the application model. |
| [FlatBuffers](https://flatbuffers.dev/schema/) | Schema-led buffers with generated accessors; a schema is normally needed to interpret the buffer | The [tutorial's buffer-access model](https://flatbuffers.dev/tutorial/) reads fields directly from the serialized buffer through generated accessors. The cited docs make no general canonical-byte promise. | A fit where applications want typed generated APIs and direct access to serialized buffers without first unpacking to another object representation. This access model differs from generic CBOR decoding. |

In this grouping, MessagePack and Amazon Ion are schema-free binary alternatives by their stated generic data models; JSON is also schema-free but text-based. Protocol Buffers, Avro, and FlatBuffers are schema-led alternatives. BSON is document-oriented with a fixed document/value grammar. These distinctions help select a workload and representation; they do not support a universal conclusion about encoded size or latency.

## Database storage competitor: PostgreSQL `jsonb`

[PostgreSQL `jsonb`](https://www.postgresql.org/docs/current/datatype-json.html) competes when an application needs to store and query JSON-shaped data inside PostgreSQL. It parses input into a decomposed binary representation and supports JSON operators and indexing; PostgreSQL documents higher input conversion cost than its textual `json` type, with faster processing because queries do not need to reparse the original text. `jsonb` drops insignificant whitespace and object-key order, and when duplicate object keys are supplied it keeps only the last value. Its object keys remain JSON strings, and its JSON data model does not supply CBOR byte strings or semantic tags. JSON numbers map to PostgreSQL `numeric`, so `jsonb` rejects values outside that type's range.

This is a database feature comparison, not a wire-format or in-process codec comparison. PostgreSQL's internal `jsonb` representation is not a stable cross-system wire format; PostgreSQL notes that binary representations for complex types may change across server versions ([protocol formats](https://www.postgresql.org/docs/current/protocol-overview.html#PROTOCOL-FORMATS)). A useful measurement would need a separate design that states PostgreSQL version, schema, indexes, transaction and durability settings, client protocol, insert/query workload, and whether reported size includes indexes and table overhead. Do not compare database storage size with the Python benchmark's encoded payload bytes or combine SQL execution time with codec latency.

The repository compares compact JSON and dCBOR bytes, generic CBOR modes,
`orjson` JSON, `msgspec` MessagePack, and strict DAG-CBOR. Separate reports
cover dCBOR profile workloads and Rust-core versus Python binding operations.
These reports measure one recorded host and fixture set; they do not measure
PostgreSQL storage or queries. See [benchmark status and scope](../benchmarks/README.md),
the [wire-size report](../benchmarks/wire_size/README.md), the
[latency report](../benchmarks/latency/README.md), the
[dCBOR profile](../benchmarks/profile/README.md), and
[Rust core](../benchmarks/rust_core/README.md).

## Benchmark interpretation

The tables above describe the competitive landscape, not a performance ranking. The repository's benchmark reports use identical JSON-compatible values and record emitted bytes, runtime, codec version, and backend. Future measurements should separate byte-returning APIs from writer/fixed-buffer paths and compare either both with deterministic options off or with specifically matched rules. Size differences can come from model choices such as byte strings versus integer arrays, maps versus structs encoded as arrays, or omitted fields versus explicit `null`; those are not automatically codec efficiency differences. Keep generic-CBOR and strict dCBOR workloads separate because dCBOR both narrows the accepted inputs and normalizes some values.
