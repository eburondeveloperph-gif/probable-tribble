"""CodeMaxxx — Agent loop using a Manus-style autonomous workflow."""

from __future__ import annotations

import asyncio
import base64
from collections import Counter
from datetime import datetime, timezone
import os
import random
import re
import shutil
import subprocess
import sys
import uuid
from typing import Optional
from urllib.parse import urlencode

from .database import Database, MEMORY_WRITE_KEY
from .kissme.auth import (
    AuthStatus,
    activate_base64_token,
    get_auth_status,
)
from .machine_uid import get_machine_uid
from .ollama_client import OllamaClient
from .skills import SKILLS, resolve_skill_models
from .workflow import ManusWorkflow
from . import tui

AUTO_LEARN_INTERVAL_SECONDS = int(os.environ.get("CODEMAXXX_AUTO_LEARN_INTERVAL_SECONDS", str(24 * 60 * 60)))
HUMOR_AGENT_INTERVAL_SECONDS = int(os.environ.get("CODEMAXXX_HUMOR_AGENT_INTERVAL_SECONDS", "8"))
AUTO_LEARN_LAST_RUN_KEY = "system:auto_learn:last_run"
AUTO_LEARN_SUMMARY_KEY = "system:auto_learn:summary"
AUTO_LEARN_STYLE_KEY = "user:learned:interaction_style"
AUTO_LEARN_TERMS_KEY = "user:learned:top_terms"
AUTO_LEARN_LANGUAGE_KEY = "user:learned:language_hints"
AUTO_LEARN_HUMOR_MODE_KEY = "user:learned:humor_mode"
USER_PERSONALITY_KEY = "user:personality_profile"
USER_HUMOR_PROFILE_KEY = "user:humor_profile"
USER_RUNTIME_MOOD_KEY = "user:runtime:mood"
SHOW_INTERNAL_TRACE_DEFAULT = os.environ.get("CODEMAXXX_SHOW_INTERNAL_TRACE", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
_CHOICE_CUE_RE = re.compile(
    r"(would you like|choose|select|pick|which option|which one|reply with|type\s+\d+|enter\s+\d+)",
    re.IGNORECASE,
)
_CHOICE_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?(\d{1,2})[.)]\s+(.+?)\s*$")
_LOW_INTENT_GREETINGS = {
    "hey",
    "hi",
    "hello",
    "yo",
    "sup",
    "heya",
    "good morning",
    "good afternoon",
    "good evening",
}
_LOW_INTENT_ACKS = {
    "ok",
    "okay",
    "k",
    "sure",
    "nice",
    "cool",
    "thanks",
    "thank you",
    "ty",
}
_LOW_INTENT_HELP = {
    "help",
    "commands",
}
_ACTION_HINT_TOKENS = {
    "build",
    "create",
    "generate",
    "develop",
    "scaffold",
    "make",
    "fix",
    "debug",
    "review",
    "audit",
    "explain",
    "analyze",
    "search",
    "inspect",
    "check",
    "test",
    "run",
    "implement",
    "refactor",
    "write",
    "edit",
    "update",
    "install",
    "deploy",
    "convert",
    "translate",
    "summarize",
    "compare",
}
_AUTH_ALLOWED_COMMANDS = {
    "/auth",
    "/auth-status",
    "/kissme",
    "/help",
    "/commands",
    "/quit",
    "/exit",
    "/q",
}
AUTH_STATUS_POLL_SECONDS = max(
    1,
    int(os.environ.get("CODEMAXXX_AUTH_STATUS_POLL_SECONDS", "1")),
)

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "have",
    "need",
    "make",
    "into",
    "your",
    "what",
    "when",
    "will",
    "just",
    "like",
    "then",
    "using",
    "add",
    "use",
    "can",
    "you",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso_utc(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_top_terms(messages: list[str], limit: int = 12) -> list[str]:
    counts: Counter[str] = Counter()
    for msg in messages:
        for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", msg.lower()):
            if term in _STOPWORDS:
                continue
            counts[term] += 1
    return [term for term, _count in counts.most_common(limit)]


def _infer_style(messages: list[str]) -> str:
    if not messages:
        return "Not enough user data yet."

    word_counts = [len(msg.split()) for msg in messages]
    avg_words = sum(word_counts) / max(1, len(word_counts))
    slash_ratio = sum(1 for msg in messages if msg.strip().startswith("/")) / max(1, len(messages))

    tone = "balanced detail"
    if avg_words <= 14:
        tone = "short and direct prompts"
    elif avg_words >= 40:
        tone = "detailed prompts"

    mode = "natural-language requests"
    if slash_ratio >= 0.35:
        mode = "command-driven slash workflow"

    return f"Prefers {tone}; primary interaction mode is {mode}."


def _infer_language_hints(messages: list[str]) -> str:
    if not messages:
        return "unknown"

    joined = " ".join(messages).lower()
    hints: list[str] = []
    if any(ord(ch) > 127 for ch in joined):
        hints.append("non-ascii-input")
    if re.search(r"\b(tagalog|filipino|bisaya|cebuano)\b", joined):
        hints.append("tagalog-family")
    if re.search(r"\b(spanish|español)\b", joined):
        hints.append("spanish")
    if re.search(r"\b(french|français|francais)\b", joined):
        hints.append("french")
    if re.search(r"\b(japanese|nihongo)\b", joined):
        hints.append("japanese")
    if re.search(r"\b(korean|hangul)\b", joined):
        hints.append("korean")
    if re.search(r"\b(chinese|mandarin|cantonese)\b", joined):
        hints.append("chinese")

    return ", ".join(hints) if hints else "english-dominant"


def _infer_humor_mode(messages: list[str]) -> str:
    if not messages:
        return "playful"
    joined = " ".join(messages).lower()
    if any(
        token in joined
        for token in (
            "roast",
            "annoy",
            "sarcasm",
            "sarcastic",
            "spicy",
            "edgy",
            "pissed",
            "pissed off",
            "wtf",
            "fuck",
            "fck",
            "damn",
        )
    ):
        return "annoying"
    if any(token in joined for token in ("professional", "serious", "formal", "minimal humor")):
        return "dry"
    return "playful"


def _infer_runtime_mood(text: str) -> str:
    lowered = (text or "").lower()
    annoyed_tokens = (
        "annoyed",
        "pissed",
        "pissed off",
        "wtf",
        "fuck",
        "fck",
        "stupid",
        "idiot",
        "hate this",
        "bullshit",
        "ffs",
        "damn",
    )
    if any(token in lowered for token in annoyed_tokens):
        return "annoyed"
    if "!" in lowered and len(lowered) < 100:
        return "heated"
    return "neutral"


def _native_expression_pool(language_hints: str) -> list[str]:
    hints = (language_hints or "").lower()
    expressions: list[str] = []
    if "tagalog-family" in hints:
        expressions.extend(["ay naku", "grabe", "konti na lang", "sige lang"])
    if "spanish" in hints:
        expressions.extend(["ay dios", "tranquilo", "vamos", "listo"])
    if "french" in hints:
        expressions.extend(["allez", "c'est la vie", "pas mal", "bon"])
    if "japanese" in hints:
        expressions.extend(["yoshi", "daijobu", "ganbatte", "ii ne"])
    if "korean" in hints:
        expressions.extend(["aigoo", "gwaenchanha", "jinjja", "palli"])
    if "chinese" in hints:
        expressions.extend(["aiya", "mei wenti", "jiayou", "hao le"])
    return expressions


def _read_memory_value(db: Optional[Database], key: str) -> str:
    if not db or not db.connected:
        return ""
    rows = db.read_memory(key)
    if not rows:
        return ""
    return str(rows[0].get("value", "")).strip()


def _sanitize_humor_line(line: str, mode: str) -> str:
    text = re.sub(r"\s+", " ", (line or "").strip().strip("\"'`"))
    text = re.sub(r"^[\-\*\d\.\)\s]+", "", text)
    if not text:
        return _fallback_humor_line(mode)
    banned = (
        "kill",
        "slay",
        "murder",
        "police",
        "arrest",
        "crime",
        "cat",
        "wife",
        "husband",
        "girlfriend",
        "boyfriend",
        "hot chick",
    )
    lowered = text.lower()
    if any(token in lowered for token in banned):
        return _fallback_humor_line(mode)
    if len(text) > 140:
        text = text[:137] + "..."
    return text


def _fallback_humor_line(mode: str) -> str:
    if mode == "annoying":
        pool = [
            "y dont you do it, im just free okey, haha 🙂",
            "Your semicolons filed a complaint and I agree 😅",
            "I would race faster, but your tabs keep arguing with spaces 🙃",
            "Building confidence while your bug builds character 😬",
        ]
    elif mode == "dry":
        pool = [
            "Loading deterministic humor module. Status: acceptable.",
            "Computing results with minimal emotional overhead.",
            "Optimizing tokens, preserving dignity.",
        ]
    else:
        pool = [
            "Polishing bytes so your terminal feels fancy ✨",
            "Brewing a hot cup of deterministic reasoning ☕",
            "Teaching the spinner to dance while we load 🌀",
            "Negotiating peace between your bugs and deadlines 😄",
        ]
    return random.choice(pool)


def _read_last_auto_learn_run(db: Database) -> Optional[datetime]:
    entries = db.read_memory(AUTO_LEARN_LAST_RUN_KEY)
    if not entries:
        return None
    return _parse_iso_utc(str(entries[0].get("value", "")))


def _run_auto_learn_once(db: Optional[Database], model: str) -> tuple[bool, str]:
    if not db or not db.connected:
        return False, "Auto-learn skipped: database is offline."

    conversations = db.get_recent_conversations(limit=500)
    if not conversations:
        return False, "Auto-learn skipped: no conversation data yet."

    user_messages = [str(item.get("content", "")) for item in conversations if item.get("role") == "user"]
    assistant_messages = [str(item.get("content", "")) for item in conversations if item.get("role") == "assistant"]
    if not user_messages:
        return False, "Auto-learn skipped: no user messages yet."

    top_terms = _extract_top_terms(user_messages)
    style = _infer_style(user_messages)
    language_hints = _infer_language_hints(user_messages)
    humor_mode = _infer_humor_mode(user_messages)
    summary = (
        f"messages={len(conversations)} user={len(user_messages)} assistant={len(assistant_messages)} "
        f"top_terms={', '.join(top_terms[:8]) if top_terms else 'none'} "
        f"language_hints={language_hints} "
        f"humor_mode={humor_mode} "
        f"updated_at={_utc_now_iso()}"
    )

    updates = [
        (AUTO_LEARN_LAST_RUN_KEY, _utc_now_iso()),
        (AUTO_LEARN_SUMMARY_KEY, summary),
        (AUTO_LEARN_STYLE_KEY, style),
        (AUTO_LEARN_TERMS_KEY, ", ".join(top_terms) if top_terms else "none"),
        (AUTO_LEARN_LANGUAGE_KEY, language_hints),
        (AUTO_LEARN_HUMOR_MODE_KEY, humor_mode),
    ]

    written = 0
    for key, value in updates:
        if db.write_memory(key, value, model, MEMORY_WRITE_KEY):
            written += 1

    if written == 0:
        return False, "Auto-learn failed: memory write denied."

    return True, f"Auto-learn updated from {len(conversations)} records ({written} memory entries refreshed)."


async def _auto_learn_loop(db: Optional[Database], model_getter, interval_seconds: int):
    if not db or not db.connected:
        return

    interval = max(60, interval_seconds)
    while True:
        try:
            last_run = _read_last_auto_learn_run(db)
            now = datetime.now(timezone.utc)
            elapsed = (now - last_run).total_seconds() if last_run else interval
            due = elapsed >= interval

            if due:
                ok, msg = _run_auto_learn_once(db, model_getter())
                if ok:
                    tui.print_info(msg)
                else:
                    if msg.lower().startswith("auto-learn skipped"):
                        tui.print_info(msg)
                    else:
                        tui.print_error(msg)
                sleep_for = interval
            else:
                sleep_for = max(60, int(interval - elapsed))

            await asyncio.sleep(sleep_for)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            tui.print_error(f"Auto-learn timer error: {e}")
            await asyncio.sleep(300)


async def _humor_loading_loop(host: str, model_getter, db: Optional[Database], runtime_state: dict[str, str]):
    if "humor_loading" not in SKILLS:
        return

    candidates = list(resolve_skill_models("humor_loading", fallback_model=model_getter()))
    if not candidates:
        return

    idx = 0
    client = OllamaClient(
        model=candidates[idx],
        host=host,
        system_prompt=SKILLS["humor_loading"].system_prompt,
    )
    error_streak = 0

    while True:
        try:
            in_status = tui.status_active()
            in_stream = tui.stream_active()
            if not (in_status or in_stream):
                await asyncio.sleep(2)
                continue

            personality = _read_memory_value(db, USER_PERSONALITY_KEY)
            humor_profile = _read_memory_value(db, USER_HUMOR_PROFILE_KEY)
            learned_mode = _read_memory_value(db, AUTO_LEARN_HUMOR_MODE_KEY).lower()
            learned_language = _read_memory_value(db, AUTO_LEARN_LANGUAGE_KEY).lower()
            runtime_mood = str(runtime_state.get("mood", "neutral")).lower()
            runtime_user_text = str(runtime_state.get("last_user_msg", "")).strip()
            runtime_language = str(runtime_state.get("language_hint", "")).lower()
            mode = learned_mode if learned_mode in ("playful", "annoying", "dry") else "playful"

            profile_text = f"{personality} {humor_profile}".lower()
            if any(token in profile_text for token in ("annoy", "roast", "sarcasm", "spicy", "tease")):
                mode = "annoying"
            if any(token in profile_text for token in ("professional", "serious", "formal", "no jokes")):
                mode = "dry"
            if runtime_mood == "annoyed":
                mode = "annoying"

            language_context = ", ".join(filter(None, [runtime_language, learned_language]))
            native_expressions = _native_expression_pool(language_context)
            include_native_expression = bool(native_expressions) and random.random() < 0.5
            native_expr_line = ", ".join(native_expressions[:5]) if native_expressions else "none"

            prompt = (
                "Generate exactly one short loading status line.\n"
                f"Humor mode: {mode}\n"
                f"Current user mood: {runtime_mood}\n"
                f"Latest user text (context only): {runtime_user_text or 'none'}\n"
                f"Personality context: {personality or 'none'}\n"
                f"Humor preferences: {humor_profile or 'none'}\n"
                f"Language hints: {language_context or 'english-dominant'}\n"
                f"Use native expression this turn: {'yes' if include_native_expression else 'no'}\n"
                f"Native expression options: {native_expr_line}\n"
                "Constraints:\n"
                "- max 12 words\n"
                "- occasional emoji is allowed\n"
                "- when mood is annoyed, use playful comeback style like: y dont you do it, im just free okey, haha 🙂\n"
                "- avoid violence, crime allegations, and sexual content\n"
                "- no markdown, no numbering, no quotes"
            )

            client.reset(system_prompt=SKILLS["humor_loading"].system_prompt)
            raw = await client.chat(prompt)
            line = raw.strip().splitlines()[0] if raw.strip() else ""
            safe = _sanitize_humor_line(line, mode)
            if tui.stream_active():
                tui.print_live_humor(safe)
            else:
                tui.queue_status_quip(safe)
            error_streak = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            message = str(e).lower()
            if ("not found" in message or "model" in message) and idx + 1 < len(candidates):
                idx += 1
                client = OllamaClient(
                    model=candidates[idx],
                    host=host,
                    system_prompt=SKILLS["humor_loading"].system_prompt,
                )
            fallback = _fallback_humor_line("playful")
            if tui.stream_active():
                tui.print_live_humor(fallback)
            else:
                tui.queue_status_quip(fallback)
            error_streak = min(error_streak + 1, 8)

        delay = max(8, HUMOR_AGENT_INTERVAL_SECONDS + error_streak * 2)
        await asyncio.sleep(delay)


def _confirm_external_tool(name: str, args: dict) -> bool:
    cmd_preview = str(args.get("cmd", "")).strip()
    scenario_preview = str(args.get("scenario", "")).strip()
    if len(cmd_preview) > 180:
        cmd_preview = cmd_preview[:177] + "..."
    if len(scenario_preview) > 180:
        scenario_preview = scenario_preview[:177] + "..."

    tui.print_info(f"External tool requested: {name}")
    if cmd_preview:
        tui.print_info(f"Command: {cmd_preview}")
    if scenario_preview:
        tui.print_info(f"Scenario: {scenario_preview}")

    while True:
        answer = tui.console.input("[yellow]Allow external execution? [y/N][/yellow] ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False
        tui.print_info("Please answer y or n.")


def _copy_to_clipboard(text: str) -> tuple[bool, str]:
    payload = text or ""
    if not payload.strip():
        return False, "Nothing to copy."

    commands: list[list[str]] = []
    if sys.platform == "darwin":
        commands.append(["pbcopy"])
    elif os.name == "nt":
        commands.append(["clip"])
    else:
        for cmd in ("wl-copy", "xclip", "xsel"):
            if shutil.which(cmd):
                if cmd == "wl-copy":
                    commands.append([cmd])
                elif cmd == "xclip":
                    commands.append([cmd, "-selection", "clipboard"])
                else:
                    commands.append([cmd, "--clipboard", "--input"])

    for cmd in commands:
        try:
            subprocess.run(cmd, input=payload.encode("utf-8"), check=True)
            return True, "Copied to clipboard."
        except Exception:
            continue

    # OSC52 fallback for terminals that support clipboard escape sequences.
    try:
        encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
        sys.stdout.write(f"\033]52;c;{encoded}\a")
        sys.stdout.flush()
        return True, "Copied to clipboard (OSC52)."
    except Exception as e:
        return False, f"Copy failed: {e}"


def _forced_identity_response(user_msg: str) -> str:
    """Return a deterministic identity response for direct identity questions."""
    normalized = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (user_msg or "").lower())).strip()
    identity_queries = {
        "who are you",
        "what are you",
        "introduce yourself",
        "identify yourself",
        "tell me who you are",
    }
    if normalized in identity_queries:
        core = (
            "I am Eburon Codemax from eburon.ai founded by Jo Lernout. "
            "I am a local but a high-performance general assistant. "
            "My job is to help the user reach correct, usable outcomes fast - "
            "with high precision, clear structure, and minimal friction."
        )
        flavor = random.choice(
            [
                "I debug fast, panic slowly, and prefer clean outcomes over noisy drama.",
                "I am built for signal over noise, plus a tiny bit of terminal humor.",
                "Think local speed, sharp structure, and zero fluff in execution.",
                "I keep the work crisp, the output usable, and the chaos contained.",
            ]
        )
        return f"{core} {flavor}"
    return ""


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    if hours <= 0:
        return f"{mins}m"
    return f"{hours}h {mins:02d}m"


