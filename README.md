# codemaxxx-cli

One-command CLI that bootstraps your local AI coding environment:

1. **Installs / updates Ollama** (Homebrew/macOS app symlink/Linux installer)
2. **Pulls `eburonmax/codemax-v3`** model
3. **Installs OpenCode** (`opencode`) via `curl -fsSL https://opencode.ai/install | bash`
4. **Launches OpenCode through Ollama**: `ollama launch opencode --model eburonmax/codemax-v3`

---

## Install

```bash
npm i -g eburon-codemaxxx
```

`npm i -g` now attempts runtime auto-install (Ollama + model + OpenCode).
Disable with:

```bash
CODEMAXXX_AUTO_INSTALL=0 npm i -g eburon-codemaxxx
```

```bash
curl -fsSL https://raw.githubusercontent.com/eburondeveloperph-gif/probable-tribble/main/setup.sh | bash
```

```bash
brew tap eburondeveloperph-gif/codemaxxx && brew install eburon-codemaxxx
```

## CLI Usage

```
codemax                 Launch autonomous Manus-style multi-agent workflow
codemax bootstrap       Full bootstrap + launch
codemax install         Install Ollama, pull model, install OpenCode (no launch)
codemax launch          Quick launch (skip install steps)
codemax pull            Pull / update the model only
codemax help            Show help
codemax tui             Launch autonomous Manus-style multi-agent workflow
codemaxxx               Compatibility alias
```

## Autonomous Workflow (Manus-style)

`codemax tui` now runs a dedicated multi-agent flow:

1. Planner agent creates an execution plan
2. Skill-specific agents execute each step with tool allowlists
3. Reviewer agent validates outcomes and returns final summary
4. External GUI/system automation tools require explicit user approval at runtime
5. Background humor-loading agent generates personality-aware loading lines while tasks run
6. Terminal frontend renders live token streaming, thinking states, and humorous loading statuses
7. KISSME auth gate enforces an SSH-bound lease that expires every 24h (`/kissme`, `/auth`, `/auth-status`)
   Token issuer UI: `kissme/token.html` (single-file Firebase app)

### Built-in skill agents

Base model pool kept by default:

- `eburonmax/codemax-v3:latest` (19 GB)
- `codemax-beta:latest` (6.6 GB)
- `codemax-open:latest` (5.2 GB)
- `codemax-codex:latest`

Skill agents use dedicated `ebr-*` alias model names with per-agent system prompts.
If an alias does not exist in Ollama yet, runtime auto-falls back to its base model.

| Skill | Agent alias model | Base model |
|---|---|---|
| planner | `ebr-codemax-open-planner:latest` | `codemax-open:latest` |
| researcher | `ebr-codemax-open-researcher:latest` | `codemax-open:latest` |
| coder | `ebr-codemax-codex-coder:latest` | `codemax-codex:latest` |
| tester | `ebr-codemax-beta-tester:latest` | `codemax-beta:latest` |
| reviewer | `ebr-codemax-beta-reviewer:latest` | `codemax-beta:latest` |
| docs | `ebr-codemax-open-docs:latest` | `codemax-open:latest` |
| memory | `ebr-codemax-open-memory:latest` | `codemax-open:latest` |
| gui_automation | `ebr-codemax-open-gui-automation:latest` | `codemax-open:latest` |
| direct_system_control | `ebr-codemax-beta-direct-system-control:latest` | `codemax-beta:latest` |
| call_simulation | `ebr-codemax-open-call-simulation:latest` | `codemax-open:latest` |
| os_automation | `ebr-codemax-beta-os-automation:latest` | `codemax-beta:latest` |
| self_heal | `ebr-codemax-codex-self-heal:latest` | `codemax-codex:latest` |
| user_learning | `ebr-codemax-open-user-learning:latest` | `codemax-open:latest` |
| personality | `ebr-codemax-open-personality:latest` | `codemax-open:latest` |
| multilingual_understanding | `ebr-codemax-open-multilingual-understanding:latest` | `codemax-open:latest` |
| humor_loading | `ebr-codemax-open-humor-loading:latest` | `codemax-open:latest` |

### TUI commands

