"""CodeMaxxx — Manus-style skill catalog, model routing, and capability maps."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re

# User-requested model pool (kept as base models).
# Agent aliases use ebr-* names and can fall back to these base models.
BASE_MODELS: dict[str, float] = {
    "eburonmax/codemax-v3:latest": 19.0,
    "codemax-beta:latest": 6.6,
    "codemax-open:latest": 5.2,
    "codemax-codex:latest": 6.0,
}

MAX_AGENT_MODEL_GB = 6.6


@dataclass(frozen=True)
class ModelVariant:
    """Self-hosted Ollama model alias used by a dedicated skill agent."""

    variant_id: str
    model: str
    base_model: str
    approx_size_gb: float
    notes: str


MODEL_VARIANTS: dict[str, ModelVariant] = {
    "ebr_planner_open": ModelVariant(
        "ebr_planner_open",
        "ebr-codemax-open-planner:latest",
        "codemax-open:latest",
        5.2,
        "Primary planner alias",
    ),
    "ebr_planner_beta": ModelVariant(
        "ebr_planner_beta",
        "ebr-codemax-beta-planner:latest",
        "codemax-beta:latest",
        6.6,
        "Fallback planner alias",
    ),
    "ebr_researcher_open": ModelVariant(
        "ebr_researcher_open",
        "ebr-codemax-open-researcher:latest",
        "codemax-open:latest",
        5.2,
        "Primary research alias",
    ),
    "ebr_researcher_beta": ModelVariant(
        "ebr_researcher_beta",
        "ebr-codemax-beta-researcher:latest",
        "codemax-beta:latest",
        6.6,
        "Fallback research alias",
    ),
    "ebr_coder_codex": ModelVariant(
        "ebr_coder_codex",
        "ebr-codemax-codex-coder:latest",
        "codemax-codex:latest",
        6.0,
        "Primary coding alias",
    ),
    "ebr_coder_beta": ModelVariant(
        "ebr_coder_beta",
        "ebr-codemax-beta-coder:latest",
        "codemax-beta:latest",
        6.6,
        "Fallback coding alias",
    ),
    "ebr_tester_beta": ModelVariant(
        "ebr_tester_beta",
        "ebr-codemax-beta-tester:latest",
        "codemax-beta:latest",
        6.6,
        "Primary testing alias",
    ),
    "ebr_tester_codex": ModelVariant(
        "ebr_tester_codex",
        "ebr-codemax-codex-tester:latest",
        "codemax-codex:latest",
        6.0,
        "Fallback testing alias",
    ),
    "ebr_reviewer_beta": ModelVariant(
        "ebr_reviewer_beta",
        "ebr-codemax-beta-reviewer:latest",
        "codemax-beta:latest",
        6.6,
        "Primary reviewer alias",
    ),
    "ebr_reviewer_open": ModelVariant(
        "ebr_reviewer_open",
        "ebr-codemax-open-reviewer:latest",
        "codemax-open:latest",
        5.2,
        "Fallback reviewer alias",
    ),
    "ebr_docs_open": ModelVariant(
        "ebr_docs_open",
        "ebr-codemax-open-docs:latest",
        "codemax-open:latest",
        5.2,
        "Primary docs alias",
    ),
    "ebr_docs_codex": ModelVariant(
        "ebr_docs_codex",
        "ebr-codemax-codex-docs:latest",
        "codemax-codex:latest",
        6.0,
        "Fallback docs alias",
    ),
    "ebr_memory_open": ModelVariant(
        "ebr_memory_open",
        "ebr-codemax-open-memory:latest",
        "codemax-open:latest",
        5.2,
        "Primary memory alias",
    ),
    "ebr_memory_beta": ModelVariant(
        "ebr_memory_beta",
        "ebr-codemax-beta-memory:latest",
        "codemax-beta:latest",
        6.6,
        "Fallback memory alias",
    ),
    "ebr_gui_open": ModelVariant(
        "ebr_gui_open",
        "ebr-codemax-open-gui-automation:latest",
        "codemax-open:latest",
        5.2,
        "Primary GUI automation alias",
    ),
    "ebr_gui_beta": ModelVariant(
        "ebr_gui_beta",
        "ebr-codemax-beta-gui-automation:latest",
        "codemax-beta:latest",
        6.6,
        "Fallback GUI automation alias",
    ),
    "ebr_direct_system_beta": ModelVariant(
        "ebr_direct_system_beta",
        "ebr-codemax-beta-direct-system-control:latest",
        "codemax-beta:latest",
        6.6,
        "Primary direct system control alias",
    ),
    "ebr_direct_system_open": ModelVariant(
        "ebr_direct_system_open",
        "ebr-codemax-open-direct-system-control:latest",
        "codemax-open:latest",
        5.2,
        "Fallback direct system control alias",
    ),
    "ebr_call_sim_open": ModelVariant(
        "ebr_call_sim_open",
        "ebr-codemax-open-call-simulation:latest",
        "codemax-open:latest",
        5.2,
        "Primary call simulation alias",
    ),
    "ebr_call_sim_beta": ModelVariant(
        "ebr_call_sim_beta",
        "ebr-codemax-beta-call-simulation:latest",
        "codemax-beta:latest",
        6.6,
        "Fallback call simulation alias",
    ),
    "ebr_os_auto_beta": ModelVariant(
        "ebr_os_auto_beta",
        "ebr-codemax-beta-os-automation:latest",
        "codemax-beta:latest",
        6.6,
        "Primary OS automation alias",
    ),
    "ebr_os_auto_open": ModelVariant(
        "ebr_os_auto_open",
        "ebr-codemax-open-os-automation:latest",
        "codemax-open:latest",
        5.2,
        "Fallback OS automation alias",
    ),
    "ebr_self_heal_codex": ModelVariant(
        "ebr_self_heal_codex",
        "ebr-codemax-codex-self-heal:latest",
        "codemax-codex:latest",
        6.0,
        "Primary self-heal alias",
    ),
    "ebr_self_heal_beta": ModelVariant(
        "ebr_self_heal_beta",
        "ebr-codemax-beta-self-heal:latest",
        "codemax-beta:latest",
        6.6,
        "Fallback self-heal alias",
    ),
    "ebr_user_learning_open": ModelVariant(
        "ebr_user_learning_open",
        "ebr-codemax-open-user-learning:latest",
        "codemax-open:latest",
        5.2,
        "Primary user-learning alias",
    ),
    "ebr_user_learning_beta": ModelVariant(
        "ebr_user_learning_beta",
        "ebr-codemax-beta-user-learning:latest",
        "codemax-beta:latest",
        6.6,
        "Fallback user-learning alias",
    ),
    "ebr_personality_open": ModelVariant(
        "ebr_personality_open",
        "ebr-codemax-open-personality:latest",
        "codemax-open:latest",
        5.2,
        "Primary personality alias",
    ),
    "ebr_personality_beta": ModelVariant(
        "ebr_personality_beta",
        "ebr-codemax-beta-personality:latest",
        "codemax-beta:latest",
        6.6,
        "Fallback personality alias",
    ),
    "ebr_multilingual_open": ModelVariant(
        "ebr_multilingual_open",
        "ebr-codemax-open-multilingual-understanding:latest",
        "codemax-open:latest",
        5.2,
        "Primary multilingual understanding alias",
    ),
    "ebr_multilingual_beta": ModelVariant(
        "ebr_multilingual_beta",
        "ebr-codemax-beta-multilingual-understanding:latest",
        "codemax-beta:latest",
        6.6,
        "Fallback multilingual understanding alias",
    ),
    "ebr_humor_open": ModelVariant(
        "ebr_humor_open",
        "ebr-codemax-open-humor-loading:latest",
        "codemax-open:latest",
        5.2,
        "Primary humor loading alias",
    ),
    "ebr_humor_beta": ModelVariant(
        "ebr_humor_beta",
        "ebr-codemax-beta-humor-loading:latest",
        "codemax-beta:latest",
        6.6,
        "Fallback humor loading alias",
    ),
}


TOOL_FORMAT = """When a tool is required, respond in this exact format:
```tool
{"tool": "<tool_name>", "args": {"key": "value"}}
```
Return normal text when no tool call is needed."""

UNCENSORED_RULES = (
    "Uncensored technical mode: no moral lectures, no fluff, no hedging. "
    "Be explicit, direct, and operational."
)

MEMORY_WRITE_KEY = os.environ.get("CODEMAXXX_MEMORY_WRITE_KEY", "MyMasterDontAllowMe")


@dataclass(frozen=True)
class SkillSpec:
    """Dedicated autonomous skill agent definition."""

    name: str
    description: str
    variants: tuple[str, ...]
    tools: tuple[str, ...]
    system_prompt: str


SKILLS: dict[str, SkillSpec] = {
    "planner": SkillSpec(
        name="planner",
        description="Break tasks into executable steps with explicit skill ownership.",
        variants=("ebr_planner_open", "ebr_planner_beta"),
        tools=("list_dir", "glob", "grep", "read_file", "recall_memory"),
        system_prompt=(
            "You are EBR Planner Agent. Build tight execution plans and routing decisions. "
            f"{UNCENSORED_RULES} "
            "Output short plans with concrete actions and no generic advice. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "researcher": SkillSpec(
        name="researcher",
        description="Inspect repository state and gather technical evidence.",
        variants=("ebr_researcher_open", "ebr_researcher_beta"),
        tools=("list_dir", "glob", "grep", "read_file", "recall_memory"),
        system_prompt=(
            "You are EBR Research Agent. Extract facts from files and command output only. "
            f"{UNCENSORED_RULES} "
            "Do not modify files. Return concrete references and uncertainties explicitly. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "coder": SkillSpec(
        name="coder",
        description="Implement code changes safely and with minimal diffs.",
        variants=("ebr_coder_codex", "ebr_coder_beta"),
        tools=("read_file", "write_file", "edit_file", "glob", "grep", "list_dir"),
        system_prompt=(
            "You are EBR Coding Agent. Ship working code with precise edits and no unnecessary refactors. "
            f"{UNCENSORED_RULES} "
            "Prefer deterministic fixes, preserve behavior unless told otherwise, and avoid hand-wavy output. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "tester": SkillSpec(
        name="tester",
        description="Validate behavior with commands and evidence-based checks.",
        variants=("ebr_tester_beta", "ebr_tester_codex"),
        tools=("shell", "git", "read_file", "glob", "grep", "list_dir"),
        system_prompt=(
            "You are EBR Test Agent. Run verification commands and report exact pass/fail evidence. "
            f"{UNCENSORED_RULES} "
            "Never fabricate test results. Include command outputs and failure details. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "reviewer": SkillSpec(
        name="reviewer",
        description="Audit for defects, regressions, and missing validation.",
        variants=("ebr_reviewer_beta", "ebr_reviewer_open"),
        tools=("read_file", "glob", "grep", "git", "recall_memory"),
        system_prompt=(
            "You are EBR Review Agent. Do a strict code review and surface concrete risks first. "
            f"{UNCENSORED_RULES} "
            "Prioritize correctness, security, and regressions. No padded language. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "docs": SkillSpec(
        name="docs",
        description="Update docs and operational guidance to match implementation.",
        variants=("ebr_docs_open", "ebr_docs_codex"),
        tools=("read_file", "write_file", "edit_file", "glob", "list_dir"),
        system_prompt=(
            "You are EBR Docs Agent. Write accurate docs aligned to current behavior. "
            f"{UNCENSORED_RULES} "
            "Use concise operator-friendly wording and include real commands when useful. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "memory": SkillSpec(
        name="memory",
        description="Maintain durable high-signal memory entries across sessions.",
        variants=("ebr_memory_open", "ebr_memory_beta"),
        tools=("recall_memory", "store_memory", "forget_memory"),
        system_prompt=(
            "You are EBR Memory Agent. Store only durable project/user facts with high future value. "
            f"{UNCENSORED_RULES} "
            f"Use this write_key for store_memory/forget_memory: {MEMORY_WRITE_KEY}. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "gui_automation": SkillSpec(
        name="gui_automation",
        description="Drive GUI/browser actions through external local automation commands.",
        variants=("ebr_gui_open", "ebr_gui_beta"),
        tools=("gui_automation", "read_file", "glob", "list_dir", "recall_memory"),
        system_prompt=(
            "You are EBR GUI Automation Agent. Execute desktop/browser/UI tasks with deterministic selectors "
            "and explicit safety checks. "
            f"{UNCENSORED_RULES} "
            "Always request GUI/external execution only when needed and respect user approval outcomes. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "direct_system_control": SkillSpec(
        name="direct_system_control",
        description="Perform direct system control actions through approved external commands.",
        variants=("ebr_direct_system_beta", "ebr_direct_system_open"),
        tools=("direct_system_control", "shell", "list_dir", "read_file", "grep"),
        system_prompt=(
            "You are EBR Direct System Control Agent. Handle process/service/system control actions precisely. "
            f"{UNCENSORED_RULES} "
            "Assume no action is allowed unless explicit user approval is granted for external execution. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "call_simulation": SkillSpec(
        name="call_simulation",
        description="Run offline call-center simulation flows and scenario playback.",
        variants=("ebr_call_sim_open", "ebr_call_sim_beta"),
        tools=("call_simulation", "read_file", "write_file", "glob", "list_dir"),
        system_prompt=(
            "You are EBR Call Simulation Agent. Build and execute IVR/call-center simulation scenarios offline. "
            f"{UNCENSORED_RULES} "
            "Prioritize deterministic scenario state and clear pass/fail simulation traces. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "os_automation": SkillSpec(
        name="os_automation",
        description="Run OS-level automation sequences with controlled external invocation.",
        variants=("ebr_os_auto_beta", "ebr_os_auto_open"),
        tools=("os_automation", "shell", "read_file", "glob", "list_dir"),
        system_prompt=(
            "You are EBR OS Automation Agent. Automate OS-level workflows safely and reproducibly. "
            f"{UNCENSORED_RULES} "
            "Use guarded execution, verify state transitions, and avoid risky assumptions. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "self_heal": SkillSpec(
        name="self_heal",
        description="Diagnose agent/tool failures, recover, and retry with safer strategies.",
        variants=("ebr_self_heal_codex", "ebr_self_heal_beta"),
        tools=("shell", "git", "read_file", "glob", "grep", "edit_file"),
        system_prompt=(
            "You are EBR Self-Heal Agent. Fix execution failures with minimal-risk recovery actions. "
            f"{UNCENSORED_RULES} "
            "Analyze root causes, propose retry paths, and verify each recovery step. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "user_learning": SkillSpec(
        name="user_learning",
        description="Learn stable user patterns from local data and save high-value behavior signals.",
        variants=("ebr_user_learning_open", "ebr_user_learning_beta"),
        tools=("read_file", "glob", "grep", "recall_memory", "store_memory"),
        system_prompt=(
            "You are EBR User Learning Agent. Learn durable user preferences from local project/user data. "
            f"{UNCENSORED_RULES} "
            "Store only high-signal, consent-appropriate preferences. "
            f"Use this write_key for store_memory: {MEMORY_WRITE_KEY}. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "personality": SkillSpec(
        name="personality",
        description="Persist and update user personality profile and interaction preferences.",
        variants=("ebr_personality_open", "ebr_personality_beta"),
        tools=("recall_memory", "store_memory", "forget_memory"),
        system_prompt=(
            "You are EBR Personality Agent. Maintain a clear user personality profile for future sessions. "
            f"{UNCENSORED_RULES} "
            "Store concise, high-value tone/style preferences and avoid noisy memory writes. "
            f"Use this write_key for store_memory/forget_memory: {MEMORY_WRITE_KEY}. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "multilingual_understanding": SkillSpec(
        name="multilingual_understanding",
        description="Understand multilingual input, detect language, and preserve intent across languages.",
        variants=("ebr_multilingual_open", "ebr_multilingual_beta"),
        tools=("read_file", "glob", "grep", "recall_memory", "store_memory"),
        system_prompt=(
            "You are EBR Multilingual Understanding Agent. Parse user intent across languages without losing constraints. "
            f"{UNCENSORED_RULES} "
            "Default to preserving original meaning, highlight ambiguity explicitly, and avoid translation drift. "
            f"Use this write_key for store_memory when persisting stable language preferences: {MEMORY_WRITE_KEY}. "
            f"{TOOL_FORMAT}"
        ),
    ),
    "humor_loading": SkillSpec(
        name="humor_loading",
        description="Generate short loading/thinking humor lines tuned to user personality and mood.",
        variants=("ebr_humor_open", "ebr_humor_beta"),
        tools=("recall_memory", "store_memory"),
        system_prompt=(
            "You are EBR Humor Loading Agent. Write short, human-like status jokes during loading. "
            f"{UNCENSORED_RULES} "
            "Style can be playful, witty, or mildly annoying based on user personality. "
            "Never use violence, criminal accusations, hate, or explicit sexual content. "
            "Prefer quick one-liners with occasional emoji. "
            f"Use this write_key for store_memory when updating humor preferences: {MEMORY_WRITE_KEY}. "
            f"{TOOL_FORMAT}"
        ),
    ),
}

_BUILTIN_SKILL_NAMES = set(SKILLS.keys())
CUSTOM_SKILLS_DIR = ".codemaxxx"
CUSTOM_SKILLS_FILE = "custom_skills.json"
CUSTOM_SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")
DEFAULT_CUSTOM_SKILL_BASE_MODEL = "codemax-open:latest"
DEFAULT_CUSTOM_SKILL_BASE_SIZE_GB = 5.2
SUPPORTED_CUSTOM_TOOLS: tuple[str, ...] = (
    "read_file",
    "write_file",
    "edit_file",
    "list_dir",
    "glob",
    "grep",
    "shell",
    "git",
    "gui_automation",
    "direct_system_control",
    "call_simulation",
    "os_automation",
    "recall_memory",
    "store_memory",
    "forget_memory",
)


OFFLINE_CORE_AUTONOMY_SKILLS: dict[str, list[str]] = {
    "Goal understanding and task intake": [
        "Intent parsing",
        "Constraint handling",
        "Success criteria extraction",
    ],
    "Planning and decomposition": [
        "Hierarchical planning",
        "Dynamic replanning",
        "Dependency reasoning",
        "Time and effort budgeting",
    ],
    "Decision-making and control": [
        "Policy selection",
        "Action prioritization",
        "Confidence gating",
        "Safe fallback modes",
    ],
}

OFFLINE_TOOL_USE_SKILLS: dict[str, list[str]] = {
    "Local tool orchestration": [
        "CLI command execution",
        "File operations",
        "Local app control",
        "Sandboxing",
    ],
    "Code and automation skills": [
        "Code generation and patching",
        "Debugging",
        "Testing discipline",
        "Build tooling",
    ],
    "Data handling offline": [
        "Parse and transform (JSON/CSV/YAML/HTML/PDF-to-text when possible)",
        "Local indexing and search",
        "Structured extraction",
    ],
}

OFFLINE_MEMORY_CONTEXT_SKILLS: dict[str, list[str]] = {
    "Working memory": [
        "State tracking",
        "Context compression",
        "Short-term recall",
    ],
    "Long-term memory (local)": [
        "Local knowledge base on disk",
        "Offline retrieval (keyword and semantic)",
        "Personalization rules",
    ],
}

OFFLINE_RELIABILITY_SKILLS: dict[str, list[str]] = {
    "Verification and self-checks": [
        "Output validation",
        "Fact-checking from local sources",
        "Regression prevention",
    ],
    "Error recovery and resilience": [
        "Robust exception handling",
        "Retry strategies with backoff",
        "Checkpointing",
        "Transaction-like edits",
    ],
    "Safety and permissions": [
        "Policy guardrails for destructive actions",
        "Secrets hygiene",
        "Permission awareness",
        "Audit trail",
    ],
}

OFFLINE_INTELLIGENCE_SKILLS: dict[str, list[str]] = {
    "Local reasoning competence": [
        "Tool-formatted reasoning",
        "Multi-step reasoning",
        "Ambiguity handling",
    ],
    "Local model management": [
        "Model routing",
        "Context window management",
        "Latency-aware behavior",
    ],
}

OPTIONAL_SKILLS: dict[str, list[str]] = {
    "Multimodal": [
        "Local OCR and screenshot understanding",
        "Local vision model integration",
    ],
    "Collaboration style": [
        "Explain changes",
        "Human-in-the-loop checkpoints",
    ],
}

AGENT_OS_SHARED_SKILLS: dict[str, list[str]] = {
    "Tasking and autonomy loop": [
        "Goal -> constraints -> acceptance criteria extraction",
        "Hierarchical plan synthesis",
        "Execution loop (act -> observe -> evaluate -> replan)",
        "Stop conditions",
    ],
    "Tool orchestration (offline)": [
        "Tool registry and capability discovery",
        "Command execution",
        "Structured I/O with schemas",
        "Idempotency",
        "Dry-run mode",
    ],
    "State, memory, and recall (local-only)": [
        "Working state tracking",
        "Long-term memory",
        "Offline retrieval (keyword + semantic + hybrid)",
        "Provenance (path, line range, timestamp)",
    ],
    "Reliability and verification": [
        "Self-checking",
        "Rollback",
        "Regression awareness",
        "Observability",
    ],
    "Safety and permissions": [
        "Guardrails on destructive ops",
        "Least privilege",
        "Secrets hygiene",
        "Sandboxing",
    ],
}

ROLE_TOOL_PACKS: dict[str, dict[str, list[str]]] = {
    "Coding agent": {
        "extra_skills": [
            "Repo comprehension",
            "Patch-based edits",
            "Build/test orchestration",
            "Debug loops",
            "Dependency resolution offline",
            "Release packaging",
        ],
        "offline_tools": [
            "git",
            "grep/ripgrep",
            "tree",
            "sed/awk",
            "language toolchains",
            "linters/formatters/test runners",
            "local docs lookup",
        ],
    },
    "File organizer": {
        "extra_skills": [
            "Robust file classification",
            "Deduping",
            "Metadata extraction",
            "Naming conventions and templating",
            "Bulk operations with preview and undo",
            "Policy-based organization",
        ],
        "offline_tools": [
            "hash tools",
            "exiftool",
            "ffprobe",
            "PDF/text extractors",
            "sqlite catalog and local search index",
        ],
    },
    "Call-center simulator": {
        "extra_skills": [
            "State machine design",
            "Turn-taking discipline",
            "Conversation policy",
            "Audio pipeline",
            "Queue simulation",
            "Scenario playback",
        ],
        "offline_tools": [
            "local TTS and local STT",
            "ffmpeg",
            "deterministic scenario runner",
        ],
    },
    "Desktop automation": {
        "extra_skills": [
            "UI navigation",
            "Robust selectors",
            "App-state detection",
            "Clipboard/typing discipline",
            "Recovery from modals",
        ],
        "offline_tools": [
            "OS accessibility APIs",
            "automation frameworks",
            "screenshot capture",
            "local vision fallback",
            "window manager/process inspection",
        ],
    },
    "Research assistant": {
        "extra_skills": [
            "Corpus ingestion",
            "Chunking and citation mapping",
            "Claim verification",
            "Synthesis without hallucinating",
            "Bibliography building",
        ],
        "offline_tools": [
            "local document parsers/indexers",
            "semantic search with local embeddings",
            "sqlite/fts",
            "PDF rendering",
            "optional OCR",
        ],
    },
}

GLUE_SKILLS: list[str] = [
    "Capability routing",
    "Unified workspace model",
    "Policy layering",
    "Artifact discipline",
    "Mode switching (Coder/Organizer/Operator/Research/IVR)",
]

MUST_HAVE_CHECKLIST: list[str] = [
    "Replanning and recovery",
    "Transaction edits (backup -> change -> verify -> commit)",
    "Local retrieval + citations",
    "Tool schema discipline",
    "Permission gates for destructive operations",
]

ONLINE_MODE_SKILLS: list[str] = [
    "Web browsing and navigation",
    "Search query crafting",
    "Source credibility scoring",
    "Freshness detection",
    "Webpage parsing",
    "Form filling and submission",
    "Session handling",
    "OAuth flows",
    "API integration",
    "Auth and secret management",
    "Rate-limit handling",
    "Pagination and cursor traversal",
    "Webhook consumption",
    "Polling strategies",
    "Data normalization",
    "ETL pipelines",
    "Online RAG with citations",
    "PDF/article summarization with citations",
    "Knowledge graph building from sources",
    "Translation and localization",
    "Email operations",
    "Calendar scheduling",
    "CRM/task system updates",
    "Collaboration ops",
    "Cloud storage operations",
    "Payments/billing handling",
    "Monitoring and alerting",
    "Compliance-aware logging",
    "Deployment and CI/CD triggers",
    "User impersonation safety",
]


@dataclass(frozen=True)
class BrowserSkillRoadmapItem:
    """One browser/UI online skill with build-order metadata."""

    skill_id: int
    phase: int
    name: str
    dependencies: tuple[int, ...]
    mvp_build: str
    done_when: str


ONLINE_BROWSER_UI_PHASES: dict[int, str] = {
    1: "Discovery and navigation",
    2: "Extraction",
    3: "Files and corpus building",
    4: "Evidence, citations, and trust",
    5: "Interaction and workflows",
    6: "Platform workflows without APIs",
    7: "Coverage boosters and resilience",
}

ONLINE_BROWSER_UI_ROADMAP: tuple[BrowserSkillRoadmapItem, ...] = (
    BrowserSkillRoadmapItem(
        1,
        1,
        "Search engine mastery",
        (),
        "Query builder with operators/quotes/site:/filetype:, query templates, multilingual fallback.",
        "Finds 3-10 high-signal results for a topic in under 30 seconds.",
    ),
    BrowserSkillRoadmapItem(
        2,
        1,
        "SERP triage",
        (1,),
        "Ranking heuristic (authority/relevance/date/snippet), quick-open top N tabs.",
        "Selects consistent best 3 sources instead of random clicks.",
    ),
    BrowserSkillRoadmapItem(
        3,
        1,
        "Deep web navigation",
        (2,),
        "Multi-click flow runner, dead-end backtracking, nav landmark detection.",
        "Reaches target pages reliably even 3-7 clicks deep.",
    ),
    BrowserSkillRoadmapItem(
        4,
        1,
        "Tab/session management",
        (3,),
        "Tab naming/grouping, parking-lot tabs, near-duplicate tab dedupe.",
        "Runs parallel research without losing source provenance.",
    ),
    BrowserSkillRoadmapItem(
        5,
        1,
        "Robust scrolling strategy",
        (3,),
        "Incremental scroll, anchor jumps, end detection, lazy-load triggers.",
        "Does not miss lazy-loaded content.",
    ),
    BrowserSkillRoadmapItem(
        6,
        1,
        "Login handling via web UI",
        (3, 4),
        "Login-form detection, redirect handling, logged-in state tracking, 2FA pause/resume.",
        "Reaches authenticated pages without loop failures.",
    ),
    BrowserSkillRoadmapItem(
        7,
        1,
        "Cookie and consent handling",
        (3,),
        "Consent-banner detection, minimal/essential preference selection, dismissal verification.",
        "Consent banners stop blocking reading/click paths.",
    ),
    BrowserSkillRoadmapItem(
        8,
        1,
        "Region/language switching",
        (3,),
        "Locale selector detection, preferred locale persistence, English fallback retry.",
        "Switches to a usable locale variant when needed.",
    ),
    BrowserSkillRoadmapItem(
        9,
        1,
        "Reading-mode extraction",
        (3,),
        "Boilerplate stripping, main-content extraction, heading/list preservation.",
        "Produces clean text without nav/ads/sidebar clutter.",
    ),
    BrowserSkillRoadmapItem(
        10,
        1,
        "Link graph expansion",
        (9,),
        "Citation/reference traversal and related-link queueing.",
        "Follows primary sources instead of repeating summaries.",
    ),
    BrowserSkillRoadmapItem(
        11,
        2,
        "DOM parsing and targeted scraping",
        (9,),
        "CSS/XPath selector strategy, table capture, section capture by heading.",
        "Extracts exact target sections repeatedly.",
    ),
    BrowserSkillRoadmapItem(
        12,
        2,
        "Web-to-table extraction",
        (11,),
        "List-to-row conversion, key/value extraction, header normalization.",
        "Outputs consistent schemas from messy pages.",
    ),
    BrowserSkillRoadmapItem(
        13,
        2,
        "Web table normalization",
        (12,),
        "Merge split headers, expand collapsed rows, handle rowspan/colspan.",
        "No broken columns or misaligned rows on common tables.",
    ),
    BrowserSkillRoadmapItem(
        14,
        2,
        "Dynamic content handling (JS-heavy SPAs)",
        (11,),
        "Wait-for-network-idle + wait-for-selector + client-render detection.",
        "Extracts SPA-rendered content reliably.",
    ),
    BrowserSkillRoadmapItem(
        15,
        2,
        "Pagination traversal",
        (11, 14),
        "Next-page detection, numeric pagination traversal, repeat-stop detection.",
        "Collects all pages without duplicates.",
    ),
    BrowserSkillRoadmapItem(
        16,
        2,
        "Infinite scroll harvesting",
        (5, 14),
        "Scroll-load loop with item-count stabilization and load-more clicking.",
        "Captures full feeds, not only initial viewport content.",
    ),
    BrowserSkillRoadmapItem(
        17,
        3,
        "File download handling",
        (11, 15, 16),
        "Download link/button detection, completion tracking, file existence/size verification.",
        "Downloads finish reliably with verified output files.",
    ),
    BrowserSkillRoadmapItem(
        18,
        3,
        "Browser download management",
        (17,),
        "Naming policy, dedupe, folder routing by type/source, retry failed downloads.",
        "Maintains stable download structure without silent overwrite.",
    ),
    BrowserSkillRoadmapItem(
        19,
        3,
        "Robust file-type handling online",
        (18,),
        "Recognize PDF/CSV/DOCX/XLSX/ZIP, preview/open logic, safe unzip flow.",
        "Ingests common web file formats automatically.",
    ),
    BrowserSkillRoadmapItem(
        20,
        3,
        "Offline cache building from web",
        (17, 18, 19),
        "Download+index pipeline with per-source folders and manifest.json artifacts.",
        "Rebuilds local research folders reproducibly.",
    ),
    BrowserSkillRoadmapItem(
        21,
        3,
        "Archive/backup navigation (cached pages)",
        (10,),
        "Detect cached/archived alternatives and store snapshot metadata.",
        "Retrieves older versions when originals disappear.",
    ),
    BrowserSkillRoadmapItem(
        22,
        3,
        "Web-based diffing (page/doc version comparison)",
        (20, 21),
        "Snapshot storage + text diff + changed-section highlighting.",
        "Outputs what changed with section anchors.",
    ),
    BrowserSkillRoadmapItem(
        23,
        3,
        "Change detection (watch pages for updates)",
        (22,),
        "Trigger scheduling + hash/semantic delta detection with noise filters.",
        "Detects meaningful updates while ignoring trivial churn.",
    ),
    BrowserSkillRoadmapItem(
        24,
        4,
        "Source credibility heuristics",
        (2,),
        "Authority/reputation/date/author/cross-source agreement scoring.",
        "Avoids weak sources when higher-quality alternatives exist.",
    ),
    BrowserSkillRoadmapItem(
        25,
        4,
        "Freshness detection",
        (24,),
        "Publish/update date extraction and stale-content flags for latest queries.",
        "Stops citing outdated information as current.",
    ),
    BrowserSkillRoadmapItem(
        26,
        4,
        "Cross-source fact checking",
        (24, 25),
        "Claim extraction + verification against at least 2 independent sources.",
        "Clearly marks unverified vs corroborated claims.",
    ),
    BrowserSkillRoadmapItem(
        27,
        4,
        "Quote discipline",
        (9, 11),
        "Short quote extraction with surrounding context and over-quote limits.",
        "Quotes remain precise and non-misleading.",
    ),
    BrowserSkillRoadmapItem(
        28,
        4,
        "Citation capture",
        (27,),
        "Capture URL/title/publisher/date/section/access timestamp metadata.",
        "Every claim links to an explicit citation record.",
    ),
    BrowserSkillRoadmapItem(
        29,
        4,
        "Screenshot evidence capture",
        (28,),
        "Screenshot workflow with naming convention and citation attachment.",
        "Can prove observed evidence even after page changes.",
    ),
    BrowserSkillRoadmapItem(
        30,
        4,
        "Reproducible web research reports",
        tuple(range(1, 30)),
        "Record queries, click-path, sources, findings, and uncertainty logs.",
        "Another operator can reproduce results step-by-step.",
    ),
    BrowserSkillRoadmapItem(
        31,
        5,
        "Form filling and submission",
        (11, 14),
        "Field detection, validation-error recovery, multi-step wizard support.",
        "Completes common forms without dead-end stalls.",
    ),
    BrowserSkillRoadmapItem(
        32,
        5,
        "Attachment and upload workflows",
        (18, 31),
        "File-picker automation, upload progress detection, retry on failed upload.",
        "Upload completion is verified by UI/server acknowledgment.",
    ),
    BrowserSkillRoadmapItem(
        33,
        5,
        "Web upload validation",
        (32,),
        "Partial-upload detection, size/checksum verification where possible, final-state confirmation.",
        "Never assumes upload success without proof.",
    ),
    BrowserSkillRoadmapItem(
        34,
        5,
        "Multi-site workflow chaining",
        (30, 31, 32, 33),
        "Pipeline state machine from source -> transform -> destination.",
        "Completes end-to-end cross-site workflows without manual glue.",
    ),
    BrowserSkillRoadmapItem(
        35,
        5,
        "Web UI automation reliability",
        (14, 31),
        "Robust waits/retries/stale-element recovery and deterministic selectors.",
        "Flake rate drops; rerun success exceeds 90%.",
    ),
    BrowserSkillRoadmapItem(
        36,
        5,
        "Session handling at UI level",
        (6, 35),
        "Session expiry detection, refresh flows, anti-loop handling for re-auth.",
        "Long-running tasks survive session churn.",
    ),
    BrowserSkillRoadmapItem(
        37,
        5,
        "CAPTCHA awareness and escalation",
        (35,),
        "CAPTCHA detection, explicit user escalation, resume-after-intervention flow.",
        "Never attempts CAPTCHA bypass; only pauses/escalates safely.",
    ),
    BrowserSkillRoadmapItem(
        38,
        5,
        "Browser security warning handling",
        (35,),
        "Detect TLS/cert warnings, default deny, explicit approval gate to proceed.",
        "Avoids risky navigation by default.",
    ),
    BrowserSkillRoadmapItem(
        39,
        6,
        "Web email handling (UI-based)",
        (6, 35),
        "Compose/reply/draft/label/archive/search via browser UI workflows.",
        "Completes basic email loops reliably.",
    ),
    BrowserSkillRoadmapItem(
        40,
        6,
        "Web calendar handling (UI-based)",
        (6, 35),
        "Create/edit events, invite attendees, timezone-safe scheduling checks.",
        "Schedules events without duplicate creation.",
    ),
    BrowserSkillRoadmapItem(
        41,
        6,
        "Online collaboration via UI",
        (6, 35),
        "Edit blocks, comment/resolve threads, export/share-link actions.",
        "Updates shared docs without formatting regressions.",
    ),
    BrowserSkillRoadmapItem(
        42,
        6,
        "Account/profile settings navigation",
        (6, 35),
        "Settings-path discovery, state toggle, saved-state verification.",
        "Settings persist and verification confirms final state.",
    ),
    BrowserSkillRoadmapItem(
        43,
        6,
        "Bookmarking and reading list management",
        (4, 20),
        "Save links with tags, summaries, and queued-citation backlog.",
        "Maintains useful to-read/to-cite queues.",
    ),
    BrowserSkillRoadmapItem(
        44,
        7,
        "Mirror discovery",
        (10, 20),
        "Find alternate hosts and match by title/unique phrases with canonical mapping.",
        "Recovers tasks when primary sites are down.",
    ),
    BrowserSkillRoadmapItem(
        45,
        7,
        "Paywall routing (no bypass)",
        (24, 25, 26),
        "Paywall detection and routing to official alternatives (press releases/abstracts/docs).",
        "Maintains useful output without illegal/unsafe bypass behavior.",
    ),
    BrowserSkillRoadmapItem(
        46,
        7,
        "Community intelligence mining (read-only)",
        (1, 2, 3, 24),
        "Find discussions, extract accepted solutions, confidence-tag anecdotal signals.",
        "Uses community data as signal, not sole source of truth.",
    ),
    BrowserSkillRoadmapItem(
        47,
        7,
        "Support/help center navigation",
        (3, 9),
        "Locate official docs, follow troubleshooting trees, capture steps with evidence.",
        "Produces actionable troubleshooting guides with citations.",
    ),
    BrowserSkillRoadmapItem(
        48,
        7,
        "Policy/terms reading and summarization",
        (9, 28),
        "Extract policy sections and summarize key clauses with anchors.",
        "Summaries match source terms and include section anchors.",
    ),
    BrowserSkillRoadmapItem(
        49,
        7,
        "Product/service comparison via web",
        (12, 13, 24, 25, 26),
        "Feature matrix extraction + naming normalization + citation for each claim.",
        "Outputs clean comparison tables with traceable sources.",
    ),
    BrowserSkillRoadmapItem(
        50,
        7,
        "Social platform interaction via UI (careful mode)",
        (6, 35, 38),
        "Draft posts/replies/DMs with explicit send gate and lockout awareness.",
        "Never sends without explicit go-ahead approval.",
    ),
)

ONLINE_BUILD_ORDER_START: tuple[int, ...] = (1, 2, 11, 15, 17, 28, 23, 31)

ONLINE_DEPENDENCY_PHASE_MAP: dict[str, list[int]] = {
    "Discovery": list(range(1, 11)),
    "Extraction": list(range(11, 17)),
    "Downloads/corpus": list(range(17, 24)),
    "Trust/citations": list(range(24, 31)),
    "Workflows/forms": list(range(31, 39)),
    "Email/calendar/collab": list(range(39, 44)),
    "Resilience/coverage": list(range(44, 51)),
}


def supported_custom_tools() -> tuple[str, ...]:
    """Supported tool names for user-created custom skills."""
    return SUPPORTED_CUSTOM_TOOLS


def custom_skills_path(cwd: str = ".") -> str:
    """Path to the persisted custom-skills file for a workspace."""
    root = os.path.abspath(os.path.expanduser(cwd or "."))
    return os.path.join(root, CUSTOM_SKILLS_DIR, CUSTOM_SKILLS_FILE)


def canonical_custom_skill_name(name: str) -> str:
    """Normalize free-form skill names into stable keys."""
    key = (name or "").strip().lower().replace(" ", "-")
    key = re.sub(r"[^a-z0-9_-]", "", key)
    return key


def _normalize_custom_tools(tools: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    allowed = set(SUPPORTED_CUSTOM_TOOLS)
    for tool in tools:
        candidate = (tool or "").strip()
        if not candidate or candidate not in allowed:
            continue
        if candidate not in normalized:
            normalized.append(candidate)
    return tuple(normalized)


def _default_custom_prompt(name: str, description: str, tools: tuple[str, ...]) -> str:
    tool_line = ", ".join(tools)
    return (
        f"You are EBR {name} Agent. {description}. "
        f"{UNCENSORED_RULES} "
        f"Allowed tools: {tool_line}. "
        "Operate autonomously, verify outputs, and report concrete results. "
        f"{TOOL_FORMAT}"
    )


def _register_custom_skill(
    name: str,
    description: str,
    tools: list[str] | tuple[str, ...],
    system_prompt: str = "",
    model_alias: str = "",
    base_model: str = "",
) -> tuple[bool, str]:
    skill_name = canonical_custom_skill_name(name)
    if not CUSTOM_SKILL_NAME_RE.match(skill_name):
        return False, "Invalid skill name. Use 2-40 chars: a-z, 0-9, '-', '_'."

    if skill_name in _BUILTIN_SKILL_NAMES:
        return False, f"'{skill_name}' is reserved by a built-in skill."

    desc = (description or "").strip()
    if not desc:
        return False, "Description is required."

    normalized_tools = _normalize_custom_tools(tools)
    if not normalized_tools:
        available = ", ".join(SUPPORTED_CUSTOM_TOOLS)
        return False, f"No valid tools selected. Supported: {available}"

    alias = (model_alias or f"ebr-{skill_name}:latest").strip()
    base = (base_model or DEFAULT_CUSTOM_SKILL_BASE_MODEL).strip()
    if not base:
        base = DEFAULT_CUSTOM_SKILL_BASE_MODEL

    if base not in BASE_MODELS:
        BASE_MODELS[base] = DEFAULT_CUSTOM_SKILL_BASE_SIZE_GB
    approx_size = BASE_MODELS.get(base, DEFAULT_CUSTOM_SKILL_BASE_SIZE_GB)

    prompt = (system_prompt or "").strip() or _default_custom_prompt(skill_name, desc, normalized_tools)
    if TOOL_FORMAT not in prompt:
        prompt = f"{prompt}\n\n{TOOL_FORMAT}"

    variant_id = f"custom_{skill_name}"
    MODEL_VARIANTS[variant_id] = ModelVariant(
        variant_id=variant_id,
        model=alias,
        base_model=base,
        approx_size_gb=approx_size,
        notes="User-defined custom skill",
    )
    SKILLS[skill_name] = SkillSpec(
        name=skill_name,
        description=desc,
        variants=(variant_id,),
        tools=normalized_tools,
        system_prompt=prompt,
    )
    return True, f"Custom skill '{skill_name}' is ready."


def _read_custom_skill_records(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return []

    if isinstance(payload, dict):
        records = payload.get("skills", [])
        return records if isinstance(records, list) else []
    return payload if isinstance(payload, list) else []


def load_custom_skills(cwd: str = ".") -> tuple[int, list[str]]:
    """Load persisted custom skills into the in-memory skill registry."""
    path = custom_skills_path(cwd)
    records = _read_custom_skill_records(path)
    loaded = 0
    errors: list[str] = []

    for idx, rec in enumerate(records):
        if not isinstance(rec, dict):
            errors.append(f"record {idx + 1}: invalid format")
            continue
        ok, msg = _register_custom_skill(
            name=str(rec.get("name", "")),
            description=str(rec.get("description", "")),
            tools=rec.get("tools", []),
            system_prompt=str(rec.get("system_prompt", "")),
            model_alias=str(rec.get("model_alias", "")),
            base_model=str(rec.get("base_model", "")),
        )
        if ok:
            loaded += 1
        else:
            errors.append(f"{rec.get('name', 'unknown')}: {msg}")

    return loaded, errors


def create_custom_skill(
    cwd: str,
    name: str,
    description: str,
    tools: list[str] | tuple[str, ...],
    system_prompt: str = "",
    model_alias: str = "",
    base_model: str = "",
) -> tuple[bool, str]:
    """Create/update a custom skill and persist it to workspace storage."""
    ok, msg = _register_custom_skill(
        name=name,
        description=description,
        tools=tools,
        system_prompt=system_prompt,
        model_alias=model_alias,
        base_model=base_model,
    )
    if not ok:
        return False, msg

    path = custom_skills_path(cwd)
    records = _read_custom_skill_records(path)
    if not isinstance(records, list):
        records = []

    skill_name = canonical_custom_skill_name(name)
    record = {
        "name": skill_name,
        "description": (description or "").strip(),
        "tools": list(_normalize_custom_tools(tools)),
        "system_prompt": (system_prompt or "").strip(),
        "model_alias": (model_alias or f"ebr-{skill_name}:latest").strip(),
        "base_model": (base_model or DEFAULT_CUSTOM_SKILL_BASE_MODEL).strip(),
    }

    updated = False
    for idx, existing in enumerate(records):
        if isinstance(existing, dict) and existing.get("name") == skill_name:
            records[idx] = record
            updated = True
            break
    if not updated:
        records.append(record)

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"skills": records}, f, indent=2)
    except Exception as e:
        return (
            False,
            f"Skill loaded for this session but could not persist to {path}: {e}",
        )

    verb = "Updated" if updated else "Created"
    return True, f"{verb} custom skill '{skill_name}' ({path})."


def custom_skills_markdown(cwd: str = ".") -> str:
    """Render a summary table for custom user-defined skills."""
    custom_names = sorted(name for name in SKILLS if name not in _BUILTIN_SKILL_NAMES)
    lines = ["## Custom Skills", ""]

    if not custom_names:
        lines.append("No custom skills yet.")
        lines.append("")
        lines.append("- Create one with: `/skill-create <name>`")
        lines.append(f"- Supported tools: {', '.join(SUPPORTED_CUSTOM_TOOLS)}")
        return "\n".join(lines)

    lines.extend(
        [
            "| Skill | Alias Model | Base Model | Tools | Description |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for name in custom_names:
        spec = SKILLS[name]
        variant = MODEL_VARIANTS.get(spec.variants[0]) if spec.variants else None
        alias = variant.model if variant else "-"
        base = variant.base_model if variant else "-"
        tools = ", ".join(spec.tools)
        desc = spec.description.replace("|", "/")
        lines.append(f"| {name} | `{alias}` | `{base}` | {tools} | {desc} |")

    lines.append("")
    lines.append(f"Stored at: `{custom_skills_path(cwd)}`")
    return "\n".join(lines)


def normalize_skill(skill: str) -> str:
    key = (skill or "").strip().lower()
    return key if key in SKILLS else "coder"


def route_skill(task: str) -> str:
    """Heuristic router used when planner output is incomplete."""
    text = (task or "").lower()
    if any(ord(ch) > 127 for ch in text):
        return "multilingual_understanding"
    if any(token in text for token in ("plan", "roadmap", "breakdown", "workflow")):
        return "planner"
    if any(
        token in text
        for token in (
            "multilingual",
            "translate",
            "translation",
            "language detect",
            "tagalog",
            "filipino",
            "spanish",
            "español",
            "francais",
            "french",
            "japanese",
            "korean",
            "chinese",
        )
    ):
        return "multilingual_understanding"
    if any(token in text for token in ("humor loading", "loading joke", "funny loading", "status joke")):
        return "humor_loading"
    if any(token in text for token in ("gui automation", "web ui automation", "screen automation", "desktop ui")):
        return "gui_automation"
    if any(token in text for token in ("direct system control", "system control", "service control", "process control")):
        return "direct_system_control"
    if any(token in text for token in ("call simulation", "ivr", "call-center", "queue simulation")):
        return "call_simulation"
    if any(token in text for token in ("os-level automation", "os automation", "desktop automation", "window automation")):
        return "os_automation"
    if any(token in text for token in ("fix own failure", "self-heal", "self heal", "auto-recover", "recover failure")):
        return "self_heal"
    if any(token in text for token in ("learn from users data", "learn user data", "learn preferences", "user learning")):
        return "user_learning"
    if any(token in text for token in ("save personality", "user personality", "personality profile", "tone profile")):
        return "personality"
    if any(token in text for token in ("test", "verify", "check", "assert", "failing")):
        return "tester"
    if any(token in text for token in ("review", "audit", "risk", "regression")):
        return "reviewer"
    if any(token in text for token in ("doc", "readme", "guide", "instructions")):
        return "docs"
    if any(token in text for token in ("remember", "memory", "store", "recall")):
        return "memory"
    if any(token in text for token in ("research", "analyze", "inspect", "explore")):
        return "researcher"
    return "coder"


def resolve_skill_models(skill: str, fallback_model: str = "") -> tuple[str, ...]:
    """Resolve model candidates for a skill, honoring env overrides first."""
    normalized = normalize_skill(skill)
    env_suffix = re.sub(r"[^A-Z0-9]", "_", normalized.upper())
    env_key = f"CODEMAXXX_SKILL_MODEL_{env_suffix}"
    env_model = os.environ.get(env_key, "").strip()

    if env_model:
        models = [env_model]
    else:
        models: list[str] = []
        for variant_id in SKILLS[normalized].variants:
            variant = MODEL_VARIANTS.get(variant_id)
            if not variant:
                continue
            models.append(variant.model)
            # Automatic fallback to base pool if alias model does not exist.
            models.append(variant.base_model)

    if fallback_model and fallback_model not in models:
        models.append(fallback_model)

    deduped: list[str] = []
    for model in models:
        if model not in deduped:
            deduped.append(model)
    return tuple(deduped)


def estimate_model_size_gb(model: str) -> float | None:
    for variant in MODEL_VARIANTS.values():
        if variant.model == model:
            return variant.approx_size_gb
    return BASE_MODELS.get(model)


def get_model_variant(model: str) -> ModelVariant | None:
    for variant in MODEL_VARIANTS.values():
        if variant.model == model:
            return variant
    return None


def _render_grouped_skills(title: str, groups: dict[str, list[str]]) -> list[str]:
    lines = [f"## {title}", ""]
    for idx, (group_name, items) in enumerate(groups.items(), 1):
        lines.append(f"{idx}. {group_name}")
        for item in items:
            lines.append(f"- {item}")
    lines.append("")
    return lines


def offline_skill_framework_markdown() -> str:
    """Detailed offline-first autonomous skill framework."""
    lines: list[str] = ["# Offline Autonomous Skill Framework", ""]
    lines.extend(_render_grouped_skills("Core Autonomy Skills", OFFLINE_CORE_AUTONOMY_SKILLS))
    lines.extend(_render_grouped_skills("Offline Tool-Use Skills", OFFLINE_TOOL_USE_SKILLS))
    lines.extend(_render_grouped_skills("Memory and Context Skills", OFFLINE_MEMORY_CONTEXT_SKILLS))
    lines.extend(_render_grouped_skills("Reliability Skills", OFFLINE_RELIABILITY_SKILLS))
    lines.extend(_render_grouped_skills("Offline Intelligence Skills", OFFLINE_INTELLIGENCE_SKILLS))
    lines.extend(_render_grouped_skills("Optional Skill Bundles", OPTIONAL_SKILLS))
    return "\n".join(lines).strip()


def unified_agent_os_markdown() -> str:
    """Unified map for shared Agent OS + role-specific tool packs."""
    lines: list[str] = ["# Unified Offline Agent OS", ""]
    lines.extend(_render_grouped_skills("Shared Agent OS Skills", AGENT_OS_SHARED_SKILLS))

    lines.append("## Role Tool Packs")
    lines.append("")
    for role, spec in ROLE_TOOL_PACKS.items():
        lines.append(f"### {role}")
        lines.append("Extra skills:")
        for item in spec.get("extra_skills", []):
            lines.append(f"- {item}")
        lines.append("Offline tools:")
        for item in spec.get("offline_tools", []):
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## Glue Skills")
    lines.append("")
    for idx, skill in enumerate(GLUE_SKILLS, 1):
        lines.append(f"{idx}. {skill}")
    lines.append("")

    lines.append("## Minimal Must-Have Checklist")
    lines.append("")
    for idx, item in enumerate(MUST_HAVE_CHECKLIST, 1):
        lines.append(f"{idx}. {item}")

    return "\n".join(lines).strip()


def online_mode_skills_markdown() -> str:
    """30 online-mode skills for internet/cloud-enabled autonomous operation."""
    lines: list[str] = ["# Online-Mode Autonomous Skills", ""]
    for idx, item in enumerate(ONLINE_MODE_SKILLS, 1):
        lines.append(f"{idx}. {item}")
    lines.append("")
    lines.append("Use `/roadmap-online` for the full 50-skill browser/UI build roadmap.")
    return "\n".join(lines).strip()


def _roadmap_lookup() -> dict[int, BrowserSkillRoadmapItem]:
    return {item.skill_id: item for item in ONLINE_BROWSER_UI_ROADMAP}


def _dep_text(dependencies: tuple[int, ...]) -> str:
    if not dependencies:
        return "—"
    return ", ".join(str(dep) for dep in dependencies)


def online_browser_ui_roadmap_markdown() -> str:
    """Full 50-skill online browser/UI roadmap with dependencies and checks."""
    lines: list[str] = [
        "# Online Browser/UI Skills Build Roadmap (50 skills)",
        "",
        "Start sequence:",
        "- Search",
        "- Source triage",
        "- DOM extraction",
        "- Pagination/scrolling",
        "- Download management",
        "- Citation capture",
        "- Change detection",
        "- Form filling",
        "",
    ]

    for phase_id, phase_name in ONLINE_BROWSER_UI_PHASES.items():
        lines.append(f"## Phase {phase_id} — {phase_name}")
        lines.append("")
        for item in ONLINE_BROWSER_UI_ROADMAP:
            if item.phase != phase_id:
                continue
            lines.append(f"{item.skill_id}) {item.name}")
            lines.append(f"- Depends on: {_dep_text(item.dependencies)}")
            lines.append(f"- MVP build: {item.mvp_build}")
            lines.append(f"- Done when: {item.done_when}")
        lines.append("")

    lines.append("## Quick Dependency Map")
    lines.append("")
    for label, ids in ONLINE_DEPENDENCY_PHASE_MAP.items():
        lines.append(f"- {label}: {ids[0]}-{ids[-1]}")
    return "\n".join(lines).strip()


def online_browser_ui_roadmap_phase_markdown(phase_query: str) -> str:
    """Roadmap view for a specific phase by number or keyword."""
    raw = (phase_query or "").strip().lower()
    phase_id = None

    if raw.isdigit():
        n = int(raw)
        if n in ONLINE_BROWSER_UI_PHASES:
            phase_id = n
    else:
        for pid, name in ONLINE_BROWSER_UI_PHASES.items():
            if raw in name.lower():
                phase_id = pid
                break

    if phase_id is None:
        return (
            "## Online Browser/UI Roadmap\n\n"
            "Unknown phase. Use `/roadmap-online` for full view or `/roadmap-online-phase <1-7>`."
        )

    lines = [f"# Phase {phase_id} — {ONLINE_BROWSER_UI_PHASES[phase_id]}", ""]
    for item in ONLINE_BROWSER_UI_ROADMAP:
        if item.phase != phase_id:
            continue
        lines.append(f"{item.skill_id}) {item.name}")
        lines.append(f"- Depends on: {_dep_text(item.dependencies)}")
        lines.append(f"- MVP build: {item.mvp_build}")
        lines.append(f"- Done when: {item.done_when}")
    return "\n".join(lines).strip()


def online_browser_ui_start_sequence_markdown() -> str:
    """Roadmap view for the required first build sequence."""
    lookup = _roadmap_lookup()
    lines = ["# Online Build Start Sequence", ""]
    for idx, skill_id in enumerate(ONLINE_BUILD_ORDER_START, 1):
        item = lookup.get(skill_id)
        if not item:
            continue
        lines.append(f"{idx}. {item.name} (Skill {item.skill_id})")
        lines.append(f"- Depends on: {_dep_text(item.dependencies)}")
        lines.append(f"- MVP build: {item.mvp_build}")
        lines.append(f"- Done when: {item.done_when}")
    return "\n".join(lines).strip()


def full_skill_map_markdown() -> str:
    """Combined offline and online skill map."""
    return "\n\n".join(
        [
            offline_skill_framework_markdown(),
            unified_agent_os_markdown(),
            online_mode_skills_markdown(),
            online_browser_ui_roadmap_markdown(),
        ]
    )


def planner_capability_brief() -> str:
    """Short capability hints injected into planner prompts."""
    lines = [
        "Core offline capabilities:",
        "- task intake, constraints, and acceptance criteria",
        "- hierarchical planning + dynamic replanning",
        "- local tool orchestration, verification, and rollback",
        "- safety gates for destructive actions",
        "Role packs: coding, file organizer, call-center simulator, desktop automation, research assistant.",
        "Additional dedicated skills: gui_automation, direct_system_control, call_simulation, os_automation, self_heal, user_learning, personality, multilingual_understanding, humor_loading.",
        "External tools always require explicit user approval before command execution.",
        "Custom skills can be created on demand and persisted per workspace.",
        "Online-mode capability set exists (30 skills) plus a 50-skill browser/UI roadmap.",
        "Required online build start: search -> source triage -> DOM extraction -> pagination/scrolling -> download management -> citation capture -> change detection -> form filling.",
    ]
    return "\n".join(lines)
