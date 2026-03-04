# ~/.zsh/eburon_bootstrap.zsh
# Eburon bootstrap: Ollama update/install -> pull model -> install opencode -> launch via ollama launch

export EBURON_OLLAMA_MODEL="${EBURON_OLLAMA_MODEL:-eburonmax/codemax-v3}"

eburon_bootstrap() {
  emulate -L zsh
  setopt errexit nounset pipefail

  local model="${EBURON_OLLAMA_MODEL}"

  echo "🚀 [Eburon] Starting bootstrap..."
  echo "   • Model: ${model}"

  # ── Step 1: Update / Install Ollama ──────────────────────────────
  echo "🔧 [1/4] Updating/Installing Ollama..."

  if command -v brew >/dev/null 2>&1; then
    brew update
    if brew list --formula ollama >/dev/null 2>&1; then
      brew upgrade ollama || true
    else
      brew install ollama
    fi
  fi

  # Wire Ollama.app CLI if Homebrew didn't provide it
  if ! command -v ollama >/dev/null 2>&1; then
    if [[ -x "/Applications/Ollama.app/Contents/Resources/ollama" ]]; then
      echo "🔗 Ollama.app detected. Creating /usr/local/bin/ollama symlink (may prompt for sudo)..."
      sudo mkdir -p /usr/local/bin
      sudo ln -sf "/Applications/Ollama.app/Contents/Resources/ollama" /usr/local/bin/ollama
    fi
  fi

  if ! command -v ollama >/dev/null 2>&1; then
    echo "❌ ERROR: ollama not found in PATH."
    echo "   Install via Homebrew (recommended) or install Ollama.app and ensure the CLI is linked in PATH."
    return 1
  fi

  # ── Step 2: Ensure Ollama server is running ──────────────────────
  echo "🟢 [2/4] Ensuring Ollama server is running..."
  if ! ollama ps >/dev/null 2>&1; then
    nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
    sleep 2
  fi

  # ── Step 3: Pull the model ──────────────────────────────────────
  echo "📦 [3/4] Pulling model: ${model}"
  ollama pull "${model}"

  # ── Step 4: Install OpenCode ─────────────────────────────────────
  echo "⬇️  [4/4] Installing OpenCode (opencode) via curl if missing..."
  if ! command -v opencode >/dev/null 2>&1; then
    curl -fsSL https://opencode.ai/install | bash
    hash -r 2>/dev/null || true
    rehash 2>/dev/null || true
  fi

  if ! command -v opencode >/dev/null 2>&1; then
    echo "⚠️  opencode still not found in PATH."
    echo "   Open a new terminal, or run: source ~/.zshrc"
  fi

  # ── Launch ───────────────────────────────────────────────────────
  echo "🎯 Launching: ollama launch opencode --model ${model}"
  if ! ollama launch --help >/dev/null 2>&1; then
    echo "❌ ERROR: 'ollama launch' not available."
    echo "   Update Ollama to a version that supports Launch (v0.15+)."
    return 1
  fi

  ollama launch opencode --model "${model}"
}

# Convenience: just launch (assumes already installed/pulled)
eburon_opencode() {
  emulate -L zsh
  setopt errexit nounset pipefail
  local model="${EBURON_OLLAMA_MODEL}"
  ollama launch opencode --model "${model}"
}
