#!/bin/sh
# Installa i git hook del progetto OP-NEUROTRIGGER.
# I hook vivono versionati in tools/ e vengono collegati in .git/hooks/.
REPO="$(git rev-parse --show-toplevel)" || exit 1
ln -sf ../../tools/pre-commit "$REPO/.git/hooks/pre-commit"
chmod +x "$REPO/tools/pre-commit"
echo "✓ Hook installato: .git/hooks/pre-commit → tools/pre-commit"
