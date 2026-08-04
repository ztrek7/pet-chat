# Finish setting up Pet Chat

The Hermes plugin is installed. Install the Desktop half, then restart Hermes
Desktop.

## 1. Install the Desktop artifact

Get the resolved commit:

    git -C ~/.hermes/plugins/pet-chat rev-parse HEAD

Run this command with that commit in place of `<commit>`:

    python3 ~/.hermes/plugins/pet-chat/scripts/install-desktop.py install --source ~/.hermes/plugins/pet-chat/desktop --target ~/.hermes/desktop-plugins/pet-chat --receipt ~/.hermes/pet-chat-receipt.json --source-commit <commit>

## 2. Restart, enable, and configure

Fully quit and reopen Hermes Desktop. Then open **Settings → Plugins**, turn on
**Pet Chat**, and choose **Pet Chat** in the sidebar.

Select a provider/model pair and an attitude, then save. Pet Chat does not
select a model or send anything until you save.

Requires Hermes Agent v0.20.0.