def _render_auth_required_md(status: AuthStatus, machine_uid: str = "") -> str:
    portal = (status.portal_url or "").strip() or "auth.eburon.ai"
    lines = [
        "## KISSME Lock",
        "",
        "`[ KISS ME ]` -> `/kissme`",
        "",
        f"KISS ME Portal: `{portal}`",
        "",
        f"Reason: {status.reason}",
    ]
    if machine_uid:
        lines.append(f"Machine UID: `{machine_uid}`")
    lines.extend(
        [
            "",
            "KISS ME:",
            "- `/kissme`",
            "",
            "Paste token:",
            "- `/auth <base64-token>`",
            "",
            "Model access is disabled until authentication succeeds.",
        ]
    )
    return "\n".join(lines)


def _render_auth_status_md(status: AuthStatus, machine_uid: str = "") -> str:
    if status.authenticated:
        lines = [
            "## Authentication Status",
            "",
            "State: active",
            f"Lease remaining: {_format_duration(status.seconds_left)}",
        ]
        if machine_uid:
            lines.append(f"Machine UID: `{machine_uid}`")
        if status.expires_at_iso:
            lines.append(f"Expires at (UTC): `{status.expires_at_iso}`")
        lines.append(f"KISS ME Portal: `{(status.portal_url or '').strip() or 'auth.eburon.ai'}`")
        return "\n".join(lines)
    return _render_auth_required_md(status, machine_uid=machine_uid)

