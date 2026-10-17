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

The owner will provide a DevOps-agent handoff and decommission that agent. Read
it when received and take ownership of its outstanding work. It has not yet
arrived. No remote push, release, or deployment was performed for this review.

Continue delegating independent work with explicit file ownership. The current
session supports eight workers plus the PM. Prefer Luna xhigh workers and Sol
xhigh for critical independent review; model overrides need fresh task context.
