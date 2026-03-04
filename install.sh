#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  install.sh — Install codemax CLI + wire zsh bootstrap into shell
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  📦  codemax Installer"
echo "  ───────────────────────"
echo ""

# 1. Make the CLI executable and symlink into PATH
chmod +x "${SCRIPT_DIR}/bin/codemax"
chmod +x "${SCRIPT_DIR}/bin/codemaxxx"

if [[ -d /usr/local/bin ]]; then
  LINK_DIR="/usr/local/bin"
else
  LINK_DIR="${HOME}/.local/bin"
  mkdir -p "$LINK_DIR"
fi

echo "  → Linking codemax (primary) and codemaxxx (compat) into ${LINK_DIR}"
if [[ -w "$LINK_DIR" ]]; then
  ln -sf "${SCRIPT_DIR}/bin/codemax" "${LINK_DIR}/codemax"
  ln -sf "${SCRIPT_DIR}/bin/codemaxxx" "${LINK_DIR}/codemaxxx"
else
  sudo ln -sf "${SCRIPT_DIR}/bin/codemax" "${LINK_DIR}/codemax"
  sudo ln -sf "${SCRIPT_DIR}/bin/codemaxxx" "${LINK_DIR}/codemaxxx"
fi

# 2. Install zsh bootstrap
echo "  → Installing zsh bootstrap to ~/.zsh/eburon_bootstrap.zsh"
mkdir -p "${HOME}/.zsh"
cp -f "${SCRIPT_DIR}/zsh/eburon_bootstrap.zsh" "${HOME}/.zsh/eburon_bootstrap.zsh"

# 3. Wire into .zshrc (idempotent)
ZSHRC="${HOME}/.zshrc"
[[ -f "$ZSHRC" ]] || touch "$ZSHRC"

if ! grep -q 'source "$HOME/.zsh/eburon_bootstrap.zsh"' "$ZSHRC"; then
  printf '\n# Eburon bootstrap (Ollama + OpenCode)\nsource "$HOME/.zsh/eburon_bootstrap.zsh"\n' >> "$ZSHRC"
  echo "  → Added source line to ~/.zshrc"
else
  echo "  → ~/.zshrc already configured"
fi

echo ""
echo "  ✅  Installed!  You now have:"
echo ""
echo "     codemax                 full bootstrap + launch"
echo "     codemax install         install everything"
echo "     codemax launch          quick launch"
echo "     codemax pull            update the model"
echo "     codemaxxx               compatibility alias"
echo ""
echo "     eburon_bootstrap        (zsh function) full bootstrap + launch"
echo "     eburon_opencode         (zsh function) quick launch"
echo ""
echo "  Run 'source ~/.zshrc' or open a new terminal, then:"
echo "     codemax"
echo ""