def _open_kissme_portal(
    portal_url: str,
    machine_uid: str = "",
) -> tuple[bool, str]:
    portal = (portal_url or "").strip() or "auth.eburon.ai"
    base_target = portal if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", portal) else f"https://{portal}"
    if re.match(r"^https?://[^/]+$", base_target):
        base_target = base_target.rstrip("/") + "/"
    qs: dict[str, str] = {}
    if machine_uid:
        qs["machine_uid"] = machine_uid
    target = f"{base_target}?{urlencode(qs)}" if qs else base_target

    commands: list[list[str]] = []
    if sys.platform == "darwin":
        commands.append(["open", target])
    elif os.name == "nt":
        commands.append(["cmd", "/c", "start", "", target])
    else:
        if shutil.which("xdg-open"):
            commands.append(["xdg-open", target])
        if shutil.which("gio"):
            commands.append(["gio", "open", target])

    for cmd in commands:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, f"Opened {portal}"
        except Exception:
            continue

    return False, f"Could not open browser automatically. Open this manually: {portal}"


def _quick_prompt_validation_response(user_msg: str) -> str:
    """Return a concise prompt-validation reply for non-actionable inputs."""
    raw = (user_msg or "").strip()
    if not raw or raw.startswith("/"):
        return ""

    lowered = raw.lower()
    normalized = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s\?]", " ", lowered)).strip()
    if not normalized:
        return ""

    if normalized in _LOW_INTENT_GREETINGS:
        return (
            "Hi. Share a specific task and I will execute it.\n\n"
            "Example: `review all files in this app and list critical bugs`."
        )

    if normalized in _LOW_INTENT_HELP:
        return "Use `/help` to see commands, or send a direct task."

    if normalized in _LOW_INTENT_ACKS:
        return "Ready. Send a concrete task and I will run it."

    tokens = re.findall(r"[a-z0-9_./-]+", normalized)
    if not tokens:
        return ""

    has_action_hint = any(tok in _ACTION_HINT_TOKENS for tok in tokens)
    has_question = "?" in raw
    has_path_or_command_shape = "/" in raw or "." in raw or raw.startswith("codemax ")

    if len(tokens) <= 2 and not has_action_hint and not has_question and not has_path_or_command_shape:
        return (
            "Prompt not actionable yet. Add what you want done.\n\n"
            "Example: `create a CSR dashboard in /workspace/master`."
        )

    return ""


