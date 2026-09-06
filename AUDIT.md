# Pet Chat audit — 2026-09-05

## Assessment

The original checkout matched `origin/main` at `5a013a9`, but it did not run
on the installed Hermes 0.21.0: both its manifest and generation guard rejected
that version. The original 13 smoke tests passed despite this runtime failure.

The repaired backend passed a real provider call on Hermes 0.21.0. Python and
Desktop logic regression checks pass. Full visual operation in Hermes Desktop
has **not** been verified. This audit did not install or enable the plugin.
Changes are local; they have not been committed or published.

## Findings fixed

| Priority | Finding | Repair |
| --- | --- | --- |
| High | Generation blocked the FastAPI event loop for the duration of a synchronous provider call. | Run blocking handlers in worker threads. Serialize first-time sibling imports. |
| High | A staging failure in the legacy installer deleted the untouched previous artifact. | Remove only a newly installed target during rollback. Retain backups if restoration fails. |
| High | Unreadable or non-mapping YAML could be treated as empty config before a save. | Refuse these inputs and malformed parent mappings. Return a bounded error for write failures. |
| High | Hermes' bare `custom` route could select an unrelated API-key provider. | Exclude it before client resolution and from the picker. Named custom providers remain available. |
| Medium | Different vendor-qualified model IDs could pass the exact-model check. | Compare complete IDs when both have a vendor prefix. |
| Medium | Hermes ignores cleanup functions returned by `register(ctx)`. | Use `ctx.onDispose`; remove listeners and invalidate late replies on disable. |
| Medium | Old readiness replies could overwrite the state for a new profile or connection. | Check scope and request sequence. Skip cross-owner composer submissions. |
| Medium | Electron HTTP errors were treated as parsed objects, hiding cost confirmations and conflict messages. | Decode serialized HTTP JSON and display only known error codes. |
| Medium | The supported-version guard rejected Hermes 0.21.0. | Accept 0.20.x and 0.21.x; keep unknown versions blocked. Align the registered timeout with the existing 30-second request budget. |
| Low | Old instructions required two installed copies and made unsupported scan/privacy claims. | Document the unified loader, legacy migration, and actual limits. |

## Verification

Environment: Hermes reports `0.21.0 (2026.8.31)`, source checkout `ee5b5ec21e`,
Python 3.11.15, OpenAI SDK 2.24.0. GitHub's latest published Hermes release at
check time was `v2026.8.31`. This does not assert that every host dependency is
at its latest package version. Pet Chat has no separate dependency manifest;
it uses packages supplied by Hermes. No runtime dependencies were added.

Completed checks:

- `python -m unittest discover -s tests -v`: **23 passed**, no skips in the
  Hermes environment.
- `node --experimental-vm-modules --test tests/test_desktop.mjs`: **3 passed**.
  Node emits the expected experimental VM-module warning.
- `node --input-type=module --check < desktop/plugin.js`: passed.
- `ruff check --isolated --select E9,F .`: passed.
- `git diff --check`: passed.

The inherited machine-wide Ruff rules initially reported style findings.
This audit used isolated correctness rules rather than reformatting the repo
or applying unrelated typing changes. It does not claim a full style-lint pass.

The new regression checks were run before the fixes and reproduced failures
in rollback, config handling, routing, event-loop blocking, error decoding,
disposal, and readiness ordering. They use explicit test doubles and temporary
files; no model calls are part of the normal regression suite.

### Real generation check

Mounted the actual `dashboard/plugin_api.py` router in a FastAPI test app using
the installed Hermes Python environment. The provider resolver, request builder,
credential handling, catalog and model call were real, not mocked. The request
used the existing saved `xai-oauth` / `grok-4.5` pair and a harmless test prompt.

- `GET /api/plugins/pet-chat/status`: HTTP 200, `state: ready`.
- `POST /api/plugins/pet-chat/quip`: HTTP 200, with this actual text:

  > Alphabetizing stars ignores how gravity keeps misfiling the whole sky nightly.

The measured status-plus-generation sequence took 5.06 seconds. This checks the
plugin router and provider path, not Electron rendering or the host's full
authenticated HTTP mount. The host catalog also emitted a Copilot token-exchange
warning; the selected xAI call succeeded and did not use Copilot.

## Remaining limits

- Desktop installation, enabling, visible pet anchoring and actual settings-page
  interaction remain unverified. Permission to enable the disabled plugin was
  requested, but no answer was received. No profile settings were changed.
- The internal LLM adapter still needs review with each Hermes version. Only
  the saved xAI route was live-tested; other providers were not certified.
  Hermes 0.20 support was retained, not re-tested end to end.
- `ctx.llm` was not substituted: current official docs explicitly describe
  fallback behavior, which does not meet Pet Chat's no-fallback requirement.
- The pet anchor still depends on Hermes' fixed-position, z-index-60 canvas
  container. The installed upstream source still uses that structure, but a
  later renderer change can break the anchor.
- The secret check is a heuristic, not a complete credential scanner. Provider
  retention and billing still apply. Some Hermes adapters omit token caps;
  64 requested tokens is not a hard cost ceiling for every provider.
- Config saves preserve unrelated values, not comments or YAML formatting.
  The advisory lock coordinates Pet Chat processes, not external editors or
  unrelated host writers. Do not edit config while saving Pet Chat settings.
  Settings writes now fail closed without POSIX locking; Windows is not claimed.
- No full vulnerability scan of the host environment was performed. This is a
  code and runtime audit, not a security certification.

## Primary references

- [Latest published Hermes release](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.31)
- [Desktop plugin SDK and unified packages](https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk)
- [Plugin LLM access and fallback behavior](https://hermes-agent.nousresearch.com/docs/developer-guide/plugin-llm-access)
- [Hermes provider adapter source](https://github.com/NousResearch/hermes-agent/blob/ee5b5ec21e/agent/auxiliary_client.py)
- [Desktop plugin context and disposal](https://github.com/NousResearch/hermes-agent/blob/ee5b5ec21e/apps/desktop/src/contrib/plugin.ts)
