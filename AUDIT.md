# Pet Chat audit — 2026-10-13

Checked the latest published release, Hermes **v0.21.7**, at source commit
`71d34bad1045610252eda02ee79549436896e784`. No local Hermes installation was
used. Compatibility failures were reproduced before the fixes; the existing
tests alone had passed.

| Finding | Correction |
| --- | --- |
| The old `hermes_cli.__version__` reports `0.0.0` on an unstamped 0.21.7 source checkout, disabling generation. | Read `get_version_info().base_version`; retain the old lookup only for hosts without the new API. Unknown identities still fail closed. |
| The backend imports PyYAML, which current Hermes no longer supplies as its YAML dependency. | Use `hermes_yaml`, with PyYAML as the older-host fallback. |
| The catalog omitted profile provider definitions, hiding named custom models and ignoring provider enablement overrides. | Pass both `providers` and `custom_providers` into the host picker. Verified through a real settings save and generation request. |
| Current Hermes ignores the manifest's old `compatibility` field. | Add the host-supported `requires_hermes` constraint and verify that it rejects 0.22.0. |
| Canvas-based pet detection excludes popped-out pets and depends on private DOM structure. | Prefer the supported `ctx.pet.say/clear/visible` API; keep the in-window fallback for older hosts. |
| Changing the focused owner without changing the backend socket can show an old profile's pending quip. | Clear and invalidate on an owner identity change. Equal owner objects do not discard pending replies. |

Validation uses an isolated Python environment with OpenAI SDK 2.24.0,
FastAPI 0.133.1, Starlette 1.3.1, and ruamel.yaml 0.18.16, matching the relevant
Hermes pins. No runtime dependencies were added to Pet Chat.

- Python regression suite: **28 passed**, no skips.
- Desktop logic suite: **8 passed**, covering native bubbles, hidden pets,
  owner changes, late replies, cleanup, and the older-host path.
- `python tests/check_hermes.py /path/to/hermes-agent`: **4 passed** against
  v0.21.7. Uses real host helpers and the OpenAI SDK, temporary configs, and an
  in-memory HTTP transport. Real socket connections and non-git subprocesses
  are blocked. Checks settings → exact-model generation, request-local profile
  context, version gates, and one-request/no-fallback behavior for HTTP
  401/404/429/500 failures.
- JavaScript syntax, isolated Ruff correctness checks, and `git diff --check`
  passed.

This establishes source/API compatibility and offline behavior, **not** live
provider success or visual Desktop operation. No plugin was installed,
enabled, published, or tested against a paid model in this audit. Older Hermes
support is retained but was not re-tested against its real source. The native
bubble caps visible text at 120 characters; the legacy bubble and backend cap
at 200. The private generation adapter and provider-dependent token limits
remain as described below.

Sources: [release](https://github.com/NousResearch/hermes-agent/releases/tag/v0.21.7),
[version API](https://github.com/NousResearch/hermes-agent/blob/71d34bad1045610252eda02ee79549436896e784/hermes_cli/version_info.py),
[YAML module](https://github.com/NousResearch/hermes-agent/blob/71d34bad1045610252eda02ee79549436896e784/hermes_yaml.py),
[catalog](https://github.com/NousResearch/hermes-agent/blob/71d34bad1045610252eda02ee79549436896e784/hermes_cli/model_switch_providers.py),
[pet API](https://github.com/NousResearch/hermes-agent/blob/71d34bad1045610252eda02ee79549436896e784/apps/desktop/src/contrib/plugin.ts).

# Previous audit — 2026-09-05

The following records the earlier environment and verification; it is retained
as history and does not describe the current machine or all current behavior.

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
