# Pet Chat

A Hermes Desktop plugin that gives your existing pet short reactions to your prompts.

Your pet has opinions now. Snarky by default; your actual message stays unchanged.

> Accepts Hermes Agent **0.20.x and 0.21.x**. Source/API compatibility was checked
> offline against **v0.21.7**; **Desktop visual operation remains unverified**.
> Generation uses an internal Hermes API. See the [audit](AUDIT.md) for the limits.

## Install and first use

You need macOS or Linux, a provider configured in Hermes, and a pet enabled
**and selected** under **Settings → Appearance → Pet**. Pet Chat supplies no sprites.

```bash
hermes plugins install https://github.com/ztrek7/pet-chat
```

1. Fully quit and reopen Hermes Desktop. A gateway restart alone is not enough.
2. Turn on **Pet Chat** in **Settings → Plugins**, then open it from the sidebar.
3. Choose the exact provider/model pair and an attitude, then save.
4. Send a short prompt with your pet visible. Eligible prompts can receive a
   one-line reaction; no model is selected or called until you save a pair.

Current Desktop loads both halves from the same package; no second Desktop
copy is needed. Older hosts without the native pet bubble API require the pet
to stay in the window. See [INSTALL.md](INSTALL.md) for profiles and troubleshooting.

## Attitudes

| Attitude | Personality |
| --- | --- |
| **snarky** (default) | Goes after the typos, vagueness, and ambition of the prompt. |
| supportive | Nice about it. |
| dramatic | Far too invested. |
| minimal | Can barely be bothered. |

Custom attitudes are not supported yet.

## Cost and privacy

Quips use the provider and model **you choose and pay for**. The provider gets
up to the first **400 characters** of your prompt, never attachments, tool
output, history, memory, or Hermes' reply. Prompts over 4,000 characters are
skipped. Pet Chat does not store prompts or quips; **provider retention rules
still apply**. Token limits depend on the provider and are not a hard billing cap.

The plugin refuses text that looks like a credential, but that check is only a
heuristic. A failed request stops there: **no retry and no model fallback**.
Review the code before installing.

## Limits

- Quips run one at a time, at most once every eight seconds per backend process.
- Hidden pets receive no quips. Popped-out pets need Hermes' native bubble API.
- The backend caps quips at 200 characters; the native bubble displays up to 120.
- Chats on another profile or connection are skipped if they do not match the
  active plugin backend.
- Settings writes require macOS/Linux. Avoid editing Hermes config while saving
  Pet Chat settings; YAML comments and formatting are not preserved.

## Update or remove

Update, then fully restart Hermes Desktop:

```bash
hermes plugins update pet-chat
```

For an ordinary single-package install, turn Pet Chat off in **Settings → Plugins**,
then remove it and restart Desktop:

```bash
hermes plugins disable pet-chat
hermes plugins remove pet-chat
```

**Older two-copy installs:** follow the [legacy cleanup steps](INSTALL.md#uninstall)
**before** removing the backend package. They verify ownership of the standalone
Desktop copy; ordinary installs do not need them.

## More details

- [Installation, profiles, and troubleshooting](INSTALL.md)
- [Implementation, provider safeguards, and offline checks](docs/REFERENCE.md)
- [Audit results and unverified behavior](AUDIT.md)
- [Report a problem](https://github.com/ztrek7/pet-chat/issues)

MIT. See [LICENSE](LICENSE).
