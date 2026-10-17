# Requirements

Feature proposals and bug reports are tracked here as individual Markdown
files. Use one of these formats:

```text
FEAT_NNN_short_title.md
BUG_NNN_short_title.md
```

Use one shared serial sequence for all items, regardless of type. Assign the
next available zero-padded number to each new item: for example, after
`FEAT_001`, the next item may be `BUG_002`, followed by `FEAT_003`. Do not
restart numbering for bugs or features. Use a short lowercase title with words
separated by underscores.

A `FEAT` document describes a proposed capability or engineering improvement.
Include its status, problem, expected outcome, scope, acceptance criteria, and
research references. It records desired behavior and constraints; it does not
authorize implementation by itself. The PM should prioritize and assign
accepted features before implementation.

A `BUG` document records a defect. Include the observed behavior, expected
behavior, reproducible steps or evidence, impact, and acceptance criteria for
the fix. Avoid including secrets or sensitive user data.

## Sign-off and cleanup

When the PM signs off that a feature is complete or a bug is fixed, delete its
corresponding `FEAT_NNN_...md` or `BUG_NNN_...md` file and remove its entry
from the current list. Keep lasting implementation details in relevant product
or maintenance documentation rather than retaining completed items as open
work.

## Current items

- Features:
  - [FEAT_002: Versioned release and bundle workflow](FEAT_002_versioned_release_workflow.md)
- Bugs: none
