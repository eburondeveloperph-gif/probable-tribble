# codemaxxx-cli

One-command CLI that bootstraps your local AI coding environment:

1. **Installs / updates Ollama** (via Homebrew or macOS app symlink)
2. **Pulls `eburonmax/codemax-v3`** model
3. **Installs OpenCode** (`opencode`) via `curl -fsSL https://opencode.ai/install | bash`
4. **Launches OpenCode through Ollama**: `ollama launch opencode --model eburonmax/codemax-v3`

---

## Quick Start

```bash
git clone https://github.com/eburondeveloperph-gif/probable-tribble.git codemaxxx-cli
cd codemaxxx-cli
bash install.sh        # symlinks CLI + wires zsh functions
codemaxxx              # bootstrap everything + launch
```

## CLI Usage

```
codemaxxx               Full bootstrap + launch
codemaxxx install       Install Ollama, pull model, install OpenCode (no launch)
codemaxxx launch        Quick launch (skip install steps)
codemaxxx pull          Pull / update the model only
codemaxxx help          Show help
```

## Zsh Functions

After install, two shell functions are available in any new terminal:

| Function             | Description                          |
|----------------------|--------------------------------------|
| `eburon_bootstrap`   | Full install + pull + launch         |
| `eburon_opencode`    | Quick launch with current model      |

## Change Model

```bash
export EBURON_OLLAMA_MODEL="eburonmax/codemax-v3"
```

Add to `~/.zshrc` to persist.

## Structure

```
codemaxxx-cli/
├── bin/
│   └── codemaxxx                  # Main CLI (bash)
├── zsh/
│   └── eburon_bootstrap.zsh      # Zsh functions (sourced by .zshrc)
├── install.sh                     # Installer
└── README.md
```

## Requirements

- macOS (Homebrew recommended) or Linux
- Ollama v0.15+ (for `ollama launch` support)
- Internet connection (for model pull + OpenCode install)