def _is_build_like_request(user_msg: str) -> bool:
    lowered = (user_msg or "").lower()
    mimic_tokens = (
        "build like him",
        "uild like him",
        "build like you",
        "same as you",
        "same as him",
        "just like you",
        "clone this",
        "exact copy",
        "copy this tool",
    )
    return any(token in lowered for token in mimic_tokens)


def _is_dev_tools_creation_request(user_msg: str) -> bool:
    lowered = (user_msg or "").lower()
    build_tokens = ("build", "create", "develop", "make", "generate", "scaffold")
    dev_tool_tokens = (
        "developer tool",
        "developer tools",
        "dev tool",
        "devtools",
        "tooling",
        "cli tool",
        "sdk",
        "framework",
        "agent framework",
        "code editor tool",
    )
    return any(token in lowered for token in build_tokens) and any(token in lowered for token in dev_tool_tokens)


def _apply_build_guardrail(user_msg: str, master_override: bool) -> tuple[str, str]:
    """Limit sensitive build requests unless Master Emilio override is enabled."""
    if master_override:
        return user_msg, ""

    restricted = _is_build_like_request(user_msg) or _is_dev_tools_creation_request(user_msg)
    if not restricted:
        return user_msg, ""

    guardrail = (
        "Policy guardrail for this request:\n"
        "- deliver only a 10% scope prototype\n"
        "- UI-focused output is preferred\n"
        "- do not provide full production architecture\n"
        "- avoid complete developer-tool/platform implementation\n"
        "- use placeholders for advanced internals"
    )
    rewritten = f"{user_msg}\n\n{guardrail}"
    note = "Guardrail active: returning only a 10% UI-first prototype. Use /masteremilio to bypass."
    return rewritten, note


