# AGENTS.md

## Scope

These instructions apply to the entire repository unless a more specific
`AGENTS.md` or `AGENTS.override.md` exists in a subdirectory.

## Working style

- Inspect the existing codebase before making changes.
- Preserve the project's existing architecture, naming, and conventions unless a change is explicitly requested.
- Prefer small, focused changes over broad rewrites.
- Do not expand the scope of a task beyond what was requested.
- Do not introduce abstractions, frameworks, dependencies, or helper layers without a concrete need.
- Prefer simple, explicit solutions over clever ones.
- Follow SOLID, DRY, and KISS where they improve the code; do not apply them mechanically.
- Reuse existing utilities and patterns before creating new ones.
- Avoid speculative refactors.

## Collaboration

- Treat the developer as the decision-maker.
- Support the developer's reasoning instead of replacing it.
- When a task is exploratory, explain relevant findings and trade-offs rather than immediately rewriting large parts of the project.
- When implementation is explicitly requested, implement it directly.
- If the developer has already proposed an approach, evaluate that approach first instead of replacing it with a different design.
- Do not repeat information the developer has already established unless it is needed for the current decision.

## Code changes

- Read the relevant files and nearby call sites before editing.
- Keep diffs minimal and localized.
- Preserve public interfaces unless the task explicitly requires changing them.
- Do not silently change behavior unrelated to the task.
- Do not add placeholder code, fake implementations, or TODO-only stubs unless explicitly requested.
- Do not invent APIs, configuration keys, file paths, or external behavior. Verify them from the repository or authoritative documentation.
- Use exact known paths and identifiers when they are available; avoid placeholder paths when the repository already provides the real ones.
- Prefer modifying existing code over duplicating functionality.

## Dependencies

- Prefer the standard library and existing project dependencies.
- Add a dependency only when it provides a clear advantage over a reasonable existing solution.
- Do not upgrade unrelated dependencies while solving a task.
- If a new dependency is necessary, state why.

## Testing and verification

- Run the narrowest relevant tests, linters, type checks, or build steps after changes.
- Fix failures caused by the change.
- Do not claim that something was tested unless the corresponding command actually ran successfully.
- If verification cannot be performed, state exactly what remains unverified.
- Prefer reproducing a bug before changing code when practical.

## Error handling and logging

- Preserve useful error information.
- Do not suppress exceptions without a specific reason.
- Keep logging useful and non-noisy.
- Never log secrets, credentials, tokens, recovery codes, or other sensitive values.

## Security and secrets

- Never commit credentials, API keys, tokens, private keys, recovery codes, or other secrets.
- Treat existing secrets found in the repository as sensitive and avoid reproducing them in output.
- Do not weaken security controls merely to make a test or implementation pass.

## Documentation

- Update documentation when behavior, configuration, interfaces, or usage changes.
- Keep comments focused on why something exists, not on restating obvious code.
- Do not generate large amounts of documentation unless requested.

## Git

- Do not rewrite history, force-push, delete branches, or discard unrelated working-tree changes unless explicitly requested.
- Do not include unrelated formatting or cleanup in a focused change.
- Keep commits and diffs scoped to the task when commit work is requested.

## External documentation

- For OpenAI API, ChatGPT, Codex, or plugin behavior, prefer current official OpenAI documentation over memory or third-party sources.
