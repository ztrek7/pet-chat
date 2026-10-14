# Install Pet Chat

Pet Chat has a Hermes backend and a Desktop UI in one installed package.

## Requirements

- Hermes Agent 0.20.x or 0.21.x (offline compatibility checked on 0.21.7)
- A provider configured and authenticated in Hermes
- Git available to Hermes
- macOS or Linux for settings writes
- A pet enabled and selected under **Settings → Appearance → Pet**

Current Hermes displays quips through its native pet bubble, including the
popped-out overlay. On older hosts without that API, keep the pet in the window.

## 1. Install the Hermes plugin

```bash
hermes plugins install https://github.com/ztrek7/pet-chat
```

When Hermes asks whether to enable `pet-chat`, answer `y`. The installer uses
the repository's default branch and records the commit it received.

Current Desktop loads `desktop/plugin.js` from the installed backend package.
Do not create a second copy under `desktop-plugins/` for a new local install.
For a named profile, run the install command in that profile. The Desktop UI
must be installed locally even when its backend is on a remote machine.

## 2. Restart Hermes Desktop

Fully quit Hermes Desktop (**⌘Q** or **Hermes → Quit**) and open it again. A
gateway restart alone is not enough: the Desktop app mounts plugin API routes
when its local server starts.

## 3. Enable and configure

1. Open **Settings → Plugins** and turn on **Pet Chat**.
2. Open **Pet Chat** from the sidebar.
3. Choose an exact provider/model pair and an attitude.
4. Save.

Pet Chat makes no generation request until a pair is saved.

## Update

```bash
hermes plugins update pet-chat
git -C ~/.hermes/plugins/pet-chat rev-parse HEAD
```

Fully restart Hermes Desktop after a backend update. Both halves now come
from the same checkout. An update does not override your disabled state.

### Migrate an old two-copy install

If `~/.hermes/desktop-plugins/pet-chat` exists from an older install, turn off
Pet Chat, then remove that copy with the receipt-backed uninstall command
below. Keep the backend package. Restart Desktop and enable its unified UI.
Do not delete a copy that fails receipt verification; inspect it first.

## Uninstall

Turn Pet Chat off in **Settings → Plugins**. For a legacy two-copy install
only, remove the standalone Desktop artifact:

```bash
python3 ~/.hermes/plugins/pet-chat/scripts/uninstall.py \
  --target ~/.hermes/desktop-plugins/pet-chat \
  --receipt ~/.hermes/pet-chat-receipt.json
```

For named profiles, use that profile's directory in these paths. Remove the
Hermes plugin (this also removes the unified Desktop UI):

```bash
hermes plugins disable pet-chat
hermes plugins remove pet-chat
```

Restart Hermes Desktop after removal. Pet Chat does not edit Hermes Desktop's
own plugin settings.

## Troubleshooting

- **Backend unreachable:** fully quit and reopen Hermes Desktop after
  installation or update.
- **Quips unavailable:** confirm that Hermes is 0.20.x or 0.21.x.
- **No bubble:** confirm that a provider/model pair is saved and the pet is
  visible. Older hosts require the pet to stay in the Hermes window.
- **Provider failed:** Pet Chat does not retry with another provider or model.
- **Missing custom provider:** name the endpoint in Hermes. The bare `custom`
  route is excluded because it can fall through to another provider.
