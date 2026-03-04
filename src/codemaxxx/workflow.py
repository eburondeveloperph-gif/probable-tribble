"""CodeMaxxx — Manus-style autonomous multi-agent workflow engine."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Callable, Optional

from .ollama_client import OllamaClient
from .skills import (
    SKILLS,
    normalize_skill,
    resolve_skill_models,
    route_skill,
    estimate_model_size_gb,
    get_model_variant,
    offline_skill_framework_markdown,
    unified_agent_os_markdown,
    online_mode_skills_markdown,
    full_skill_map_markdown,
    planner_capability_brief,
    online_browser_ui_roadmap_markdown,
    online_browser_ui_roadmap_phase_markdown,
    online_browser_ui_start_sequence_markdown,
    load_custom_skills,
    create_custom_skill as persist_custom_skill,
    custom_skills_markdown,
    supported_custom_tools as list_supported_custom_tools,
    canonical_custom_skill_name,
)
from .tools import ToolResult, execute_tool

TOOL_BLOCK_RE = re.compile(r"```tool\s*\n(.*?)\n```", re.DOTALL)
JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(\{.*?\})\n```", re.DOTALL)
MAX_PLAN_STEPS = 8
MAX_TOOL_ROUNDS = 8


@dataclass
class PlanStep:
    skill: str
    task: str


@dataclass
class StepRun:
    index: int
    skill: str
    task: str
    output: str
    success: bool


@dataclass
class WorkflowResult:
    """Structured workflow output shown back to the user."""

    user_request: str
    plan_steps: list[PlanStep]
    runs: list[StepRun]
    final_summary: str

    def to_markdown(self) -> str:
        lines = [
            "## Autonomous Workflow",
            "",
            f"**Request:** {self.user_request}",
            "",
            "### Plan",
        ]

        for idx, step in enumerate(self.plan_steps, 1):
            lines.append(f"{idx}. [{step.skill}] {step.task}")

        lines.extend(["", "### Execution", ""])

        for run in self.runs:
            icon = "✅" if run.success else "⚠️"
            lines.append(f"**{icon} Step {run.index} · {run.skill}**")
            lines.append(f"Task: {run.task}")
            lines.append(run.output.strip() or "(no output)")
            lines.append("")

        lines.extend(["### Final", self.final_summary.strip() or "Workflow complete."])
        return "\n".join(lines)


class ManusWorkflow:
    """Planner -> skill agents -> reviewer loop inspired by Manus-style execution."""

    def __init__(
        self,
        host: str,
        default_model: str,
        cwd: str,
        db=None,
        on_status: Optional[Callable[[str], None]] = None,
        on_stream: Optional[Callable[[str, str], None]] = None,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
        on_tool_result: Optional[Callable[[ToolResult], None]] = None,
        confirm_external: Optional[Callable[[str, dict], bool]] = None,
    ):
        self.host = host
        self.default_model = default_model
        self.cwd = cwd
        self.db = db
        self._on_status = on_status or (lambda _msg: None)
        self._on_stream = on_stream or (lambda _skill, _chunk: None)
        self._on_tool_call = on_tool_call or (lambda _name, _args: None)
        self._on_tool_result = on_tool_result or (lambda _result: None)
        self._confirm_external = confirm_external or (lambda _name, _args: False)

        loaded, errors = load_custom_skills(cwd)
        self._custom_skill_load_errors = errors
        self._custom_skill_loaded_count = loaded

        self._skill_candidates: dict[str, tuple[str, ...]] = {
            skill: resolve_skill_models(skill, fallback_model=default_model)
            for skill in SKILLS
        }
        self._skill_model_index: dict[str, int] = {skill: 0 for skill in SKILLS}
        self._skill_clients: dict[str, OllamaClient] = {
            skill: self._new_client(skill, self._skill_candidates[skill][0])
            for skill in SKILLS
        }

    def custom_skill_load_summary(self) -> tuple[int, list[str]]:
        return self._custom_skill_loaded_count, list(self._custom_skill_load_errors)

    def _new_client(self, skill: str, model: str) -> OllamaClient:
        spec = SKILLS[normalize_skill(skill)]
        return OllamaClient(model=model, host=self.host, system_prompt=spec.system_prompt)

    def reset(self):
        for skill, client in self._skill_clients.items():
            client.reset(system_prompt=SKILLS[skill].system_prompt)

    def set_default_model(self, model: str):
        self.default_model = model
        for skill in SKILLS:
            candidates = list(resolve_skill_models(skill, fallback_model=model))
            self._skill_candidates[skill] = tuple(candidates)
            self._skill_model_index[skill] = 0
            self._skill_clients[skill] = self._new_client(skill, candidates[0])

    def skills_markdown(self) -> str:
        lines = [
            "## Skill Agents",
            "",
            "| Skill | Agent Alias Model | Base Model | Est. GB | Allowed Tools |",
            "| --- | --- | --- | ---: | --- |",
        ]
        for skill, spec in SKILLS.items():
            model = self._skill_clients[skill].model
            variant = get_model_variant(model)
            base_model = variant.base_model if variant else "-"
            size = estimate_model_size_gb(model)
            size_text = f"{size:.1f}" if size is not None else "n/a"
            tools = ", ".join(spec.tools)
            lines.append(f"| {skill} | `{model}` | `{base_model}` | {size_text} | {tools} |")
        lines.append("")
        lines.append("`ebr-*` models are dedicated skill aliases. If missing, fallback uses the listed base model.")
        lines.append("External automation tools (`gui_automation`, `direct_system_control`, `call_simulation`, `os_automation`) require explicit user approval.")
        lines.append("Use `/skills-custom` to view user-created skills.")
        lines.append("Use `/skill-create <name>` to create one on demand.")
        lines.append("Use `/skills-offline`, `/skills-online`, or `/skills-all` for capability maps.")
        return "\n".join(lines)

    def skills_custom_markdown(self) -> str:
        return custom_skills_markdown(self.cwd)

    def supported_custom_tools(self) -> tuple[str, ...]:
        return list_supported_custom_tools()

    def create_custom_skill(
        self,
        name: str,
        description: str,
        tools: list[str] | tuple[str, ...],
        system_prompt: str = "",
        model_alias: str = "",
        base_model: str = "",
    ) -> tuple[bool, str]:
        ok, msg = persist_custom_skill(
            cwd=self.cwd,
            name=name,
            description=description,
            tools=tools,
            system_prompt=system_prompt,
            model_alias=model_alias,
            base_model=base_model,
        )
        if not ok:
            return False, msg

        skill_name = canonical_custom_skill_name(name)
        if skill_name not in SKILLS:
            return False, f"Skill '{skill_name}' was saved but not loaded into runtime."

        candidates = list(resolve_skill_models(skill_name, fallback_model=self.default_model))
        self._skill_candidates[skill_name] = tuple(candidates)
        self._skill_model_index[skill_name] = 0
        self._skill_clients[skill_name] = self._new_client(skill_name, candidates[0])
        return True, msg

    def skills_offline_markdown(self) -> str:
        return "\n\n".join([offline_skill_framework_markdown(), unified_agent_os_markdown()])

    def skills_online_markdown(self) -> str:
        return online_mode_skills_markdown()

    def skills_all_markdown(self) -> str:
        return full_skill_map_markdown()

    def roadmap_online_markdown(self) -> str:
        return online_browser_ui_roadmap_markdown()

    def roadmap_online_phase_markdown(self, phase_query: str) -> str:
        return online_browser_ui_roadmap_phase_markdown(phase_query)

    def roadmap_online_start_markdown(self) -> str:
        return online_browser_ui_start_sequence_markdown()

    async def run(self, user_request: str) -> WorkflowResult:
        memory_context = self._memory_context()

        self._on_status("planning")
        plan_steps = await self._build_plan(user_request, memory_context)

        runs: list[StepRun] = []
        prior_context = memory_context
        exec_index = 1
        for idx, step in enumerate(plan_steps, 1):
            self._on_status(f"step {idx}/{len(plan_steps)} · {step.skill}")
            run = await self._run_skill_step(
                index=exec_index,
                skill=step.skill,
                task=step.task,
                context=prior_context,
            )
            runs.append(run)
            exec_index += 1
            prior_context = self._build_step_context(runs)

            if not run.success and "self_heal" in SKILLS:
                heal_task = (
                    f"Recover from failed step {idx}.\n"
                    f"Original skill: {step.skill}\n"
                    f"Original task: {step.task}\n"
                    f"Failure output:\n{run.output}\n\n"
                    "Diagnose root cause, apply safe recovery actions, and report whether the workflow can continue."
                )
                self._on_status(f"step {idx} failed · self_heal")
                heal_run = await self._run_skill_step(
                    index=exec_index,
                    skill="self_heal",
                    task=heal_task,
                    context=prior_context,
                )
                runs.append(heal_run)
                exec_index += 1
                prior_context = self._build_step_context(runs)

        self._on_status("reviewing")
        final_summary = await self._final_review(user_request, plan_steps, runs)
        self._on_status("done")

        return WorkflowResult(
            user_request=user_request,
            plan_steps=plan_steps,
            runs=runs,
            final_summary=final_summary,
        )

    def _memory_context(self) -> str:
        if not self.db or not getattr(self.db, "connected", False):
            return "No long-term memory available."
        memories = self.db.read_memory()
        if not memories:
            return "No stored long-term memory entries."
        top = memories[:20]
        return "\n".join(f"- {m['key']}: {m['value']}" for m in top)

    def _build_step_context(self, runs: list[StepRun]) -> str:
        if not runs:
            return "No prior step outputs."
        chunks = []
        for run in runs[-4:]:
            chunks.append(f"Step {run.index} [{run.skill}] {run.task}\n{run.output[:1000]}")
        return "\n\n".join(chunks)

    async def _build_plan(self, user_request: str, memory_context: str) -> list[PlanStep]:
        available_skills = "|".join(sorted(SKILLS.keys()))
        planning_task = (
            "Create an execution plan as strict JSON only.\n"
            "Schema:\n"
            f"{{\"steps\": [{{\"skill\": \"{available_skills}\", \"task\": \"...\"}}]}}\n"
            "Rules:\n"
            "- 2 to 6 steps\n"
            "- each step must have one dedicated skill\n"
            "- keep tasks concrete and execution-ready\n\n"
            f"{planner_capability_brief()}\n\n"
            f"User request:\n{user_request}\n\n"
            f"Long-term memory context:\n{memory_context}"
        )
        plan_run = await self._run_skill_step(
            index=0,
            skill="planner",
            task=planning_task,
            context=memory_context,
            allow_finalize=False,
        )
        steps = self._parse_plan(plan_run.output, user_request)
        return steps

    def _parse_plan(self, raw: str, user_request: str) -> list[PlanStep]:
        text = self._strip_tool_blocks(raw)
        candidates: list[str] = []

        for match in JSON_BLOCK_RE.findall(text):
            candidates.append(match.strip())

        candidates.append(text.strip())

        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            candidates.append(text[brace_start : brace_end + 1])

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except Exception:
                continue

            steps = payload.get("steps") if isinstance(payload, dict) else None
            if not isinstance(steps, list):
                continue

            parsed: list[PlanStep] = []
            for item in steps[:MAX_PLAN_STEPS]:
                if not isinstance(item, dict):
                    continue
                task = str(item.get("task", "")).strip()
                if not task:
                    continue
                skill = normalize_skill(str(item.get("skill", "")))
                if skill not in SKILLS:
                    skill = route_skill(task)
                parsed.append(PlanStep(skill=skill, task=task))

            if parsed:
                return parsed

        # deterministic fallback if planner output is malformed
        primary = route_skill(user_request)
        return [
            PlanStep(skill="researcher", task="Inspect the repository and gather context for this request."),
            PlanStep(skill=primary, task=user_request),
            PlanStep(skill="reviewer", task="Review the result and list remaining risks or next actions."),
        ]

    async def _run_skill_step(
        self,
        index: int,
        skill: str,
        task: str,
        context: str,
        allow_finalize: bool = True,
    ) -> StepRun:
        skill = normalize_skill(skill)
        spec = SKILLS[skill]
        allowed_tools = set(spec.tools)

        prompt = (
            f"[Skill]\n{skill}\n\n"
            f"[Task]\n{task}\n\n"
            f"[Context]\n{context}\n\n"
            "Complete the task. Use tools only if needed. "
            "If you are done, return plain text (no tool blocks)."
        )

        for round_num in range(MAX_TOOL_ROUNDS):
            self._on_status(f"{skill} thinking (round {round_num + 1})")
            response = await self._chat_with_fallback(skill, prompt)
            tool_calls = self._extract_tool_calls(response)
            clean_output = self._strip_tool_blocks(response).strip()

            if not tool_calls:
                return StepRun(
                    index=index,
                    skill=skill,
                    task=task,
                    output=clean_output or response.strip(),
                    success=True,
                )

            self._on_status(f"{skill} executing {len(tool_calls)} tool call(s)")
            tool_outputs: list[str] = []
            for call in tool_calls:
                name = call.get("tool", "")
                args = call.get("args", {})
                if not isinstance(args, dict):
                    args = {}

                if name not in allowed_tools:
                    blocked = ToolResult(
                        success=False,
                        output=f"❌ Tool '{name}' is not allowed for skill '{skill}'.",
                        tool=name,
                    )
                    self._on_tool_result(blocked)
                    tool_outputs.append(f"Tool `{name}` blocked: not allowed for skill `{skill}`.")
                    continue

                self._on_status(f"{skill} running tool: {name}")
                self._on_tool_call(name, args)
                result = execute_tool(
                    name,
                    args,
                    db=self.db,
                    cwd=self.cwd,
                    model=self.default_model,
                    allowed_tools=allowed_tools,
                    confirm_external=self._confirm_external,
                )
                self._on_tool_result(result)
                tool_outputs.append(f"Tool `{name}` result:\n{result.output}")

            if not tool_outputs and allow_finalize:
                return StepRun(
                    index=index,
                    skill=skill,
                    task=task,
                    output=clean_output or "No tool output produced.",
                    success=False,
                )

            prompt = (
                "[Tool results]\n"
                + "\n\n".join(tool_outputs)
                + "\n\nContinue the same task. Return final text when done."
            )

            if round_num == MAX_TOOL_ROUNDS - 1:
                return StepRun(
                    index=index,
                    skill=skill,
                    task=task,
                    output="Max tool rounds reached before finalizing step.",
                    success=False,
                )

        return StepRun(
            index=index,
            skill=skill,
            task=task,
            output="Workflow step terminated unexpectedly.",
            success=False,
        )

    async def _chat_with_fallback(self, skill: str, prompt: str) -> str:
        skill = normalize_skill(skill)
        candidates = self._skill_candidates[skill]

        for _ in range(len(candidates)):
            client = self._skill_clients[skill]
            try:
                chunks: list[str] = []
                async for chunk in client.chat_stream(prompt):
                    chunks.append(chunk)
                    self._on_stream(skill, chunk)
                return "".join(chunks)
            except Exception as exc:
                message = str(exc).lower()
                if "not found" not in message and "model" not in message:
                    raise

                switched = self._switch_skill_model(skill)
                if not switched:
                    raise
                self._on_status(
                    f"{skill}: model unavailable, switched to {self._skill_clients[skill].model}"
                )

        raise RuntimeError(f"No available model candidate for skill '{skill}'.")

    def _switch_skill_model(self, skill: str) -> bool:
        idx = self._skill_model_index[skill]
        candidates = self._skill_candidates[skill]
        if idx + 1 >= len(candidates):
            return False
        new_idx = idx + 1
        self._skill_model_index[skill] = new_idx
        self._skill_clients[skill] = self._new_client(skill, candidates[new_idx])
        return True

    def _extract_tool_calls(self, text: str) -> list[dict]:
        calls: list[dict] = []
        for match in TOOL_BLOCK_RE.findall(text):
            try:
                payload = json.loads(match)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("tool"):
                calls.append(payload)
        return calls

    def _strip_tool_blocks(self, text: str) -> str:
        return TOOL_BLOCK_RE.sub("", text)

    async def _final_review(self, user_request: str, plan_steps: list[PlanStep], runs: list[StepRun]) -> str:
        steps_text = "\n".join(
            f"{idx}. [{step.skill}] {step.task}" for idx, step in enumerate(plan_steps, 1)
        )
        run_text = "\n\n".join(
            f"Step {run.index} ({run.skill})\nTask: {run.task}\nResult: {run.output}" for run in runs
        )

        review_task = (
            "Produce a final user-facing summary.\n"
            "Include:\n"
            "1) what was done\n"
            "2) what was validated\n"
            "3) remaining risks or next actions\n\n"
            f"Original request:\n{user_request}\n\n"
            f"Plan:\n{steps_text}\n\n"
            f"Execution outputs:\n{run_text}"
        )

        review_run = await self._run_skill_step(
            index=len(runs) + 1,
            skill="reviewer",
            task=review_task,
            context=self._build_step_context(runs),
        )
        return review_run.output
