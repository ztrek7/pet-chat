# Compatibility and validation

Target: official NousResearch Hermes Agent **0.22.5**, source commit
`bf0203a794a07aac3ff764972ab9087baa4e4f4e` (checked 2026-10-24).
The installed Desktop build uses the same commit. This candidate accepts
`>=0.22.5,<0.23.0`; widening that range requires another compatibility check.

This is a native unified package: `plugin.yaml` and `register(ctx)` provide the
agent-side entrypoint, `dashboard/manifest.json` mounts scoped Python HTTP
routes, and `desktop/plugin.js` imports `@hermes/plugin-sdk`. It is not a
portable Agent Plugins package, a CLI-only frontend, or the web-dashboard JS SDK.
Both backend and Desktop must be enabled deliberately. `requires_hermes` is the
runtime gate; the old `compatibility`/`entrypoint` fields were ignored by this host
and have been removed. `__init__.py` is discovered normally.

Authoritative references:

- [Native plugin guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins)
- [Desktop SDK and unified packages](https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk#one-package-both-sdks)
- [Plugin management](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins)
- [Installed-version source](https://github.com/NousResearch/hermes-agent/tree/bf0203a794a07aac3ff764972ab9087baa4e4f4e)

Run mock regressions with Python dependencies installed in a test environment:

```bash
python tests/run_offline.py
node --check desktop/plugin.js
```

The runner clears inherited credentials, uses a temporary home, and blocks
Python network connections. CLI fixtures are synthetic executables; no provider
sign-in, paid generation, or real secret operation belongs in this suite.
To exercise the real host, use its prepared Python with its dependencies:

```bash
python tests/check_lifecycle.py /path/to/hermes-agent
```

That check validates through Hermes' own validator and doctor and exercises
fresh discovery, explicit temporary enablement, repeated reload, disable/unload,
and package removal. It does not impersonate the package manager's dependency
transaction or start Desktop. Host validation warnings are reported, not hidden.

The same mock suite also passes in a fresh test venv without Hermes on its
import path. Full standard lifecycle verification subsequently passed through
the real CLI handlers and PM transactions in a separate official Hermes source
checkout with isolated HOME, config, caches and runtime. It covered install
without enablement, enable, disable, update, re-enable and remove. Update kept
disabled state and a synthetic user file; removal cleared package/selection
metadata and retained unrelated configuration. No host functions were mocked.
Public package downloads used the approved normal-host executor after the
sandbox-only attempt could not resolve DNS. No live installation was touched.
These tests do not cover a running Desktop, remote gateway, or provider account.

Desktop tests use SDK doubles, not a visual end-to-end session. No live plugin
replacement, active-session restart, or persistent permission change was made
while preparing this release. Passing these tests is not a claim that every
provider, OS, remote gateway, or future Hermes release has been verified.

## Pet Chat 0.2.0

Verified: 28 Python regressions, 9 Desktop checks, and 4 real-host offline HTTP
integration checks. The latter exercise settings/catalog/provider resolution,
request construction through an in-memory HTTP transport, profile propagation,
and one-request failure behavior for 401/404/429/500. No paid endpoint was called.

```bash
node --experimental-vm-modules tests/test_desktop.mjs
python tests/check_hermes.py /path/to/hermes-agent
```

The native `ctx.pet` API replaces DOM inspection and the legacy bubble renderer.
No native API means no prompt egress. Disable/scope changes dispose listeners and
suppress late quips. Prompt length, credential heuristic, exact selected pair,
zero-retry checks, cooldown, cost confirmation, and privacy disclosures remain.
The published documentation cleanup remains part of the branch history.

**Remaining internal contract:** generation, model catalog, and cost classification
still import Hermes internals. The official `ctx.llm` API explicitly permits
fallback on provider errors and cannot currently preserve this plugin's
exact-model/no-fallback promise. Do not replace it without a supported strict
route and equivalent regression proof. The validator reports private-import
warnings; this candidate is not claimed ready for official catalog admission.
The [LLM API documentation](https://hermes-agent.nousresearch.com/docs/developer-guide/plugin-llm-access)
explains host fallback. Desktop visual behavior remains unverified.

## Public API review (0.22.5)

The follow-up review removed the obsolete `hermes_cli.__version__` and
`hermes_cli.version.__version__` fallbacks. Missing/unreadable authoritative
version information fails closed; a stale constant cannot enable generation.

Remaining imports are grouped by behavior, not hidden from validation:

- `hermes_cli.version_info.get_version_info`: recognizes source and packaged
  builds before direct API execution. The manifest also gates normal loading.
  No documented plugin version-query equivalent was found.
- `agent.auxiliary_client.resolve_provider_client` / `_build_call_kwargs`:
  resolve the exact chosen route and prepare one bounded request. `ctx.llm` is
  public, but owns retry/fallback behavior and exposes no strict zero-retry,
  no-fallback switch. Changing to it would weaken the existing privacy/cost
  promise; new provider/model grants are also outside this migration.
- `hermes_cli.model_switch.list_authenticated_providers`: preserves the scoped
  authenticated/custom-provider picker. `providers.list_providers()` is public
  registration metadata, not that inventory.
- `agent.models_dev` helpers/constants: text-output and reasoning-effort metadata.
  `ProviderProfile` metadata is not equivalent to the live catalog and its
  reasoning choices.
- `hermes_cli.model_cost_guard.expensive_model_warning`: host cost classification
  behind explicit confirmation. No equivalent public cost-warning function was
  found; dropping it would weaken the confirmation gate.
- `hermes_yaml`: preserves the host's YAML schema for the existing auxiliary
  settings and revision-checked raw-file transaction. `ctx.get_config/set_config`
  owns only `plugins.entries.<id>.settings`, not `auxiliary.pet_chat`;
  `load_config/save_config` normalizes the global config. PyYAML is not a drop-in
  equivalent for this host's duplicate-key and scalar behavior.

These are target-version adapters, not stable public extension points. The
proper upstream requests are a strict generation lane, authenticated model
metadata/cost surface, and a public auxiliary-settings transaction. Do not
monkeypatch the host or suppress validator findings to simulate compliance.

Review references: [PluginContext](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/plugins.py),
[public PM operations](https://hermes-agent.nousresearch.com/docs/reference/package-management#python-operation-interfaces),
[LLM contract](https://hermes-agent.nousresearch.com/docs/developer-guide/plugin-llm-access),
[provider usage contract](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/providers/base.py).
