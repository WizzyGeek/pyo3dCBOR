# FEAT_001 Linux image trial — 2026-10-18

## Result

[Run 39060344953](https://github.com/WizzyGeek/pyo3dCBOR/actions/runs/39060344953)
passed on commit `e3135737312c7f57bc9375482c6538c37670f42b`, branch
`ci/feat001-linux-images`, dispatched with `linux_images=maintained`.
There were 41 successful jobs and one intentionally skipped release job.
The final validator reported: **42 wheels and one sdist; wrote SHA256SUMS**.
All six CPython versions, vendored Rust tests, source-package tests, both
Linux architectures/libc families, Windows x64, and both macOS architectures
passed. No release was published and no default-image promotion was made.

All 12 Linux wheel jobs pulled and validated the recorded registry digests.
Their cibuildwheel logs show `before_all: bash
{project}/containers/linux/validate-image.sh`, with runtime validation of both
libc variants and no Rust installation. The pins and provenance are in
[`images.json`](../containers/linux/images.json).

This validates consumption of the existing published images. The newly
hardened publisher and checksum-pinned Dockerfiles were statically checked,
but this trial did not rebuild or publish new images. New publisher output
will need its own runtime validation and digest review before replacing pins.

## Timing method

Times come from the run/jobs API and completed job logs. Job-to-first-build
starts at the job's `startedAt` and ends at the first timestamped
`Building cp…-manylinux_… wheel` line. This includes checkout, image selection,
both image pulls/preflights, and cibuildwheel setup; it does not hide image
downloads outside the measured interval. It is a first-build *start* metric,
not time to a completed wheel. Pull/validation is the explicit preflight step's
`completedAt - startedAt`; job duration uses the corresponding job timestamps.

| Architecture | Samples in this run | Median pull + validation | Median job to first build | Median job duration |
| --- | ---: | ---: | ---: | ---: |
| x86_64 | 6 | 73.0 s | 88.15 s | 199 s |
| aarch64 | 6 | 66.5 s | 78.65 s | 182 s |

Samples are six interpreter jobs in **one** run, not six independent full runs.

| Architecture | Interpreter | Job ID | Pull + validation (s) | Job to first build (s) | Job duration (s) |
| --- | --- | --- | ---: | ---: | ---: |
| aarch64 | cp39 | 117477091979 | 66 | 77.98 | 179 |
| aarch64 | cp310 | 117477092023 | 66 | 75.99 | 177 |
| aarch64 | cp311 | 117477092096 | 90 | 102.75 | 214 |
| aarch64 | cp312 | 117477092021 | 67 | 81.81 | 182 |
| aarch64 | cp313 | 117477091975 | 66 | 77.38 | 182 |
| aarch64 | cp314 | 117477092123 | 67 | 79.31 | 183 |
| x86_64 | cp39 | 117477092040 | 70 | 82.23 | 192 |
| x86_64 | cp310 | 117477091943 | 70 | 84.55 | 196 |
| x86_64 | cp311 | 117477091954 | 76 | 91.75 | 205 |
| x86_64 | cp312 | 117477092129 | 70 | 83.88 | 195 |
| x86_64 | cp313 | 117477091957 | 93 | 105.92 | 209 |
| x86_64 | cp314 | 117477091998 | 92 | 110.81 | 202 |

The run's usage endpoint reports `run_duration_ms=471000` (7m51s). Created-to-last
successful job completion is 470 seconds. Its billable usage fields report
zero milliseconds for Ubuntu, macOS, and Windows. Those fields do not establish
image-refresh/storage cost or provide cache telemetry; they must not be treated
as zero runner execution time.

## Interpretation and next experiment

Historical upstream-image
[run 39055150721](https://github.com/WizzyGeek/pyo3dCBOR/actions/runs/39055150721)
had job-to-first-build times of 56.43 seconds on x86_64 (job 117461936679) and
47.09 seconds on ARM64 (job 117461936680). Its Linux jobs each built all six
interpreters; this trial uses separate interpreter jobs and the newer workflow
dependency graph. This is **not a controlled performance comparison**, and any
whole-workflow improvement cannot be attributed to the maintained images.

The observed first-build latency is higher in this trial, so the proposed
20% setup-speed improvement has not been demonstrated. Pulling and validating
both libc images before starting either build is a substantial part of setup.
The per-interpreter matrix also repeats image pulls across runners. A useful
next experiment would let cibuildwheel pull each pinned image when needed and
retain the same fail-closed runtime validator in `before_all`, avoiding the
redundant up-front preflight. Measure that against upstream mode using the same
matrix/source, without adding routine macOS executions.

Maintained mode remains opt-in; upstream mode is the rollback. Keep FEAT_001
open pending repeated comparable measurements, cost/cache evidence, and review
of newly hardened publisher output. One successful compatibility run does not
satisfy the five-comparable-run adoption threshold.

## Reproducing the evidence

Use `gh run view 39060344953 --json jobs,createdAt,updatedAt,headSha` for job
timestamps, `gh api repos/WizzyGeek/pyo3dCBOR/actions/runs/39060344953/timing`
for usage fields, and the job-log endpoint
`repos/WizzyGeek/pyo3dCBOR/actions/jobs/JOB_ID/logs` for the timestamped first-build
and runtime-validation lines. Current gh versions may require
`--allow-escape-sequences` when saving logs; strip ANSI formatting before parsing.
The complete bundle validator is job 117478423533. Logs/artifacts are subject
to repository retention; the tables above preserve the measured values.
