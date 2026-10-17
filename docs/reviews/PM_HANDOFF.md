# PM handoff — 2026-10-17

Repository: https://github.com/WizzyGeek/pyo3dCBOR (confirmed by owner).

The review of baseline `36e0933` is addressed in the commit containing this
handoff. Six Luna xhigh workers implemented the changes, with an independent
Sol xhigh reviewer. No substantive finding remains open from that review.

## Decisions and completed work

- Call custom `__index__` once, then range-check its returned integer. Keep
  stored-int subclass behavior, the common i64 fast path, and existing fallback
  semantics for failing hooks. A stateful `2**63` callback has a literal-wire
  regression.
- The owner explicitly chose to preserve last-entry-wins for NFC-colliding
  Python dict keys. `CBORMap` constructors still reject canonical duplicates.
- Bound hazardous iterator tests on supported Linux systems and retain guarded
  finite regressions elsewhere. Strengthen encoding, depth, timezone, and cyclic
  tag tests; rename budget files by behavior and share safe subprocess setup.
- Ship `py.typed`, correct equality/unhashability stubs and project metadata.
  Exclude the unrelated vendored README/security review from source archives.
- Run the three exhaustive numeric sweeps on representative Python 3.14/Linux
  and source-package jobs; every wheel runs the remaining tests. Change-detection
  guards recognize the new typing, test-configuration, and vendor-patch inputs.
- Keep historical review logs in `docs/reviews/`; record allocation measurements
  and queued follow-ups in `docs/allocation-plan.md` without claiming unmeasured
  improvements. Mapping inheritance and broader tag repr remain deferred.
- Record WizzyGeek as vendor maintainer. `scripts/vendor_dcbor.py` verifies a
  checksum-pinned crates.io archive, upstream revision, and repeatable local patch
  over maintained source/test/build files. Clean-export verification passes.

## Verification

- Fresh release extension: **1,606 Python tests passed**.
- Vendored Rust codec: **182 tests passed**, including doctests.
- Independent installed-wheel test outside checkout: **1,603 passed**, three
  exhaustive cases deselected.
- Independent wheel rebuilt offline from extracted source archive: **1,606
  passed**, using that archive's tests from an external working directory.
- Independent integer/subclass/constructor/lookup boundary probes and final
  clean-export vendor checks passed. `git diff --check` passed.
- Type-checker executables were unavailable; stubs use standard typeshed hash
  annotations and were syntax checked. Native older-Python/macOS/Windows/ARM
  execution belongs to CI and has not been run locally.

## Pending work

The DevOps-agent handoff at `/tmp/dcbor-devops-agent-handoff.md` has now been
reviewed. Local verification and the hosted matrix were resumed from the current
`master` head. The current GitHub Actions run passed metadata/version guards,
the vendored Rust tests, all six Python-version jobs, the sdist, Linux x86_64
and ARM, and both macOS wheel jobs. The Windows wheel job failed because
cibuildwheel passed the single-quoted pytest marker literally, causing pytest
to treat `exhaustive'` as a path. The marker is now double-quoted in
`pyproject.toml`; the 1,603-test non-exhaustive command passes locally. Commit
and push the correction, then rerun the hosted matrix and confirm Windows plus
release-bundle validation pass before considering CI closed. Do not publish a
release as part of this follow-up.

Review fixes were committed as `6d218a9`, followed by the patch-whitespace and
CI-input guard correction in `b9ad3ed`. The full Python suite still passes
1,606 tests. No remote push, release, or deployment was performed.

Continue delegating independent work with explicit file ownership. The current
session supports eight workers plus the PM. Prefer Luna xhigh workers and Sol
xhigh for critical independent review; model overrides need fresh task context.

## Requirements

Feature proposals and bug reports live in
[`docs/requirements/`](../requirements/). Use `FEAT_NNN_short_title.md` for
features and `BUG_NNN_short_title.md` for bugs, assigning the next available
zero-padded number from one shared serial sequence across both types. The
directory README records the conventions and current items.
[`FEAT_001_ci_environment_speedups.md`](../requirements/FEAT_001_ci_environment_speedups.md)
captures the research request for CI environment setup, macOS/Windows speedups,
and sdist/wheel job parallelization. It is a proposal only; prioritize and
assign it before implementation.

[`FEAT_002_versioned_release_workflow.md`](../requirements/FEAT_002_versioned_release_workflow.md)
captures the requested automated version-bump and release-fulfillment flow:
produce commit-bound, version-identified bundles; on publication of a
non-draft GitHub Release, reuse a verified bundle or build and validate one
from the tag, then attach all 42 wheels, the sdist, and checksums. It proposes
preparing version bumps as reviewable PRs and highlights artifact retention
and the existing tag-push release job for PM/design review before
implementation.

[`FEAT_003_evidence_focused_readme.md`](../requirements/FEAT_003_evidence_focused_readme.md)
captures the request for a human-scannable README backed by meaningful
specification/test evidence, fair CBOR/dCBOR/JSON comparisons, and accessible
graphs for encoded size, latency, and only well-defined memory metrics. It is
a presentation and measurement proposal; benchmark evidence should be gathered
before publishing comparative claims.