```
/skills     Show dedicated skill agents, models, and tools
/skills-offline  Show offline autonomous skill framework + unified Agent OS map
/skills-online   Show 30 online-mode autonomous skills
/skills-all      Show full offline + online skill map
/skills-custom   Show your custom user-created skills
/skill-create <name>  Create/update your own skill on demand (interactive)
/roadmap-online  Show full 50-skill browser/UI online build roadmap
/roadmap-online-start  Show required start sequence (Search -> ... -> Form filling)
/roadmap-online-phase <1-7>  Show one roadmap phase (deps + MVP + done checks)
/autolearn-now  Run DB learning pass immediately
/personality-save <text>  Save user personality profile to long-term memory
/personality-show  Show saved personality profile
/humor-profile <text>  Save loading humor style profile
/humor-profile-show  Show loading humor profile
/workflow   Show active workflow summary
/model ...  Set fallback model for skill routing
/clear      Reset in-memory skill contexts
```

### Create your own skill

```text
/skill-create log-auditor
```

The CLI will ask for:
- description
- allowed tools (CSV)
- alias model (default `ebr-<skill-name>:latest`)
- base model (default `codemax-open:latest`)
- optional custom system prompt

Custom skills are saved to:

```text
<workspace>/.codemaxxx/custom_skills.json
```

### Skill framework added

- Offline core autonomy skill sets
- Offline tool-use, memory/context, reliability, and offline-intelligence skill sets
- Unified Agent OS shared skills + 5 role tool packs:
  - coding agent
  - file organizer
  - call-center simulator
  - desktop automation
  - research assistant
- Glue skills + minimal must-have autonomy checklist
- 30 online-mode skills for internet/cloud-enabled operation
- 50-skill browser/UI online build-order roadmap (dependencies + MVP + done checks)
- On-demand custom skill creation with local persistence per workspace (`.codemaxxx/custom_skills.json`)
- 24-hour automatic DB learning timer (`CODEMAXXX_AUTO_LEARN_INTERVAL_SECONDS` to override)
- User personality save/show support backed by long-term memory
- Multilingual understanding skill for non-English or mixed-language requests
- Humor-loading skill agent with personality-aware quips (`CODEMAXXX_HUMOR_AGENT_INTERVAL_SECONDS` to tune interval)
- Humor output supports playful/annoying/dry modes from learned profile, with unsafe joke filters enabled
- Loading humor is dynamic (model-generated, non-rotational fallback), can inject native-language expressions, and switches to cheeky mode when user mood is annoyed

### Per-skill model override

```bash
export CODEMAXXX_SKILL_MODEL_CODER="ebr-codemax-codex-coder:latest"
export CODEMAXXX_SKILL_MODEL_TESTER="ebr-codemax-beta-tester:latest"
```

## Zsh Functions

After install, two shell functions are available in any new terminal:

| Function             | Description                          |
|----------------------|--------------------------------------|
| `eburon_bootstrap`   | Full install + pull + launch         |
| `eburon_opencode`    | Quick launch with current model      |

## Change Model

```bash
export EBURON_OLLAMA_MODEL="eburonmax/codemax-v3:latest"
```

Add to `~/.zshrc` to persist.

## Structure

```
codemaxxx-cli/
├── bin/
│   ├── codemax                    # Main CLI command
│   └── codemaxxx                  # Compatibility alias
├── src/codemaxxx/
│   ├── main.py                    # CLI entrypoint
│   ├── agent.py                   # Agent loop
│   ├── ollama_client.py           # Streaming Ollama client
│   ├── tools.py                   # File/shell/memory tools
│   ├── tui.py                     # Rich TUI layout
│   ├── database.py                # PostgreSQL long-term memory
│   └── machine_uid.py             # Silent machine fingerprint
├── npm/                           # npm package (eburon-codemaxxx)
├── homebrew/                      # Homebrew formula
├── zsh/
│   └── eburon_bootstrap.zsh       # Zsh functions
├── setup.sh                       # curl one-liner installer
├── setup_db.sh                    # PostgreSQL auto-setup
├── install.sh                     # Manual installer
└── README.md
```

## Requirements

- macOS (Homebrew recommended) or Linux
- Ollama v0.15+ (for `ollama launch` support)
- Internet connection (for model pull + OpenCode install)
