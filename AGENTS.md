# Agent contribution protocol

For project build, test, and release commands, see the
[agent workflow guide](project-notes/agent-workflow.md). This file defines the
repository-wide contribution and commit requirements.

Repository agents must follow this protocol when completing implementation,
documentation, review-fix, or maintenance work.

## Before committing

- Check `git status` and inspect the complete diff. Stage only files changed for
  the task; preserve unrelated work already in the worktree.
- Run the most relevant existing validation and do not claim completion while
  task-related failures remain unresolved.
- Commit completed work unless the user explicitly asks not to commit, the work
  is not ready to commit, or the environment prevents committing. Do not push or
  publish unless explicitly requested.
- Do not commit secrets, generated build output, or another contributor's
  unrelated changes.

## Attribution and sign-off

Every commit made by an agent must identify the role the agent performed and
include a sign-off for the agent's actual configured commit identity. Keep the
role and sign-off as separate Git trailers; do not put a role in place of the
signer's name or email.

Use this commit-message ending:

```text
Role: <role performed, such as DevOps agent or Python/Rust agent>
Signed-off-by: <actual agent identity> <actual agent email>
Co-authored-by: <actual contributor identity> <actual contributor email>
```

Include one `Co-authored-by` trailer for each actual co-author. For work
performed with Copilot, include:

```text
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

Do not invent identities, claim another person's review or approval, or use a
human maintainer's identity as the agent's sign-off. A sign-off represents the
signer's own contribution and must be truthful. If the environment does not
provide an agent identity/email suitable for sign-off, stop before committing
and ask the user or maintainer how that identity should be represented.

Example:

```text
docs(ci): document build environment speedups

Role: DevOps research agent
Signed-off-by: Copilot <223556219+Copilot@users.noreply.github.com>
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

If the signed-off agent is also a listed co-author, retain both trailers: one
records sign-off and the other records authorship. Never add a `Signed-off-by`
trailer merely to imply a DCO attestation that the signer has not made.
