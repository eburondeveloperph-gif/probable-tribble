#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  codemaxxx one-liner bootstrap
#  curl -fsSL https://raw.githubusercontent.com/eburondeveloperph-gif/probable-tribble/main/setup.sh | bash
#
#  Installs Ollama → pulls eburonmax/codemax-v3 → installs OpenCode → launches
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

MODEL="${EBURON_OLLAMA_MODEL:-eburonmax/codemax-v3}"

info()  { printf '  \033[1;34mℹ\033[0m  %s\n' "$*"; }
ok()    { printf '  \033[1;32m✔\033[0m  %s\n' "$*"; }
warn()  { printf '  \033[1;33m⚠\033[0m  %s\n' "$*" >&2; }
err()   { printf '  \033[1;31m✖\033[0m  %s\n' "$*" >&2; exit 1; }

echo ""
echo "  🚀  codemaxxx — One-Line Bootstrap"
echo "  ───────────────────────────────────"
echo "  Model: ${MODEL}"
echo ""

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
command -v ollama >/dev/null 2>&1 || err "ollama not found — install from https://ollama.com/download"
ok "Ollama ready"

# ── 2. Server ──────────────────────────────────────────────────────
info "[2/4] Ensuring Ollama server is running..."
if ! ollama ps >/dev/null 2>&1; then
  nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
  sleep 2
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
ok "OpenCode ready"

# ── Launch ─────────────────────────────────────────────────────────
echo ""
ok "All set! Launching OpenCode with ${MODEL}..."
echo ""
if ollama launch --help >/dev/null 2>&1; then
  exec ollama launch opencode --model "${MODEL}"
else
  warn "'ollama launch' not available (needs Ollama v0.15+), falling back to opencode directly"
  exec opencode
fi
