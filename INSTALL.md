# Install Pet Chat

Requires Hermes Agent 0.22.5–0.22.x on macOS/Linux, a configured provider,
and a pet enabled **and selected** in Settings → Appearance → Pet.
This package targets native Hermes Desktop; it does not add a CLI pet or web UI.

```bash
hermes plugins install https://github.com/ztrek7/pet-chat --no-enable
hermes plugins show pet-chat
hermes plugins enable pet-chat
```

Review the exact revision before enabling. For a named profile, add Hermes'
global `-p PROFILE` before `plugins`. The backend uses that profile's config.
No provider/model is selected by installation or enablement.

Desktop: **Capabilities → Plugins → Rescan**, then enable Pet Chat there too.
The two switches are intentional. Follow Hermes' activation notice; if routes
remain unavailable, fully quit and reopen Desktop when safe. Open Pet Chat,
choose an exact provider/model and attitude, and save. Provider charges apply.

The host manages the Desktop copy from `desktop/plugin.js`; do not copy it by
hand. Remote backends also need the UI installed on the Desktop machine.

## Update and remove

```bash
hermes plugins check-updates
hermes plugins update pet-chat
hermes plugins disable pet-chat
hermes plugins remove pet-chat
```

Turn off the Desktop component before removal. Rescan afterwards; follow the
host's activation notice. Updates preserve configuration and disabled state.
Removal does not promise to purge retained auxiliary settings or plugin data.

For a reviewed pinned install, add `--ref FULL_COMMIT_SHA` to `install`.
Pinned installs do not advance with `update`: review a new SHA, then explicitly
reinstall with `install SOURCE --force --ref NEW_SHA`. Back up configuration
before migration. No script here restarts Hermes or edits its permission grants.

## Older two-copy installs

A host-owned copy has `.hermes-package.json`; let Hermes manage it. A standalone
legacy copy without that marker can shadow the unified package. Inspect it first.
Only Pet Chat's receipt-owned legacy copy can be removed using:

```bash
python3 /path/to/pet-chat/scripts/uninstall.py \
  --target /path/to/desktop-plugins/pet-chat \
  --receipt /path/to/pet-chat-receipt.json
```

Use the actual app-root path and receipt, not a guessed profile path. A receipt
mismatch means stop and review, not delete forcibly. Preserve local changes.

## Verification

See [COMPATIBILITY.md](COMPATIBILITY.md). Desktop visual operation and paid
provider calls remain unverified. Missing native pet API, hidden pets, an unset
pair, or an unsupported host produce no quip. Failed generation never falls
back to another provider/model.
