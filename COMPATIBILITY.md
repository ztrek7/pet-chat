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
