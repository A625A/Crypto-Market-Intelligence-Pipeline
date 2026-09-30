## Agent skills

### Issue tracker

Track work primarily in local Markdown under `.scratch/`, with optional
linked GitHub Issues. See `docs/agents/issue-tracker.md`.

### Domain docs

Use a single-context layout: root `CONTEXT.md` and `docs/adr/`.
See `docs/agents/domain.md`.

# Project Guidelines

This is a portfolio/CV data science project.

Prefer simple, readable, interview-defendable code over enterprise-level abstractions.

Follow the style and complexity of the existing files in `src/` whenever possible.

When implementing features:

* keep functions focused and easy to explain;
* avoid unnecessary abstractions, CLI frameworks, design patterns, or infrastructure;
* do not add complexity only for production realism;
* preserve important data-science safeguards such as leakage prevention, validation, reproducibility, and testing;
* reuse existing project patterns before introducing new ones;
* use logging instead of `print`;
* keep paths and script execution consistent with the rest of the repository.

If a more complex implementation is materially safer or necessary, use it, but keep it as simple as possible and explain why it is needed.

The goal is code that I can understand, explain, and defend in a junior Data Scientist / ML Engineer interview.
