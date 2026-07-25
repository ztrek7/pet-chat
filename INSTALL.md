# Install Pet Chat

Pet Chat has a Hermes backend and a separate Hermes Desktop artifact. Both
must be installed and enabled before quips can appear.

## Requirements

- Hermes Agent v0.19.0
- A provider configured and authenticated in Hermes
- Git available to Hermes
- A pet enabled and selected under **Settings → Appearance → Pet**

Pet Chat only anchors bubbles to the in-window pet. A popped-out overlay pet
does not display bubbles.

## 1. Install the Hermes plugin

```bash
hermes plugins install https://github.com/ztrek7/pet-chat
```

When Hermes asks whether to enable `pet-chat`, answer `y`. The installer uses
the repository's default branch and records the commit it received.

Record that commit:

```bash
git -C ~/.hermes/plugins/pet-chat rev-parse HEAD
```

## 2. Install the Desktop artifact

Run the following command from the installed checkout. Replace `<commit>`
with the value from the previous command:

```bash
python3 ~/.hermes/plugins/pet-chat/scripts/install-desktop.py install \
  --source ~/.hermes/plugins/pet-chat/desktop \
  --target ~/.hermes/desktop-plugins/pet-chat \
  --receipt ~/.hermes/pet-chat-receipt.json \
  --source-commit <commit>
```

For a named Hermes profile, use that profile's directory for `--target` and
`--receipt`.

The helper verifies the artifact and commit before replacing anything. It
keeps a receipt so updates, repairs, and removal can verify ownership.

## 3. Restart Hermes Desktop

Fully quit Hermes Desktop (**⌘Q** or **Hermes → Quit**) and open it again. A
gateway restart alone is not enough: the Desktop app mounts plugin API routes
when its local server starts.

## 4. Enable and configure

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

Run the Desktop install command from step 2 with the new commit, then fully
restart Hermes Desktop. The helper stops if the Python and Desktop artifacts
come from different commits.

## Uninstall

Turn Pet Chat off in **Settings → Plugins**, then remove the Desktop artifact:

```bash
python3 ~/.hermes/plugins/pet-chat/scripts/uninstall.py \
  --target ~/.hermes/desktop-plugins/pet-chat \
  --receipt ~/.hermes/pet-chat-receipt.json
```

Remove the Hermes plugin:

```bash
hermes plugins disable pet-chat
hermes plugins remove pet-chat
```

Restart Hermes Desktop after removal. Pet Chat does not edit Hermes Desktop's
own plugin settings.

## Troubleshooting

- **Backend unreachable:** fully quit and reopen Hermes Desktop after
  installation or update.
- **Quips unavailable:** confirm that Hermes is v0.19.0.
- **No bubble:** confirm that a provider/model pair is saved and the pet is
  visible in the Hermes window.
- **Provider failed:** Pet Chat does not retry with another provider or model.
