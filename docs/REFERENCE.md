# Pet Chat technical reference

[Back to the README](../README.md) · [Install and remove](../INSTALL.md)

## Provider requests

Quips run on a provider you choose and pay for. Your prompt is capped at 4,000
characters going into the plugin, and only the first 400 reach the provider —
never your attachments, tool output, history, memory, or Hermes' reply. Pet Chat
does not store prompts or quips; the selected provider's retention rules still
apply. Models that reason by default use their lightest advertised
effort when Hermes reports one; optional Claude thinking stays off. Every
provider receives the same compact system instruction and user excerpt, in
the wire format that Hermes requires. Token caps are provider-dependent;
64 requested tokens is not a universal billing limit.

Text matching the credential heuristics is refused rather than sent. This
is a backstop, not a complete secret scanner. If the provider
fails, that's the end of it — no retry, no fallback to some other model you
didn't agree to pay for.

## Security

Review the code before installing it. An old scan score is not a security
guarantee for the current revision. Pet Chat uses the host's authenticated
plugin routes, rejects virtual routing, and refuses clients that cannot show
zero SDK retries. Bare `custom` is excluded because Hermes can route it to
another provider; use a named custom provider instead.

## What's in here

The Python backend and Desktop UI ship in one package.

`dashboard/` is the Python side, running inside Hermes:

- **`exact_client.py`** — the only file here that can reach a provider. One
  call, the exact model you picked, no application retry. If Hermes resolves
  a different model, it stops before generation. It cannot independently
  verify what model a remote provider actually runs.
- **`quip.py`** — the attitudes, the eight-second cooldown, and the credential
  check. It reads your whole message before cutting it to 400 characters, so
  nothing hides in the part that gets trimmed.
- **`plugin_api.py`** — settings and readiness. It changes five owned config
  values and writes the YAML atomically. Other values are preserved, but YAML
  comments and formatting are not. Do not edit config concurrently with a save.

`desktop/plugin.js` is the settings page and the bubble. Current hosts display
quips through `ctx.pet.say`, using Hermes' own visibility and cleanup rules.
Older hosts use a fallback that locates the in-window pet by its canvas and
positioning; changes to that older renderer can still break the fallback.

`scripts/` maintains legacy standalone Desktop copies. A receipt checks
ownership for removal. New installs use the host's single-package loader.

`after-install.md` prints in your terminal the moment installation finishes.
It's for that, not for reading here.

## Known limits

The backend caps quips at 200 characters; Hermes' native bubble displays up to
120. Quips run one at a time, no more than once every eight seconds per backend
process. Generation accepts Hermes 0.20.x and 0.21.x only. Hidden pets get
nothing; popped-out pets need the native bubble API. Messages over 4,000 characters are
skipped, not truncated before scanning. Chats on another profile or connection
are skipped when they do not match the active plugin backend.

Settings writes require POSIX file locking (macOS/Linux). No Windows locking
fallback is claimed. The lock coordinates Pet Chat writers, not external editors.

## Checks

Use the Python environment that runs Hermes (it supplies `hermes_yaml`, FastAPI
and httpx; older releases supply PyYAML). Pet Chat has no separate dependency
set or build step.

```bash
python -m unittest discover -s tests -v
node --experimental-vm-modules --test tests/test_desktop.mjs
```

The regression checks use test doubles and temporary files, not paid models.
To check current Hermes helpers against a source checkout with its dependencies:

```bash
python tests/check_hermes.py /path/to/hermes-agent
```

That check runs the real catalog, cost guard, provider resolver, request builder,
and SDK against an in-memory HTTP transport. It blocks network connections and
uses temporary profile settings. See [AUDIT.md](../AUDIT.md) for results and limits.