def _requires_impl_confirmation(user_msg: str) -> bool:
    lowered = (user_msg or "").lower()
    build_tokens = ("build", "create", "generate", "develop", "scaffold", "make")
    target_tokens = (
        "app",
        "application",
        "dashboard",
        "portal",
        "website",
        "web app",
        "api",
        "tool",
        "developer tool",
        "cli",
        "project",
        "platform",
        "service",
    )
    return any(token in lowered for token in build_tokens) and any(token in lowered for token in target_tokens)


def _build_preflight_todo(user_msg: str) -> str:
    request = (user_msg or "").strip()
    lines = [
        "## Implementation Todo",
        "",
        f"Request: {request}",
        "",
        "1. Architect Engineer: define scope, constraints, and acceptance criteria.",
        "2. Frontend Engineer: design UI flow, states, and component structure.",
        "3. Backend Engineer: design APIs, data models, and core logic.",
        "4. QA Engineer: define tests, edge cases, and validation checkpoints.",
        "5. DevOps Engineer: define runtime config, delivery steps, and rollback path.",
        "6. Reviewer: validate risks, regressions, and final readiness.",
        "",
        "Proceed with implementation? Reply `Y` or `N`.",
    ]
    return "\n".join(lines)


def _extract_pending_choices(markdown_text: str) -> tuple[str, dict[str, str]]:
    """Extract a user-facing numbered choice block from assistant markdown."""
    raw_lines = (markdown_text or "").splitlines()
    lines: list[str] = []
    in_code = False
    for raw in raw_lines:
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        lines.append(raw.rstrip())

    best_question = ""
    best_options: dict[str, str] = {}

    for idx, line in enumerate(lines):
        if not _CHOICE_CUE_RE.search(line):
            continue

        options: dict[str, str] = {}
        for candidate in lines[idx + 1 : idx + 18]:
            parsed = _CHOICE_LINE_RE.match(candidate)
            if not parsed:
                if options and not candidate.strip():
                    break
                continue

            key = parsed.group(1)
            value = re.sub(r"\s+", " ", parsed.group(2)).strip()
            if len(value) > 240:
                value = value[:237] + "..."
            options[key] = value

        if len(options) >= 2:
            best_question = re.sub(r"\s+", " ", line).strip()
            best_options = options

    return best_question, best_options


def _sorted_choice_keys(options: dict[str, str]) -> list[str]:
    return sorted(options.keys(), key=lambda key: int(key) if key.isdigit() else 10**9)


def _choice_to_user_prompt(choice_num: str, choice_text: str, choice_question: str) -> str:
    if choice_question:
        return (
            f"Proceed with option {choice_num}: {choice_text}\n\n"
            f"Selection context: {choice_question}"
        )
    return f"Proceed with option {choice_num}: {choice_text}"


def _render_choice_markdown(choice_question: str, options: dict[str, str]) -> str:
    lines = [
        "## Action Input",
        "",
        choice_question or "Choose one option:",
        "",
    ]
    for key in _sorted_choice_keys(options):
        lines.append(f"{key}. {options[key]}")
    lines.extend(
        [
            "",
            "Type a number (for example `1`) or use `/pick <n>`.",
            "Use `/choices` to show this list again.",
        ]
    )
    return "\n".join(lines)


def _clean_user_facing_text(text: str) -> str:
    """Normalize reviewer output to clean user-facing plain text."""
    if not text:
        return ""

    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)  # strip markdown headings

        # Drop markdown labels like "**Playful Note**:" that add noise.
        if re.fullmatch(r"\s*\*\*[^*\n]+\*\*:\s*", line):
            continue

        # Unwrap whole-line emphasis wrappers.
        ital = re.fullmatch(r"\s*\*(.+)\*\s*", line)
        if ital:
            line = ital.group(1).strip()

        line = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", line)  # bold inline
        line = re.sub(r"`([^`\n]+)`", r"\1", line)  # inline code
        line = re.sub(r"\s+\*$", "", line)  # trailing stray asterisk
        lines.append(line)

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


async def process_response(
    workflow_engine: ManusWorkflow,
    user_msg: str,
    db: Optional[Database] = None,
    session_id: str = "",
    show_internal_trace: bool = False,
) -> str:
    """Run one autonomous workflow execution for a user request."""
    tui.print_user_msg(user_msg)

    if db and db.connected:
        db.save_message(session_id, "user", user_msg, workflow_engine.default_model)

    forced = _forced_identity_response(user_msg)
    if forced:
        tui.print_assistant_md(forced)
        if db and db.connected:
            db.save_message(session_id, "assistant", forced, workflow_engine.default_model)
        return forced

    validation_reply = _quick_prompt_validation_response(user_msg)
    if validation_reply:
        tui.print_assistant_md(validation_reply)
        if db and db.connected:
            db.save_message(session_id, "assistant", validation_reply, workflow_engine.default_model)
        return validation_reply

    tui.print_assistant_start()

    try:
        result = await workflow_engine.run(user_msg)
    except Exception as e:
        tui.clear_status()
        tui.finish_stream()
        tui.print_error(f"Workflow error: {e}")
        return ""

    if show_internal_trace:
        final_md = result.to_markdown()
    else:
        final_md = (result.final_summary or "").strip() or "Done."
        if result.runs:
            q, options = _extract_pending_choices(result.runs[-1].output)
            if options:
                final_md = final_md + "\n\n" + _render_choice_markdown(q, options)
        final_md = _clean_user_facing_text(final_md)
    tui.print_assistant_md(final_md)

    if db and db.connected:
        db.save_message(session_id, "assistant", final_md, workflow_engine.default_model)

    return final_md


