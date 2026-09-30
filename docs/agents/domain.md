# Domain Docs

## Layout

This repository uses a single-context layout:

- `CONTEXT.md` at the repository root: domain vocabulary and context.
- `docs/adr/`: architectural decision records.

## Before exploring

Read `CONTEXT.md` and ADRs relevant to the area being explored.

If these files do not exist, proceed silently. Do not suggest creating
them upfront. Domain-modeling work creates them when terms or decisions
are resolved.

## Use the glossary's vocabulary

Use terms defined in `CONTEXT.md` in issue titles, proposals, hypotheses,
and tests. Avoid synonyms the glossary explicitly excludes.

When a concept is missing, reconsider the term or note the gap for
domain-modeling work.

## Flag ADR conflicts

Explicitly identify any proposal that contradicts an existing ADR,
including which decision would need reconsideration and why.
