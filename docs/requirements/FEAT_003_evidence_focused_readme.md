# FEAT_003: Evidence-focused README for human readers

**Status:** Proposed; research and presentation requirements documented,
implementation not started.

## Problem

The README explains the API and important edge cases in detail, but a person
evaluating the package has to read a substantial amount before they can answer
basic questions:

- Is the implementation meaningfully tested against its stated format profile?
- What does it do well, and how does its performance compare with alternatives?
- How much space do representative encodings use compared with JSON?
- Are the performance and size claims reproducible and relevant to my workload?

Humans often scan for clear claims, numbers, and visual summaries before reading
implementation detail. Unsupported marketing claims would undermine trust, so
every prominent claim needs evidence, scope, and a way to inspect the method.

## Desired outcome

Make the top-level README concise and persuasive to both scanning and careful
readers. Show a small set of meaningful, measured claims with visual graphs
where they improve comprehension, and link to detailed methodology and raw
results. Keep the complete API reference and important caveats available below
the summary or in linked documentation.

## Proposed README presentation

Add a short, scannable section near the introduction with:

1. **What this is:** Python bindings for deterministic CBOR/dCBOR, a brief
   feature statement, install command, and a minimal useful example.
2. **Evidence at a glance:** concise claims such as supported Python versions,
   tested platforms, independent conformance coverage, and the latest
   benchmark environment/date. Claims must link to their sources and must not
   say “fully compliant” or imply certification beyond the tested profile.
3. **Visual results:** a small number of readable charts for encoded size and
   operation latency, plus explicit test conditions and a link to the complete
   results/methodology.
4. **Limitations and details:** keep material compatibility behaviors,
   constraints, and API reference accessible without crowding the first screen.

Use chart alt text and nearby text/table summaries so the README remains
understandable without images and in screen readers. Prefer committed,
versioned SVG/PNG assets or GitHub-renderable Mermaid where appropriate; do not
depend on temporary benchmark outputs or external chart hosting.

## Evidence and benchmark requirements

### Meaningful testing and specification claims

- Describe the exact target precisely: RFC 8949 deterministic encoding as
  applied through the documented dCBOR profile and the specific draft/profile
  revision actually used by the tests.
- Distinguish test evidence from formal certification. Prefer statements such
  as “independent wire-vector tests cover …” and “CI tests CPython … on …”
  over an unqualified “spec compliant.”
- Summarize meaningful coverage categories: canonical numeric forms and
  independent numeric oracles, malformed/noncanonical input rejection,
  Unicode NFC, canonical map ordering and duplicate keys, recursion/depth and
  resource limits, date/key identity, and cross-platform packaged-wheel tests.
- Link to the test suite, CI workflow, patch/provenance notes, and any known
  profile ambiguity or explicit compatibility exception.
- Derive counts and supported-platform statements from tests/workflow data;
  avoid static counts that silently become stale. If deriving them
  automatically is not practical, document the update point and validate the
  displayed values during review.

### Encoded-size comparison

- Compare compact UTF-8 JSON output with canonical dCBOR wire bytes for the
  same documented logical fixtures. State whether JSON whitespace is removed
  and how Unicode and escaping are handled.
- Include diverse representative workloads, not only values selected to make
  one format look favorable: small records, nested arrays/objects, repeated
  strings, numeric-heavy data, and larger collections.
- Report absolute byte sizes and preferably percentage difference, with clear
  labels and units. Include fixture names and definitions in the linked
  data/methodology.
- Explain semantic mismatches: ordinary JSON cannot represent all CBOR
  values, including byte strings, arbitrary map-key types, tags, NaN/infinity,
  and distinct integer/float encodings. Compare only equivalent representable
  values for the JSON chart, and identify exclusions.
- Distinguish serialized payload size from in-memory process footprint. A
  wire-size chart must not be presented as resident memory usage.

### Latency and throughput comparisons

- Compare end-to-end encode, decode, and where useful validation operations;
  include round-trip latency only as a separately labeled derived operation.
- Use semantically equivalent fixture values across libraries and clearly
  describe conversions, strictness modes, and unsupported values.
- Candidate comparisons may include this package, other maintained Python
  CBOR/dCBOR implementations, the Python standard-library `json` module, and
  database JSONB only as a separately designed storage/database comparison.
  JSONB is not a drop-in Python codec comparator; do not combine database
  query/serialization time with in-process codec time or label database
  storage size as JSON wire size.
