# Pet Chat

Hermes has a desktop pet. It wanders around your window, it has six animations,
and it has never once had an opinion about anything you've typed.

Pet Chat gives it one. Every prompt you send, the pet reads and reacts to in a
single line beside itself. Send a two-word prompt with a typo in it and the pet
has opinions about both.

It doesn't touch your actual message. The quip shows up on its own a few seconds
later, or not at all.

> Built against Hermes Agent **v0.19.0** using an internal API. Not a supported
> plugin, not a marketplace release.

## You need a pet first

Pet Chat isn't a pet. It has no sprites and draws nothing. It attaches to the
pet you already have.

So under **Settings → Appearance → Pet**, the pet needs to be switched on *and*
have an actual pet chosen. On-with-nothing-selected is the usual reason a
perfectly good install seems to do nothing at all. Keep it in the window, too —
pop it out to the desktop overlay and Hermes removes the in-window pet, leaving
nothing to attach to.

You'll also need a provider already set up in Hermes. Pet Chat won't pick one
for you, or spend anything until you've chosen the exact model it may use.

## Install

Hand Hermes the URL:

```bash
hermes plugins install https://github.com/ztrek7/pet-chat
```

No cloning, no build. Hermes clones it for you.

There's a second half — the Desktop artifact — and the installer prints its
command when the first part finishes. Run that, then **fully quit and reopen
Hermes Desktop.** Not `hermes gateway restart`: that reports success and does
nothing, because the Desktop app runs its own API server and only picks up new
plugins when the app itself starts.

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
never your attachments, tool output, history, memory, or Hermes' reply. Nothing
is logged or kept. Models that reason by default use their lightest advertised
effort when Hermes reports one; optional Claude thinking stays off. Every
provider receives the same compact two-message request.

Anything that looks like a credential is refused rather than sent, which is a
backstop against your own typing and not a real secret scanner. If the provider
fails, that's the end of it — no retry, no fallback to some other model you
didn't agree to pay for.

## Security scan

SkillSpector rates this **3/100 — LOW, SAFE**. The scale runs backwards from
most: 0–20 SAFE, 21–50 CAUTION, 51+ DO NOT INSTALL. Low is good.

The single finding is the MIT licence tripping a scope-creep rule, which every
MIT project on earth will do.

Scan it yourself anyway. I'm the person asking you to install this, so my number
is worth what you paid for it. What you scan is all there is: one branch, and
the same files Hermes copies onto your disk.

## What's in here

Two halves that install separately and must be on the same commit — the
installer refuses otherwise.

`dashboard/` is the Python side, running inside Hermes:

- **`exact_client.py`** — the only file here that can reach a provider. One
  call, the exact model you picked, no retries. If the provider hands back a
  different model, it stops rather than billing you for a substitute.
- **`quip.py`** — the attitudes, the eight-second cooldown, and the credential
  check. It reads your whole message before cutting it to 400 characters, so
  nothing hides in the part that gets trimmed.
- **`plugin_api.py`** — settings and readiness. It writes its own five config
  keys by hand rather than going through Hermes' config writer, which would
  reformat things it has no business touching.

`desktop/plugin.js` is the settings page and the bubble. The fiddly part is
finding the pet at all: Hermes gives it no id, class, or data attribute, so this
identifies it by where it sits and what it stacks above. If the pet ever gets
restyled upstream, bubbles stop appearing and nothing announces it.

`scripts/` installs and removes the Desktop half, keeping a receipt so it can
never delete something it didn't put there.

`after-install.md` prints in your terminal the moment installation finishes.
It's for that, not for reading here.

## Known limits

Quips top out at 200 characters, one at a time, no more than one every eight
seconds. Generation only works on Hermes v0.19.0. Popped-out pets get nothing.

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