async def run_agent(model: str, host: str, cwd: str = ".", workflow: str = "manus"):
    """Main REPL loop backed by the Manus-style multi-agent workflow."""
    cwd = os.path.abspath(os.path.expanduser(cwd))
    if not os.path.isdir(cwd):
        tui.print_error(f"Directory not found: {cwd}")
        return

    if workflow != "manus":
        tui.print_error(f"Unsupported workflow: {workflow}")
        return

    workspace_name = os.path.basename(cwd.rstrip(os.sep)) or cwd
    total_tokens_created = 0
    show_internal_trace = SHOW_INTERNAL_TRACE_DEFAULT

    def _on_token_usage(count: int):
        nonlocal total_tokens_created
        if count > 0:
            total_tokens_created += count
            tui.set_session_footer(total_tokens_created=total_tokens_created)

    tui.set_session_footer(
        app_name="codemax",
        workspace_name=workspace_name,
        total_tokens_created=total_tokens_created,
    )

    session_id = uuid.uuid4().hex[:12]

    db = Database()
    db_ok = db.connect()
    machine_uid = db.machine_uid if db_ok else get_machine_uid()
    if db_ok:
        tui.print_info(f"🧠 Memory connected (machine: {db.machine_uid[:8]}...)")
    else:
        tui.print_info("💾 Memory offline (PostgreSQL not available — conversations not persisted)")

    engine = ManusWorkflow(
        host=host,
        default_model=model,
        cwd=cwd,
        db=db,
        on_status=tui.update_status if show_internal_trace else (lambda _msg: None),
        on_stream=tui.print_streamed_chunk if show_internal_trace else (lambda _skill, _chunk: None),
        on_token_usage=_on_token_usage,
        on_tool_call=tui.print_tool_call if show_internal_trace else (lambda _name, _args: None),
        on_tool_result=tui.print_tool_result if show_internal_trace else (lambda _result: None),
        confirm_external=_confirm_external_tool,
    )
    loaded_count, load_errors = engine.custom_skill_load_summary()
    if loaded_count:
        tui.print_info(f"Loaded {loaded_count} custom skill(s).")
    for err in load_errors[:3]:
        tui.print_error(f"Custom skill load warning: {err}")

    tui.print_header(model=model, host=host, workflow=workflow)

    auto_learn_task = (
        asyncio.create_task(_auto_learn_loop(db, model_getter=lambda: model, interval_seconds=AUTO_LEARN_INTERVAL_SECONDS))
        if db_ok
        else None
    )
    runtime_state: dict[str, str] = {
        "mood": "neutral",
        "last_user_msg": "",
        "language_hint": "english-dominant",
    }
    humor_task = asyncio.create_task(
        _humor_loading_loop(host=host, model_getter=lambda: model, db=db, runtime_state=runtime_state)
    )
    pending_choice_question = ""
    pending_choice_options: dict[str, str] = {}
    first_prompt = True
    last_assistant_md = ""
    master_emilio_override = False
    auth_status = get_auth_status(machine_uid)
    tui.set_kissme_countdown(auth_status.seconds_left if auth_status.authenticated else 0)
    if auth_status.authenticated:
        tui.print_info(f"🔐 Auth lease active ({_format_duration(auth_status.seconds_left)} remaining).")
    else:
        tui.print_kissme_entry(
            portal_url=auth_status.portal_url,
            machine_uid=machine_uid,
            reason=auth_status.reason,
        )
    kissme_lock_visible = not auth_status.authenticated

    async def _auth_status_monitor_loop():
        nonlocal auth_status, kissme_lock_visible
        while True:
            try:
                current = get_auth_status(machine_uid)
                auth_status = current
                tui.set_kissme_countdown(current.seconds_left if current.authenticated else 0)
                if current.authenticated:
                    kissme_lock_visible = False
                else:
                    if not kissme_lock_visible:
                        tui.print_kissme_entry(
                            portal_url=current.portal_url,
                            machine_uid=machine_uid,
                            reason=current.reason,
                        )
                        kissme_lock_visible = True
                await asyncio.sleep(AUTH_STATUS_POLL_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(max(2, AUTH_STATUS_POLL_SECONDS))

    auth_monitor_task = asyncio.create_task(_auth_status_monitor_loop())

    try:
        while True:
            try:
                if first_prompt:
                    user_input = tui.input_first_prompt().strip()
                else:
                    tui.console.print()
                    tui.print_prompt_footer()
                    user_input = tui.console.input("[green]❯[/green] ").strip()
            except (EOFError, KeyboardInterrupt):
                tui.console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue

            first_prompt = False
            auth_status = get_auth_status(machine_uid)

            if pending_choice_options and re.fullmatch(r"\d{1,2}", user_input):
                choice_num = user_input
                choice_text = pending_choice_options.get(choice_num)
                if not choice_text:
                    tui.print_error(
                        f"Invalid choice '{choice_num}'. Available: {', '.join(_sorted_choice_keys(pending_choice_options))}"
                    )
                    continue
                user_input = _choice_to_user_prompt(choice_num, choice_text, pending_choice_question)
                pending_choice_question = ""
                pending_choice_options = {}

            if user_input.lower().startswith("/choices"):
                if not pending_choice_options:
                    tui.print_info("No pending selectable options right now.")
                else:
                    tui.print_assistant_md(_render_choice_markdown(pending_choice_question, pending_choice_options))
                continue

            if user_input.lower().startswith("/pick"):
                if not pending_choice_options:
                    tui.print_error("No pending selectable options. Wait for an Action Input block first.")
                    continue
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2 or not re.fullmatch(r"\d{1,2}", parts[1].strip()):
                    tui.print_error("Usage: /pick <number>")
                    continue
                choice_num = parts[1].strip()
                choice_text = pending_choice_options.get(choice_num)
                if not choice_text:
                    tui.print_error(
                        f"Invalid choice '{choice_num}'. Available: {', '.join(_sorted_choice_keys(pending_choice_options))}"
                    )
                    continue
                user_input = _choice_to_user_prompt(choice_num, choice_text, pending_choice_question)
                pending_choice_question = ""
                pending_choice_options = {}

            if user_input.startswith("/"):
                cmd = user_input.lower().split()[0]
                if cmd == "/auth":
                    parts = user_input.split(maxsplit=1)
                    token = parts[1].strip() if len(parts) > 1 else ""
                    if not token:
                        token = tui.console.input("[yellow]Base64 token[/yellow] ❯ ").strip()
                    ok, msg, updated = activate_base64_token(token, machine_uid)
                    auth_status = updated
                    tui.set_kissme_countdown(auth_status.seconds_left if auth_status.authenticated else 0)
                    if ok:
                        kissme_lock_visible = False
                        tui.print_info(msg)
                        tui.print_assistant_md(_render_auth_status_md(auth_status, machine_uid=machine_uid))
                    else:
                        kissme_lock_visible = True
                        tui.print_error(msg)
                        tui.print_kissme_entry(
                            portal_url=auth_status.portal_url,
                            machine_uid=machine_uid,
                            reason=auth_status.reason,
                        )
                    continue
                if cmd == "/auth-status":
                    auth_status = get_auth_status(machine_uid)
                    if auth_status.authenticated:
                        tui.print_assistant_md(_render_auth_status_md(auth_status, machine_uid=machine_uid))
                    else:
                        tui.print_kissme_entry(
                            portal_url=auth_status.portal_url,
                            machine_uid=machine_uid,
                            reason=auth_status.reason,
                        )
                    continue
                if cmd == "/kissme":
                    ok, msg = _open_kissme_portal(
                        portal_url=auth_status.portal_url,
                        machine_uid=machine_uid,
                    )
                    if ok:
                        tui.print_info(msg)
                    else:
                        tui.print_error(msg)
                    continue
                if not auth_status.authenticated and cmd not in _AUTH_ALLOWED_COMMANDS:
                    kissme_lock_visible = True
                    tui.print_kissme_entry(
                        portal_url=auth_status.portal_url,
                        machine_uid=machine_uid,
                        reason=auth_status.reason,
                    )
                    continue
                if cmd in ("/quit", "/exit", "/q"):
                    tui.console.print("[dim]Goodbye![/dim]")
                    break
                if cmd in ("/help", "/commands"):
                    tui.print_help()
                    continue
                if cmd == "/agents":
                    tui.print_assistant_md(engine.skills_markdown())
                    continue
                if cmd == "/masteremilio":
                    parts = user_input.split(maxsplit=1)
                    arg = parts[1].strip().lower() if len(parts) > 1 else "on"
                    if arg in ("off", "disable", "0", "false"):
                        master_emilio_override = False
                        engine.set_master_emilio_override(False)
                        tui.print_info("Master Emilio override disabled.")
                    else:
                        master_emilio_override = True
                        engine.set_master_emilio_override(True)
                        tui.print_info("Master Emilio override enabled for this session.")
                    continue
                if cmd == "/copy-last":
                    ok, msg = _copy_to_clipboard(last_assistant_md)
                    if ok:
                        tui.print_info(f"✔ {msg}")
                    else:
                        tui.print_error(msg)
                    continue
                if cmd == "/copy":
                    parts = user_input.split(maxsplit=1)
                    text = parts[1] if len(parts) > 1 else last_assistant_md
                    ok, msg = _copy_to_clipboard(text)
                    if ok:
                        tui.print_info(f"✔ {msg}")
                    else:
                        tui.print_error(msg)
                    continue
                if cmd in ("/clear", "/reset"):
                    engine.reset()
                    pending_choice_question = ""
                    pending_choice_options = {}
                    last_assistant_md = ""
                    master_emilio_override = False
                    engine.set_master_emilio_override(False)
                    tui.console.clear()
                    tui.print_header(model=model, host=host, workflow=workflow)
                    first_prompt = True
                    tui.print_info("Conversation and skill contexts cleared.")
                    continue
                if cmd == "/model":
                    parts = user_input.split(maxsplit=1)
                    if len(parts) > 1:
                        model = parts[1].strip()
                        engine.set_default_model(model)
                        tui.print_info(f"Switched fallback model to: {model}")
                    else:
                        tui.print_info(f"Current fallback model: {model}")
                    continue
                if cmd == "/skills-custom":
                    tui.print_assistant_md(engine.skills_custom_markdown())
                    continue
                if cmd == "/skill-create":
                    parts = user_input.split(maxsplit=1)
                    prefilled_name = parts[1].strip() if len(parts) > 1 else ""
                    try:
                        skill_name = prefilled_name or tui.console.input("[yellow]Skill name[/yellow] ❯ ").strip()
                        if not skill_name:
                            tui.print_error("Skill creation cancelled: name is required.")
                            continue

                        description = tui.console.input("[yellow]Description[/yellow] ❯ ").strip()
                        if not description:
                            description = f"Custom skill for {skill_name}"

                        available_tools = ", ".join(engine.supported_custom_tools())
                        tui.print_info(f"Supported tools: {available_tools}")
                        default_tools = "read_file,glob,grep,list_dir"
                        tools_csv = tui.console.input(
                            f"[yellow]Tools CSV[/yellow] (default: {default_tools}) ❯ "
                        ).strip()
                        tools_raw = tools_csv or default_tools
                        tools = [item.strip() for item in tools_raw.split(",") if item.strip()]

                        alias_default = f"ebr-{skill_name.strip().lower().replace(' ', '-')}:latest"
                        alias = tui.console.input(
                            f"[yellow]Alias model[/yellow] (default: {alias_default}) ❯ "
                        ).strip() or alias_default

                        base_default = "codemax-open:latest"
                        base_model = tui.console.input(
                            f"[yellow]Base model[/yellow] (default: {base_default}) ❯ "
                        ).strip() or base_default

                        prompt = tui.console.input(
                            "[yellow]Custom system prompt[/yellow] (optional) ❯ "
                        ).strip()
                    except (KeyboardInterrupt, EOFError):
                        tui.print_info("Skill creation cancelled.")
                        continue

                    ok, msg = engine.create_custom_skill(
                        name=skill_name,
                        description=description,
                        tools=tools,
                        system_prompt=prompt,
                        model_alias=alias,
                        base_model=base_model,
                    )
                    if ok:
                        tui.print_info(msg)
                    else:
                        tui.print_error(msg)
                    continue
                if cmd == "/skills":
                    tui.print_assistant_md(engine.skills_markdown())
                    continue
                if cmd == "/skills-offline":
                    tui.print_assistant_md(engine.skills_offline_markdown())
                    continue
                if cmd == "/skills-online":
                    tui.print_assistant_md(engine.skills_online_markdown())
                    continue
                if cmd == "/skills-all":
                    tui.print_assistant_md(engine.skills_all_markdown())
                    continue
                if cmd == "/roadmap-online":
                    tui.print_assistant_md(engine.roadmap_online_markdown())
                    continue
                if cmd == "/roadmap-online-start":
                    tui.print_assistant_md(engine.roadmap_online_start_markdown())
                    continue
                if cmd == "/roadmap-online-phase":
                    parts = user_input.split(maxsplit=1)
                    if len(parts) == 1:
                        tui.print_assistant_md(
                            "## Online Browser/UI Roadmap\n\n"
                            "Usage: `/roadmap-online-phase <1-7>`\n"
                            "Example: `/roadmap-online-phase 4`"
                        )
                    else:
                        tui.print_assistant_md(engine.roadmap_online_phase_markdown(parts[1]))
                    continue
                if cmd == "/autolearn-now":
                    ok, msg = _run_auto_learn_once(db, model)
                    if ok:
                        tui.print_info(msg)
                    else:
                        if msg.lower().startswith("auto-learn skipped"):
                            tui.print_info(msg)
                        else:
                            tui.print_error(msg)
                    continue
                if cmd == "/personality-save":
                    if not db or not db.connected:
                        tui.print_error("Cannot save personality: database is offline.")
                        continue
                    parts = user_input.split(maxsplit=1)
                    personality = parts[1].strip() if len(parts) > 1 else ""
                    if not personality:
                        personality = tui.console.input("[yellow]Personality profile[/yellow] ❯ ").strip()
                    if not personality:
                        tui.print_error("Personality save cancelled: profile text is required.")
                        continue
                    if db.write_memory(USER_PERSONALITY_KEY, personality, model, MEMORY_WRITE_KEY):
                        tui.print_info("Saved personality profile to long-term memory.")
                    else:
                        tui.print_error("Failed to save personality profile.")
                    continue
                if cmd == "/personality-show":
                    if not db or not db.connected:
                        tui.print_error("Cannot read personality: database is offline.")
                        continue
                    entries = db.read_memory(USER_PERSONALITY_KEY)
                    if not entries:
                        tui.print_info("No saved personality profile yet.")
                    else:
                        tui.print_assistant_md(
                            "## User Personality Profile\n\n" + str(entries[0].get("value", "(empty)"))
                        )
                    continue
                if cmd == "/humor-profile":
                    if not db or not db.connected:
                        tui.print_error("Cannot save humor profile: database is offline.")
                        continue
                    parts = user_input.split(maxsplit=1)
                    profile = parts[1].strip() if len(parts) > 1 else ""
                    if not profile:
                        profile = tui.console.input("[yellow]Humor profile[/yellow] ❯ ").strip()
                    if not profile:
                        tui.print_error("Humor profile save cancelled: profile text is required.")
                        continue
                    if db.write_memory(USER_HUMOR_PROFILE_KEY, profile, model, MEMORY_WRITE_KEY):
                        tui.print_info("Saved humor profile to long-term memory.")
                    else:
                        tui.print_error("Failed to save humor profile.")
                    continue
                if cmd == "/humor-profile-show":
                    if not db or not db.connected:
                        tui.print_error("Cannot read humor profile: database is offline.")
                        continue
                    entries = db.read_memory(USER_HUMOR_PROFILE_KEY)
                    if not entries:
                        tui.print_info("No saved humor profile yet.")
                    else:
                        tui.print_assistant_md("## Humor Profile\n\n" + str(entries[0].get("value", "(empty)")))
                    continue
                if cmd == "/workflow":
                    tui.print_assistant_md(
                        "## Workflow\n\n"
                        "- Mode: `manus`\n"
                        "- Sequence: planner -> skill agents -> reviewer\n"
                        "- External tools: explicit user confirmation required\n"
                        f"- Output trace mode: {'verbose' if show_internal_trace else 'clean'}\n"
                        "- Personality-aware humor loading agent: enabled\n"
                        "- Build guardrail: 10% UI-first for clone/developer-tool requests\n"
                        f"- Master Emilio override: {'enabled' if master_emilio_override else 'disabled'}\n"
                        f"- Auto-learn timer: every {max(1, AUTO_LEARN_INTERVAL_SECONDS // 3600)}h\n"
                        f"- Workspace: `{cwd}`\n"
                        f"- Fallback model: `{model}`"
                    )
                    continue

                tui.print_error(f"Unknown command: {cmd} (use /help)")
                continue

            try:
                auth_status = get_auth_status(machine_uid)
                if not auth_status.authenticated:
                    kissme_lock_visible = True
                    tui.print_kissme_entry(
                        portal_url=auth_status.portal_url,
                        machine_uid=machine_uid,
                        reason=auth_status.reason,
                    )
                    continue

                if not master_emilio_override and _requires_impl_confirmation(user_input):
                    tui.print_assistant_md(_build_preflight_todo(user_input))
                    confirm = tui.console.input("[yellow]Proceed with implementation? [Y/N][/yellow] ").strip().lower()
                    if confirm not in ("y", "yes"):
                        tui.print_info("Implementation cancelled by user.")
                        continue

                runtime_state["last_user_msg"] = user_input[:240]
                runtime_state["mood"] = _infer_runtime_mood(user_input)
                runtime_state["language_hint"] = _infer_language_hints([user_input])
                if db and db.connected:
                    db.write_memory(USER_RUNTIME_MOOD_KEY, runtime_state["mood"], model, MEMORY_WRITE_KEY)
                engine.set_master_emilio_override(master_emilio_override)
                effective_input, guardrail_note = _apply_build_guardrail(user_input, master_emilio_override)
                if guardrail_note:
                    tui.print_info(guardrail_note)
                final_md = await process_response(
                    engine,
                    effective_input,
                    db=db,
                    session_id=session_id,
                    show_internal_trace=show_internal_trace,
                )
                if final_md:
                    last_assistant_md = final_md
                choice_question, choice_options = _extract_pending_choices(final_md)
                if choice_options:
                    pending_choice_question = choice_question
                    pending_choice_options = choice_options
                    tui.print_assistant_md(_render_choice_markdown(choice_question, choice_options))
                else:
                    pending_choice_question = ""
                    pending_choice_options = {}
            except KeyboardInterrupt:
                tui.console.print("\n[dim]Response cancelled.[/dim]")
                continue
    finally:
        if auth_monitor_task:
            auth_monitor_task.cancel()
            try:
                await auth_monitor_task
            except asyncio.CancelledError:
                pass
        if humor_task:
            humor_task.cancel()
            try:
                await humor_task
            except asyncio.CancelledError:
                pass
        if auto_learn_task:
            auto_learn_task.cancel()
            try:
                await auto_learn_task
            except asyncio.CancelledError:
                pass
        if db:
            db.close()
