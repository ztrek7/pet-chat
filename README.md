# Pet Chat

Hermes has a desktop pet. It wanders around your window, it has six animations,
and it has never once had an opinion about anything you've typed.

Pet Chat gives it one. Every prompt you send, the pet reads and reacts to in a
single line beside itself. Send a two-word prompt with a typo in it and the pet
has opinions about both.

It doesn't touch your actual message. The quip shows up on its own a few seconds
later, or not at all.

> Compatibility checked against Hermes Agent **v0.21.7** source with an offline
> provider transport; accepts **0.20.x and 0.21.x**. Desktop visual operation
> remains unverified. Generation still uses an internal API.

## You need a pet first

Pet Chat isn't a pet. It has no sprites and draws nothing. It attaches to the
pet you already have.

So under **Settings → Appearance → Pet**, the pet needs to be switched on *and*
have an actual pet chosen. On-with-nothing-selected is the usual reason a
perfectly good install seems to do nothing at all. Current Hermes supplies a
native bubble API for both the in-window pet and the desktop overlay. Older
hosts without that API require the pet to stay in the window.

You'll also need a provider already set up in Hermes. Pet Chat won't pick one
for you, or spend anything until you've chosen the exact model it may use.

## Install

Hand Hermes the URL:

```bash
hermes plugins install https://github.com/ztrek7/pet-chat
```

No cloning, no build. Hermes clones it for you.

Current Hermes Desktop loads `desktop/plugin.js` from the same installed
package. No second copy is needed. **Fully quit and reopen Hermes Desktop**
after installing the backend. A gateway restart does not restart the Desktop
app's own API server.

Then switch Pet Chat on in **Settings → Plugins**, open it from the sidebar,
choose a model and an attitude, and save.

Everything else — updates, profiles, uninstall — is in [INSTALL.md](INSTALL.md).

## Attitudes

**Snarky by default**, which is the only one that matters.

| | |
| --- | --- |
| **snarky** | Goes after the prompt: the typos, the vagueness, the ambition, how obvious the answer was. |
| supportive | Nice about it. |
| dramatic | Far too invested. |
| minimal | Can barely be bothered. |

Snarky needed a second pass. The first version was told to be "dry and teasing,
never cruel," and it came out so gentle it was basically being polite about your
typos. It now goes after the prompt properly, with two things it won't do: say
anything about you rather than what you wrote, and keep going if you sound like
you're actually having a bad time.

You can't add your own yet.

## Cost and privacy

Quips run on a provider you choose and pay for. Your prompt is capped at 4,000
characters going into the plugin, and only the first 400 reach the provider —
never your attachments, tool output, history, memory, or Hermes' reply. Pet Chat
does not store prompts or quips; the selected provider's retention rules still
apply. Models that reason by default use their lightest advertised
effort when Hermes reports one; optional Claude thinking stays off. Every
provider receives the same compact system instruction and user excerpt, in
the wire format that Hermes requires. Token caps are provider-dependent;
64 requested tokens is not a universal billing limit.

Anything that looks like a credential is refused rather than sent, which is a
backstop against your own typing and not a real secret scanner. If the provider
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
uses temporary profile settings. See [AUDIT.md](AUDIT.md) for results and limits.

## Uninstall

Switch it off in **Settings → Plugins**, run the uninstall command from
[INSTALL.md](INSTALL.md), then:

```bash
hermes plugins disable pet-chat
```

```bash
hermes plugins remove pet-chat
```

## License

MIT. See [LICENSE](LICENSE).