- Pin and report library/runtime versions, CPU/OS, interpreter, build mode,
  benchmark command, input fixture hash, warm-up, repetition count, and
  aggregation method. Compare release builds and avoid comparing debug and
  optimized builds.
- Prefer repeated independent runs and median plus a dispersion measure.
  Include error bars or ranges where they aid interpretation. Do not present
  tiny, noisy differences as wins.
- Publish raw machine-readable results and chart-generation instructions so
  graphs can be regenerated and reviewed. Keep benchmark runs out of ordinary
  pull requests if they add material cost; refresh on releases or a deliberate
  benchmark schedule.
- Describe each benchmark as workload-specific. Do not imply universal
  superiority from a small fixture suite.

### Memory metrics

- If reporting encoded payload bytes, call it payload/wire size.
- If reporting Python allocations, state the metric and limitations (for
  example, `tracemalloc` does not see Rust native allocations and peak bytes do
  not count cumulative short-lived allocation).
- If making a process-memory claim, select and document a suitable measurement
  such as peak RSS or a native heap profiler, isolate runs, and avoid treating
  allocator-retained memory as live object memory.
- Do not add a “memory footprint” chart until the measurement corresponds to
  the claimed resource. A separate encoded-size graph is useful even when
  trustworthy native-memory measurements are not yet available.

## Acceptance criteria

- The README's opening section lets a human quickly identify the library,
  install it, try a minimal example, and find meaningful test/performance
  evidence without reading the full API narrative.
- Prominent specification claims state the exact tested target and link to
  independent evidence; no wording implies external certification or broader
  conformance than verified.
- A compact CI/test summary identifies tested interpreter/platform scope and
  meaningful coverage categories, with a discoverable link to details.
- At least one visual encoded-size comparison uses equivalent, documented
  fixtures and clearly distinguishes wire bytes from memory usage.
- At least one latency visualization compares comparable operations and
  workloads across explicitly versioned implementations, or the README
  clearly states that cross-library results are not yet available instead of
  implying a comparison.
- JSONB, if included, is presented as a separately scoped database/storage
  experiment with its own methodology, not as a drop-in codec result.
- Graphs have accessible text alternatives and nearby numeric summaries.
- Raw results, environment, commands, fixture definitions, and chart generation
  are documented and versioned; readers can reproduce the charts.
- No performance, size, test-count, or compliance claim is published without
  evidence, measurement scope, and update provenance.
- The existing detailed API semantics and caveats remain available, either in
  the README's lower sections or in linked documentation.

## Non-goals

- Changing codec behavior or claiming certification.
- Selecting benchmark competitors or workloads to maximize dcbor's apparent
  advantage.
- Claiming in-memory savings from encoded payload size.
- Treating JSONB as directly interchangeable with a Python CBOR encoder.
- Removing important API details, edge cases, or limitations to make the
  README shorter.
- Running benchmarks on every pull request regardless of cost.

## Existing project assets and starting points

- [`README.md`](../../README.md) contains the current API and compatibility
  explanation, CI scope, and release process; this proposal is about
  prioritization and presentation, not deleting useful details blindly.
- [`tests/test_spec_conformance.py`](../../tests/test_spec_conformance.py)
  explicitly uses literal wire inputs and independent expected values rather
  than relying only on round trips. It covers numeric forms, malformed and
  noncanonical inputs, NFC, ordering, and duplicate keys.
- [`tests/test_numeric_oracle.py`](../../tests/test_numeric_oracle.py) provides
  independent numeric-oracle coverage.
- [`benchmarks/perf_review.py`](../../benchmarks/perf_review.py) has bounded
  end-to-end workloads and records extension hash, Python/platform metadata,
  encoded size, and operation timings. It currently benchmarks dcbor rather
  than competitors.
- [`benchmarks/allocation_review.py`](../../benchmarks/allocation_review.py)
  reports timing and Python `tracemalloc` data, explicitly noting that it does
  not measure Rust native heap or cumulative short-lived allocations.
- [`docs/allocation-plan.md`](../allocation-plan.md) documents what existing
  memory measurements do and do not establish.
- The current
  [CI workflow](../../.github/workflows/ci.yml) runs Python interpreter tests,
  vendored Rust codec tests, sdist validation, and platform wheel tests. Use
  the live workflow as the source for the displayed matrix.
