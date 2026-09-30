# Issue tracker: Local Markdown with GitHub Issues

Issues and specs live primarily as Markdown files in `.scratch/`.
GitHub Issues are also available in A625A/Crypto-Market-Intelligence-Pipeline.

## Local conventions

- One feature per directory: `.scratch/<feature-slug>/`.
- Spec: `.scratch/<feature-slug>/spec.md`.
- Tickets: `.scratch/<feature-slug>/issues/<NN>-<slug>.md`,
  numbered from 01, with one file per ticket.
- Record status near the top: `Status: open`, `Status: claimed`,
  or `Status: resolved`.
- Append conversation history under `## Comments`.
- Reference tickets by path; numbers are scoped to their feature directory.

## Publish and fetch

When a skill says "publish to the issue tracker", create a local
Markdown file using the conventions above.

When fetching a ticket, read the referenced local file. For an explicit
GitHub issue URL or repository issue number, use `gh issue view`.

## GitHub Issues

- Publish or update GitHub Issues when the user requests it.
- Use the `gh` CLI from this repository.
- For multiline content, write a temporary body file and use `--body-file`.
- Link a matching GitHub issue from the local ticket using `GitHub: <URL>`.
- Keep the local ticket as the working record for linked tickets.
- Do not automatically mirror tickets, comments, or status changes.
- If local and GitHub records disagree, flag the difference before syncing.

PRs as a request surface: no.

## Wayfinding operations

- Map: `.scratch/<effort>/map.md`, containing Notes, Decisions-so-far,
  and Fog sections.
- Children: `.scratch/<effort>/issues/<NN>-<slug>.md`.
- Record `Type: research`, `prototype`, `grilling`, or `task`.
- Record dependencies as `Blocked by: NN, NN`.
- A ticket is unblocked when every listed blocker is resolved.
- Select the first open, unblocked, unclaimed ticket by number.
- Claim by saving `Status: claimed` before starting work.
- Resolve by appending `## Answer`, setting `Status: resolved`,
  and adding a short summary and relative ticket link to the map.
