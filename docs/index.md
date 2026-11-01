---
hide-toc: true
---

# dCBOR for Python

Deterministic CBOR bytes for Python values, with canonical map ordering,
checked input, normalized text, and explicit behavior for Python types that do
not map directly to CBOR.

::::{container} docs-cards

:::{container} docs-card
### Start with a round trip

Install dCBOR, encode a Python value, inspect its bytes, and decode it again in
the [first tutorial](tutorials/first-round-trip.md).
:::

:::{container} docs-card
### Solve a specific task

Choose a focused guide for [storing values](how-to/persist-values.md),
[stable digests](how-to/stable-digests.md),
[validating external CBOR](how-to/validate-external-cbor.md), or
[preserving distinct map keys](how-to/preserve-distinct-map-keys.md).
:::

:::{container} docs-card
### Understand the format

Read about [deterministic bytes](explanation/determinism.md),
[Python type mapping](explanation/types-and-normalization.md), and
[resource limits](explanation/limits-and-memory.md).
:::

:::{container} docs-card
### Look up the API

Find the documented functions, classes, exceptions, accepted values, and
limits in the [Python API reference](reference/index.md).
:::

::::

## Browse the documentation

```{toctree}
:hidden:
:caption: Documentation
:maxdepth: 2

tutorials/index
how-to/index
explanation/index
reference/index
glossary
contributing
```

The [glossary](glossary.md) defines dCBOR terms. The
[documentation maintenance guide](contributing.md) explains how to update and
validate these pages.
