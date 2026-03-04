#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  codemaxxx one-liner bootstrap
#  curl -fsSL https://raw.githubusercontent.com/eburondeveloperph-gif/probable-tribble/main/setup.sh | bash
#
#  1) Clones the repo + installs codemaxxx CLI
#  2) Installs/updates Ollama
#  3) Pulls eburonmax/codemax-v3
#  4) Installs OpenCode
#  5) Launches OpenCode through Ollama
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

MODEL="${EBURON_OLLAMA_MODEL:-eburonmax/codemax-v3}"
INSTALL_DIR="${HOME}/.codemaxxx"
REPO="https://github.com/eburondeveloperph-gif/probable-tribble.git"

info()  { printf '  \033[1;34mℹ\033[0m  %s\n' "$*"; }
ok()    { printf '  \033[1;32m✔\033[0m  %s\n' "$*"; }
warn()  { printf '  \033[1;33m⚠\033[0m  %s\n' "$*" >&2; }
die()   { printf '  \033[1;31m✖\033[0m  %s\n' "$*" >&2; exit 1; }

echo ""
echo "  🚀  codemaxxx — One-Line Bootstrap"
echo "  ───────────────────────────────────"
echo "  Model : ${MODEL}"
echo "  Install: ${INSTALL_DIR}"
echo ""

# ── 0. Clone repo + install codemaxxx CLI ──────────────────────────
info "[0/4] Installing codemaxxx CLI..."
if [[ -d "${INSTALL_DIR}/.git" ]]; then
  git -C "${INSTALL_DIR}" pull --quiet 2>/dev/null || true
else
  rm -rf "${INSTALL_DIR}"
  git clone --quiet "${REPO}" "${INSTALL_DIR}"
fi
chmod +x "${INSTALL_DIR}/bin/codemaxxx"

# Symlink into PATH
BIN_LINK="/usr/local/bin/codemaxxx"
if [[ -w /usr/local/bin ]] 2>/dev/null; then
  ln -sf "${INSTALL_DIR}/bin/codemaxxx" "${BIN_LINK}"
elif [[ -d /usr/local/bin ]]; then
  sudo ln -sf "${INSTALL_DIR}/bin/codemaxxx" "${BIN_LINK}"
else
  mkdir -p "${HOME}/.local/bin"
  ln -sf "${INSTALL_DIR}/bin/codemaxxx" "${HOME}/.local/bin/codemaxxx"
  export PATH="${HOME}/.local/bin:${PATH}"
fi

# Install zsh bootstrap functions
mkdir -p "${HOME}/.zsh"
cp -f "${INSTALL_DIR}/zsh/eburon_bootstrap.zsh" "${HOME}/.zsh/eburon_bootstrap.zsh"
ZSHRC="${HOME}/.zshrc"
[[ -f "${ZSHRC}" ]] || touch "${ZSHRC}"
if ! grep -q 'source "$HOME/.zsh/eburon_bootstrap.zsh"' "${ZSHRC}" 2>/dev/null; then
  printf '\n# Eburon bootstrap (Ollama + OpenCode)\nsource "$HOME/.zsh/eburon_bootstrap.zsh"\n' >> "${ZSHRC}"
fi
ok "codemaxxx CLI installed"

# ── 0b. Set up Python TUI agent ───────────────────────────────────
info "Setting up CodeMaxxx TUI agent (Python)..."
if command -v python3 >/dev/null 2>&1; then
  if [[ ! -d "${INSTALL_DIR}/.venv" ]]; then
    python3 -m venv "${INSTALL_DIR}/.venv"
  fi
  "${INSTALL_DIR}/.venv/bin/pip" install --quiet -e "${INSTALL_DIR}" 2>/dev/null || \
  "${INSTALL_DIR}/.venv/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt" 2>/dev/null || true
  ok "TUI agent ready (run: codemaxxx tui)"
else
  warn "python3 not found — TUI agent skipped (install Python 3.10+)"
fi

# ── 1. Ollama ──────────────────────────────────────────────────────
info "[1/4] Installing / updating Ollama..."
if command -v brew >/dev/null 2>&1; then
  brew update --quiet
  if brew list --formula ollama >/dev/null 2>&1; then
    brew upgrade ollama 2>/dev/null || true
  else
    brew install ollama
  fi
elif ! command -v ollama >/dev/null 2>&1; then
  if [[ -x "/Applications/Ollama.app/Contents/Resources/ollama" ]]; then
    sudo mkdir -p /usr/local/bin
    sudo ln -sf "/Applications/Ollama.app/Contents/Resources/ollama" /usr/local/bin/ollama
  else
    curl -fsSL https://ollama.com/install.sh | sh
  fi
fi
command -v ollama >/dev/null 2>&1 || die "ollama not found — install from https://ollama.com/download"
ok "Ollama ready"

# ── 2. Server ──────────────────────────────────────────────────────
info "[2/4] Ensuring Ollama server is running..."
if ! ollama ps >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1 && brew services list 2>/dev/null | grep -q 'ollama.*started'; then
    ok "Server running via brew services"
  else
    nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
    sleep 3
  fi
fi
ok "Server running"

# ── 3. Model ──────────────────────────────────────────────────────
info "[3/4] Pulling ${MODEL}..."
ollama pull "${MODEL}"
ok "Model ready"

# ── 4. OpenCode ────────────────────────────────────────────────────
info "[4/4] Installing OpenCode..."
if ! command -v opencode >/dev/null 2>&1; then
  curl -fsSL https://opencode.ai/install | bash
  hash -r 2>/dev/null || true
fi
if command -v opencode >/dev/null 2>&1; then
  ok "OpenCode ready"
else
  warn "opencode not in PATH yet — open a new terminal if launch fails"
fi

# ── Launch ─────────────────────────────────────────────────────────
echo ""
ok "All set! Launching OpenCode with ${MODEL}..."
echo ""
if ollama launch --help >/dev/null 2>&1; then
  exec ollama launch opencode --model "${MODEL}"
else
  warn "'ollama launch' not available (needs Ollama v0.15+), falling back to opencode directly"
  if command -v opencode >/dev/null 2>&1; then
    exec opencode
  else
    echo ""
    ok "Installation complete! Run 'codemaxxx launch' in a new terminal."
  fi
fi
