"""CodeMaxxx — Agent loop using a Manus-style autonomous workflow."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone
import os
import random
import re
import uuid
from typing import Optional

from .database import Database, MEMORY_WRITE_KEY
from .ollama_client import OllamaClient
from .skills import SKILLS, resolve_skill_models
from .workflow import ManusWorkflow
from . import tui

AUTO_LEARN_INTERVAL_SECONDS = int(os.environ.get("CODEMAXXX_AUTO_LEARN_INTERVAL_SECONDS", str(24 * 60 * 60)))
HUMOR_AGENT_INTERVAL_SECONDS = int(os.environ.get("CODEMAXXX_HUMOR_AGENT_INTERVAL_SECONDS", "14"))
AUTO_LEARN_LAST_RUN_KEY = "system:auto_learn:last_run"
AUTO_LEARN_SUMMARY_KEY = "system:auto_learn:summary"
AUTO_LEARN_STYLE_KEY = "user:learned:interaction_style"
AUTO_LEARN_TERMS_KEY = "user:learned:top_terms"
AUTO_LEARN_LANGUAGE_KEY = "user:learned:language_hints"
AUTO_LEARN_HUMOR_MODE_KEY = "user:learned:humor_mode"
USER_PERSONALITY_KEY = "user:personality_profile"
USER_HUMOR_PROFILE_KEY = "user:humor_profile"
USER_RUNTIME_MOOD_KEY = "user:runtime:mood"

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
            if not tui.status_active():
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
            tui.queue_status_quip(_fallback_humor_line("playful"))
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


async def process_response(
    workflow_engine: ManusWorkflow,
    user_msg: str,
    db: Optional[Database] = None,
    session_id: str = "",
):
    """Run one autonomous workflow execution for a user request."""
    tui.print_user_msg(user_msg)

    if db and db.connected:
        db.save_message(session_id, "user", user_msg, workflow_engine.default_model)

    tui.print_assistant_start()

    try:
        result = await workflow_engine.run(user_msg)
    except Exception as e:
        tui.clear_status()
        tui.finish_stream()
        tui.print_error(f"Workflow error: {e}")
        return

    final_md = result.to_markdown()
    tui.print_assistant_md(final_md)

    if db and db.connected:
        db.save_message(session_id, "assistant", final_md, workflow_engine.default_model)


async def run_agent(model: str, host: str, cwd: str = ".", workflow: str = "manus"):
    """Main REPL loop backed by the Manus-style multi-agent workflow."""
    cwd = os.path.abspath(os.path.expanduser(cwd))
    if not os.path.isdir(cwd):
        tui.print_error(f"Directory not found: {cwd}")
        return

    if workflow != "manus":
        tui.print_error(f"Unsupported workflow: {workflow}")
        return

    session_id = uuid.uuid4().hex[:12]

    db = Database()
    db_ok = db.connect()
    if db_ok:
        tui.print_info(f"🧠 Memory connected (machine: {db.machine_uid[:8]}...)")
    else:
        tui.print_info("💾 Memory offline (PostgreSQL not available — conversations not persisted)")

    engine = ManusWorkflow(
        host=host,
        default_model=model,
        cwd=cwd,
        db=db,
        on_status=tui.update_status,
        on_stream=tui.print_streamed_chunk,
        on_tool_call=tui.print_tool_call,
        on_tool_result=tui.print_tool_result,
        confirm_external=_confirm_external_tool,
    )
    loaded_count, load_errors = engine.custom_skill_load_summary()
    if loaded_count:
        tui.print_info(f"Loaded {loaded_count} custom skill(s).")
    for err in load_errors[:3]:
        tui.print_error(f"Custom skill load warning: {err}")

    tui.print_header(model=model, host=host, workflow=workflow)
    tui.print_info(f"Workspace: {cwd}")
    tui.print_info("Autonomous flow: planner -> dedicated skill agents -> reviewer")
    if db_ok:
        tui.print_info(
            f"Auto-learn timer: enabled every {max(1, AUTO_LEARN_INTERVAL_SECONDS // 3600)}h from DB history (`/autolearn-now` to run now)."
        )
    tui.print_info("Humor loader agent: enabled (personality-aware loading lines).")
    tui.print_info("Tune humor with `/humor-profile ...` and tone with `/personality-save ...`.")

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

    try:
        while True:
            try:
                tui.console.print()
                user_input = tui.console.input("[green]❯[/green] ").strip()
            except (EOFError, KeyboardInterrupt):
                tui.console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                cmd = user_input.lower().split()[0]
                if cmd in ("/quit", "/exit", "/q"):
                    tui.console.print("[dim]Goodbye![/dim]")
                    break
                if cmd == "/help":
                    tui.print_help()
                    continue
                if cmd in ("/clear", "/reset"):
                    engine.reset()
                    tui.console.clear()
                    tui.print_header(model=model, host=host, workflow=workflow)
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
                        "- Personality-aware humor loading agent: enabled\n"
                        f"- Auto-learn timer: every {max(1, AUTO_LEARN_INTERVAL_SECONDS // 3600)}h\n"
                        f"- Workspace: `{cwd}`\n"
                        f"- Fallback model: `{model}`"
                    )
                    continue

                tui.print_error(f"Unknown command: {cmd}")
                continue

            try:
                runtime_state["last_user_msg"] = user_input[:240]
                runtime_state["mood"] = _infer_runtime_mood(user_input)
                runtime_state["language_hint"] = _infer_language_hints([user_input])
                if db and db.connected:
                    db.write_memory(USER_RUNTIME_MOOD_KEY, runtime_state["mood"], model, MEMORY_WRITE_KEY)
                await process_response(engine, user_input, db=db, session_id=session_id)
            except KeyboardInterrupt:
                tui.console.print("\n[dim]Response cancelled.[/dim]")
                continue
    finally:
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
