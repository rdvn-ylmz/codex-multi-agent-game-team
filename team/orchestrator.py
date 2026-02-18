#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEAM_DIR = ROOT / "team"
CONFIG_DIR = TEAM_DIR / "config"
STATE_DIR = TEAM_DIR / "state"
TASK_OUTPUT_DIR = STATE_DIR / "task_outputs"
STAGE_TEMPLATE_DIR = TEAM_DIR / "templates" / "stages"
WORKSPACE_CONFIG_FILE = CONFIG_DIR / "workspaces.json"

STATE_FILE = Path(os.getenv("TEAM_STATE_PATH", STATE_DIR / "runtime_state.json"))
EVENTS_FILE = Path(os.getenv("TEAM_EVENTS_PATH", STATE_DIR / "events.jsonl"))

DEFAULT_ROLE_IDS = [
    "orchestrator",
    "concept",
    "game_design",
    "narrative",
    "player_experience",
    "coder",
    "reviewer",
    "qa",
    "security",
    "sre",
    "devops",
    "council_red",
    "council_blue",
    "council_green",
]

DEFAULT_PIPELINE_ROLES = [
    "concept",
    "game_design",
    "narrative",
    "player_experience",
    "coder",
    "reviewer",
    "qa",
    "security",
    "sre",
    "devops",
]

DEFAULT_DEBATE_ROLES = [
    "council_red",
    "council_blue",
    "council_green",
]

DEFAULT_DEBATE_MODERATOR = "orchestrator"

MAX_OUTPUT_FORMAT_RETRIES = int(os.getenv("MAX_OUTPUT_FORMAT_RETRIES", "1"))
OUTPUT_CONTRACT_REQUIRED_FIELDS = ["task_id", "owner", "acceptance_criteria", "artifacts"]
OUTPUT_CONTRACT_ALLOWED_STATUS = {
    "done",
    "needs_review",
    "needs_changes",
    "blocked",
    "needs_fix_format",
    "ready_for_handoff",
    "approved_or_changes_requested",
    "passed_or_failed",
}

ROLE_REQUIRED_ARTIFACT_PATHS: dict[str, list[str]] = {
    "concept": ["docs/concept.md"],
    "game_design": ["docs/game_design.md", "docs/balance_knobs.md"],
    "narrative": ["docs/narrative.md", "assets/text/ui_copy.md"],
    "player_experience": ["docs/ux_flow.md", "docs/ftue.md"],
}

REQUIRED_REPORT_SECTIONS = [
    "## Task Meta",
    "## Context I Need",
    "## Plan",
    "## Work / Decisions",
    "## Artifacts",
    "## Handoff",
]


@dataclass
class CodexResult:
    return_code: int
    session_id: str | None
    message: str
    stderr: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASK_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _parse_yaml_id_list(path: Path, key: str) -> list[str]:
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    key_pattern = re.compile(rf"^(\s*){re.escape(key)}\s*:\s*$")
    item_pattern = re.compile(r"^\s*-\s*([a-zA-Z0-9_-]+)\s*$")

    key_indent: int | None = None
    values: list[str] = []

    for line in lines:
        if key_indent is None:
            match = key_pattern.match(line)
            if match:
                key_indent = len(match.group(1))
            continue

        stripped = line.strip()
        if not stripped:
            continue

        indent = len(line) - len(line.lstrip(" "))
        if indent <= key_indent:
            break

        item_match = item_pattern.match(line)
        if item_match:
            values.append(item_match.group(1))

    return values


def read_role_ids() -> list[str]:
    roles_file = CONFIG_DIR / "roles.yaml"
    if not roles_file.exists():
        return DEFAULT_ROLE_IDS

    role_ids: list[str] = []
    pattern = re.compile(r"^\s*-\s*id:\s*([a-zA-Z0-9_-]+)\s*$")
    for line in roles_file.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            role_ids.append(match.group(1))

    return role_ids or DEFAULT_ROLE_IDS


def read_default_pipeline() -> list[str]:
    workflow_file = CONFIG_DIR / "workflow.yaml"
    roles = _parse_yaml_id_list(workflow_file, "default_pipeline")
    return roles or DEFAULT_PIPELINE_ROLES


def read_default_debate_roles() -> list[str]:
    workflow_file = CONFIG_DIR / "workflow.yaml"
    roles = _parse_yaml_id_list(workflow_file, "default_debate")
    return roles or DEFAULT_DEBATE_ROLES


def read_default_debate_moderator() -> str:
    workflow_file = CONFIG_DIR / "workflow.yaml"
    if not workflow_file.exists():
        return DEFAULT_DEBATE_MODERATOR

    pattern = re.compile(r"^\s*debate_moderator\s*:\s*([a-zA-Z0-9_-]+)\s*$")
    for line in workflow_file.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1)
    return DEFAULT_DEBATE_MODERATOR


def load_stage_template(role: str) -> str:
    template_file = STAGE_TEMPLATE_DIR / f"{role}.md"
    if template_file.exists():
        return template_file.read_text(encoding="utf-8").strip()
    return ""


def load_orchestrator_system_prompt() -> str:
    system_file = TEAM_DIR / "prompts" / "orchestrator_system.md"
    if system_file.exists():
        return system_file.read_text(encoding="utf-8").strip()
    return ""


def read_workspace_config() -> dict[str, Any]:
    if WORKSPACE_CONFIG_FILE.exists():
        with WORKSPACE_CONFIG_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data

    return {
        "use_role_workspaces_if_present": True,
        "roles": {},
    }


def resolve_role_workdir(role: str) -> Path:
    config = read_workspace_config()
    use_role_workspaces = bool(config.get("use_role_workspaces_if_present", True))
    if not use_role_workspaces:
        return ROOT

    roles_map = config.get("roles", {})
    if not isinstance(roles_map, dict):
        return ROOT

    role_path = roles_map.get(role)
    if not role_path:
        return ROOT

    workdir = (ROOT / str(role_path)).resolve()
    if workdir.exists() and workdir.is_dir():
        return workdir
    return ROOT


def _extract_json_from_fenced_block(text: str) -> dict[str, Any] | None:
    marker = "```json"
    lower_text = text.lower()
    lower_marker = marker.lower()
    start = lower_text.rfind(lower_marker)
    if start < 0:
        return None

    block_start = text.find("\n", start)
    if block_start < 0:
        return None
    block_start += 1

    end = text.find("```", block_start)
    if end < 0:
        return None

    candidate = text[block_start:end].strip()
    if not candidate:
        return None

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        return data
    return None


def extract_output_contract(text: str) -> dict[str, Any] | None:
    contract = _extract_json_from_fenced_block(text)
    if contract:
        return contract

    start = text.rfind("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    candidate = text[start : end + 1].strip()

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        return data
    return None


def _artifact_paths_from_contract(contract: dict[str, Any]) -> list[str]:
    artifacts = contract.get("artifacts")
    if not isinstance(artifacts, list):
        return []

    paths: list[str] = []
    for artifact in artifacts:
        if isinstance(artifact, str):
            paths.append(artifact.strip())
            continue
        if not isinstance(artifact, dict):
            continue

        value = artifact.get("value")
        if isinstance(value, str):
            paths.append(value.strip())
            continue
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    paths.append(item.strip())
    return [path for path in paths if path]


def validate_output_contract(role: str, task: dict[str, Any], contract: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if not contract:
        return ["Missing JSON output contract footer."]

    for field in OUTPUT_CONTRACT_REQUIRED_FIELDS:
        if field not in contract:
            errors.append(f"Missing required field: {field}")

    task_id = str(contract.get("task_id", ""))
    if task_id and task_id != str(task.get("id")):
        errors.append(f"task_id mismatch: expected {task.get('id')}, got {task_id}")

    owner = str(contract.get("owner", ""))
    if owner and owner != role:
        errors.append(f"owner mismatch: expected {role}, got {owner}")

    status = str(contract.get("status", "done")).strip()
    if status and status not in OUTPUT_CONTRACT_ALLOWED_STATUS:
        errors.append(f"Invalid status: {status}")

    artifacts = contract.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) == 0:
        errors.append("artifacts must be a non-empty list")

    acceptance = contract.get("acceptance_criteria")
    if not isinstance(acceptance, list) or len(acceptance) == 0:
        errors.append("acceptance_criteria must be a non-empty list")

    handoff_to = contract.get("handoff_to")
    if not isinstance(handoff_to, list) or len(handoff_to) == 0:
        errors.append("handoff_to must be a non-empty list")

    next_actions = contract.get("next_role_action_items")
    if not isinstance(next_actions, list) or len(next_actions) == 0:
        errors.append("next_role_action_items must be a non-empty list")
    else:
        for idx, action_item in enumerate(next_actions, start=1):
            if not isinstance(action_item, dict):
                errors.append(f"next_role_action_items[{idx}] must be an object")
                continue
            role_value = action_item.get("role")
            items_value = action_item.get("items")
            if not isinstance(role_value, str) or not role_value.strip():
                errors.append(f"next_role_action_items[{idx}].role must be a non-empty string")
            if not isinstance(items_value, list) or len(items_value) == 0:
                errors.append(f"next_role_action_items[{idx}].items must be a non-empty list")
            elif not all(isinstance(item, str) and item.strip() for item in items_value):
                errors.append(f"next_role_action_items[{idx}].items must contain non-empty strings")

    required_paths = ROLE_REQUIRED_ARTIFACT_PATHS.get(role, [])
    if required_paths:
        paths = _artifact_paths_from_contract(contract)
        for required_path in required_paths:
            if required_path.endswith("/"):
                if not any(path.startswith(required_path) for path in paths):
                    errors.append(f"Missing required artifact path prefix: {required_path}")
            elif required_path not in paths:
                errors.append(f"Missing required artifact path: {required_path}")

    return errors


def validate_report_structure(message: str) -> list[str]:
    errors: list[str] = []
    lower_message = message.lower()
    for section in REQUIRED_REPORT_SECTIONS:
        if section.lower() not in lower_message:
            errors.append(f"Missing report section: {section}")
    return errors


def validate_task_output(role: str, task: dict[str, Any], message: str, contract: dict[str, Any] | None) -> list[str]:
    errors = validate_output_contract(role, task, contract)
    errors.extend(validate_report_structure(message))
    return errors


def format_contract_error_feedback(errors: list[str], task: dict[str, Any], role: str) -> str:
    bullet_lines = "\n".join(f"- {err}" for err in errors)
    return (
        "Your previous response did not satisfy the required output contract.\n"
        f"Task ID: {task['id']}\n"
        f"Role: {role}\n"
        "Fix only the response formatting/content contract and reply again.\n"
        "Do not omit the markdown sections and the final JSON block.\n"
        "Validation errors:\n"
        f"{bullet_lines}\n"
    )


def base_config() -> dict[str, Any]:
    return {
        "profile": os.getenv("TEAM_PROFILE", "low-spec"),
        "max_active_sessions": int(os.getenv("MAX_ACTIVE_SESSIONS", "2")),
        "agent_idle_timeout_sec": int(os.getenv("AGENT_IDLE_TIMEOUT_SEC", "90")),
        "local_test_scope": os.getenv("LOCAL_TEST_SCOPE", "smoke"),
        "use_docker": os.getenv("USE_DOCKER", "0") in {"1", "true", "yes"},
        "run_full_tests_in_ci": os.getenv("RUN_FULL_TESTS_IN_CI", "1") in {"1", "true", "yes"},
    }


def new_state() -> dict[str, Any]:
    now = utc_now()
    role_ids = read_role_ids()
    return {
        "version": 3,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "stopped_at": None,
        "status": "stopped",
        "config": base_config(),
        "roles": {
            role_id: {
                "session_id": None,
                "state": "idle",
                "last_active_at": None,
                "tasks_completed": 0,
            }
            for role_id in role_ids
        },
        "tasks": [],
        "pipelines": [],
        "debates": [],
    }


def ensure_state_schema(state: dict[str, Any]) -> bool:
    changed = False

    if "version" not in state:
        state["version"] = 3
        changed = True

    if "pipelines" not in state:
        state["pipelines"] = []
        changed = True

    if "debates" not in state:
        state["debates"] = []
        changed = True

    if "config" not in state:
        state["config"] = base_config()
        changed = True

    if "roles" not in state:
        state["roles"] = {}
        changed = True

    for role in read_role_ids():
        if role not in state["roles"]:
            state["roles"][role] = {
                "session_id": None,
                "state": "idle",
                "last_active_at": None,
                "tasks_completed": 0,
            }
            changed = True

    if "tasks" not in state:
        state["tasks"] = []
        changed = True

    for task in state["tasks"]:
        if "metadata" not in task:
            task["metadata"] = {}
            changed = True

    return changed


def load_state() -> dict[str, Any]:
    ensure_dirs()
    if not STATE_FILE.exists():
        state = new_state()
        save_state(state)
        return state

    with STATE_FILE.open("r", encoding="utf-8") as handle:
        state: dict[str, Any] = json.load(handle)

    if ensure_state_schema(state):
        save_state(state)

    return state


def save_state(state: dict[str, Any]) -> None:
    ensure_dirs()
    state["updated_at"] = utc_now()
    backup = STATE_FILE.with_suffix(".last.json")
    if STATE_FILE.exists():
        backup.write_text(STATE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def append_event(event_type: str, payload: dict[str, Any] | None = None) -> None:
    ensure_dirs()
    row = {
        "timestamp": utc_now(),
        "event": event_type,
        "payload": payload or {},
    }
    with EVENTS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    process = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    return process.returncode, process.stdout.strip(), process.stderr.strip()


def auth_check() -> tuple[bool, list[str]]:
    checks: list[tuple[str, list[str]]] = [
        ("codex", ["codex", "login", "status"]),
        ("github", ["gh", "auth", "status"]),
    ]
    errors: list[str] = []
    for label, cmd in checks:
        code, _stdout, stderr = run_cmd(cmd)
        if code != 0:
            errors.append(f"{label} auth check failed: {stderr or 'unknown error'}")

    return (len(errors) == 0, errors)


def next_task_id(state: dict[str, Any]) -> str:
    if not state["tasks"]:
        return "TASK-0001"

    last = max(int(task["id"].split("-")[1]) for task in state["tasks"])
    return f"TASK-{last + 1:04d}"


def next_pipeline_id(state: dict[str, Any]) -> str:
    pipelines = state.get("pipelines", [])
    if not pipelines:
        return "PIPE-0001"

    last = max(int(pipe["id"].split("-")[1]) for pipe in pipelines)
    return f"PIPE-{last + 1:04d}"


def next_debate_id(state: dict[str, Any]) -> str:
    debates = state.get("debates", [])
    if not debates:
        return "DEBATE-0001"

    last = max(int(debate["id"].split("-")[1]) for debate in debates)
    return f"DEBATE-{last + 1:04d}"


def ensure_role(state: dict[str, Any], role: str) -> None:
    if role not in state["roles"]:
        state["roles"][role] = {
            "session_id": None,
            "state": "idle",
            "last_active_at": None,
            "tasks_completed": 0,
        }


def enqueue_task(
    state: dict[str, Any],
    role: str,
    title: str,
    description: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_role(state, role)
    now = utc_now()
    task_metadata = metadata.copy() if metadata else {}
    task = {
        "id": next_task_id(state),
        "role": role,
        "title": title.strip(),
        "description": description.strip(),
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
        "session_id": None,
        "output_path": None,
        "error": None,
        "metadata": task_metadata,
    }
    state["tasks"].append(task)
    append_event(
        "task_enqueued",
        {
            "task_id": task["id"],
            "role": role,
            "title": title,
            "pipeline_id": task_metadata.get("pipeline_id"),
        },
    )
    return task


def create_pipeline(
    state: dict[str, Any],
    title: str,
    brief: str,
    roles: list[str],
) -> dict[str, Any]:
    pipeline_id = next_pipeline_id(state)
    now = utc_now()

    task_ids: list[str] = []
    depends_on: list[str] = []

    for index, role in enumerate(roles, start=1):
        stage_template = load_stage_template(role)
        stage_title = f"[{pipeline_id}] {title} :: {role}"
        stage_description = (
            f"Pipeline ID: {pipeline_id}\n"
            f"Stage: {index}/{len(roles)}\n"
            f"Role: {role}\n"
            f"Project brief:\n{brief}\n\n"
            "Execution notes:\n"
            "- Keep output concise and artifact-based.\n"
            "- Read handoff context from previous stage outputs if available.\n"
            "- Include risks and next handoff in final report.\n"
            "- Follow output contract schema at team/config/output_contract.schema.json.\n"
        )
        if stage_template:
            stage_description += "\nStage template:\n"
            stage_description += stage_template + "\n"
        task = enqueue_task(
            state,
            role,
            stage_title,
            stage_description,
            metadata={
                "pipeline_id": pipeline_id,
                "stage_index": index,
                "stage_count": len(roles),
                "depends_on_task_ids": depends_on.copy(),
            },
        )
        task_ids.append(task["id"])
        depends_on = [task["id"]]

    pipeline = {
        "id": pipeline_id,
        "title": title.strip(),
        "brief": brief.strip(),
        "roles": roles,
        "task_ids": task_ids,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "last_error": None,
    }
    state.setdefault("pipelines", []).append(pipeline)
    append_event(
        "pipeline_created",
        {
            "pipeline_id": pipeline_id,
            "title": title,
            "roles": roles,
            "task_ids": task_ids,
        },
    )
    return pipeline


def create_debate(
    state: dict[str, Any],
    title: str,
    topic: str,
    roles: list[str],
    moderator: str,
) -> dict[str, Any]:
    debate_id = next_debate_id(state)
    now = utc_now()

    participant_task_ids: list[str] = []
    for role in roles:
        task = enqueue_task(
            state,
            role,
            f"[{debate_id}] {title} :: {role}",
            (
                f"Debate ID: {debate_id}\n"
                f"Role: {role}\n"
                f"Topic:\n{topic}\n\n"
                "Debate instructions:\n"
                "- Argue one distinct approach with concrete tradeoffs.\n"
                "- Challenge assumptions and mention risks.\n"
                "- Give actionable recommendations for the moderator.\n"
                "- Follow output contract schema at team/config/output_contract.schema.json.\n"
            ),
            metadata={
                "debate_id": debate_id,
                "debate_stage": "position",
                "depends_on_task_ids": [],
            },
        )
        participant_task_ids.append(task["id"])

    moderator_task = enqueue_task(
        state,
        moderator,
        f"[{debate_id}] {title} :: moderator",
        (
            f"Debate ID: {debate_id}\n"
            f"Moderator: {moderator}\n"
            f"Topic:\n{topic}\n\n"
            "Moderator instructions:\n"
            "- Read all participant outputs.\n"
            "- Summarize agreements and disagreements.\n"
            "- Produce final recommendation with rationale and next tasks.\n"
            "- Follow output contract schema at team/config/output_contract.schema.json.\n"
        ),
        metadata={
            "debate_id": debate_id,
            "debate_stage": "moderation",
            "depends_on_task_ids": participant_task_ids.copy(),
        },
    )

    debate = {
        "id": debate_id,
        "title": title.strip(),
        "topic": topic.strip(),
        "roles": roles,
        "moderator": moderator,
        "participant_task_ids": participant_task_ids,
        "moderator_task_id": moderator_task["id"],
        "task_ids": participant_task_ids + [moderator_task["id"]],
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "last_error": None,
    }
    state.setdefault("debates", []).append(debate)
    append_event(
        "debate_created",
        {
            "debate_id": debate_id,
            "title": title,
            "roles": roles,
            "moderator": moderator,
            "task_ids": debate["task_ids"],
        },
    )
    return debate


def get_task(state: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for task in state["tasks"]:
        if task["id"] == task_id:
            return task
    return None


def get_pipeline(state: dict[str, Any], pipeline_id: str) -> dict[str, Any] | None:
    for pipeline in state.get("pipelines", []):
        if pipeline["id"] == pipeline_id:
            return pipeline
    return None


def get_debate(state: dict[str, Any], debate_id: str) -> dict[str, Any] | None:
    for debate in state.get("debates", []):
        if debate["id"] == debate_id:
            return debate
    return None


def task_dependencies(task: dict[str, Any]) -> list[str]:
    metadata = task.get("metadata") or {}
    deps = metadata.get("depends_on_task_ids")
    if not isinstance(deps, list):
        return []
    return [str(dep) for dep in deps]


def is_task_ready(state: dict[str, Any], task: dict[str, Any]) -> bool:
    for dep_id in task_dependencies(task):
        dep_task = get_task(state, dep_id)
        if not dep_task or dep_task.get("status") != "done":
            return False
    return True


def next_queued_task(state: dict[str, Any]) -> dict[str, Any] | None:
    for task in state["tasks"]:
        if task["status"] == "queued" and is_task_ready(state, task):
            return task
    return None


def queued_but_blocked(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        task
        for task in state["tasks"]
        if task["status"] == "queued" and not is_task_ready(state, task)
    ]


def load_role_prompt(role: str) -> str:
    prompt_file = TEAM_DIR / "prompts" / f"{role}.md"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8").strip()
    return ""


def codex_command(prompt: str, session_id: str | None) -> list[str]:
    cmd: list[str]
    if session_id:
        cmd = ["codex", "exec", "resume", session_id, prompt]
    else:
        cmd = ["codex", "exec", prompt]

    model = os.getenv("CODEX_MODEL", "").strip()
    if model:
        cmd.extend(["-m", model])

    cmd.extend(["--json", "--dangerously-bypass-approvals-and-sandbox"])
    return cmd


def build_low_spec_prompt_rules() -> str:
    return (
        "Low-spec runtime rules:\n"
        "- Keep changes minimal and focused.\n"
        "- Minimize file count and command count.\n"
        "- Prefer quick local checks only; heavy tests stay in CI.\n"
        "- Keep planning concise and execution-oriented.\n"
    )


def build_role_gate_guidance(role: str) -> str:
    role_gate_map: dict[str, list[str]] = {
        "coder": [
            "Before marking done, run fast local checks aligned with lint + unit_tests.",
            "If local resources are constrained, run subset locally and state that full suite is CI-only.",
        ],
        "reviewer": [
            "Provide file-referenced findings for architecture_check and review_approval.",
            "Return explicit merge recommendation: approve or needs_changes.",
        ],
        "qa": [
            "List smoke/regression flows executed and expected outcomes.",
            "Call out pass/fail status per flow.",
        ],
        "security": [
            "Provide threat model delta in STRIDE-style bullets where relevant.",
            "Include severity, exploit scenario, and concrete fix recommendation per issue.",
        ],
        "sre": [
            "Provide reliability_slo assumptions and observability baseline.",
            "Include rollback safety checks and missing signals.",
        ],
        "devops": [
            "Include deploy checklist, rollback plan, and release gate confirmation.",
            "Flag unknowns that block safe release.",
        ],
    }
    role_rules = role_gate_map.get(role, [])
    if not role_rules:
        return ""
    return "Gate-aligned role requirements:\n" + "\n".join(f"- {rule}" for rule in role_rules) + "\n"


def build_output_contract_prompt(task: dict[str, Any], role: str) -> str:
    return (
        "Output contract (strict):\n"
        "- Include markdown sections in this exact order:\n"
        "  1) Task Meta\n"
        "  2) Context I Need\n"
        "  3) Plan\n"
        "  4) Work / Decisions\n"
        "  5) Artifacts\n"
        "  6) Handoff\n"
        "- End response with ONE fenced JSON block (```json ... ```).\n"
        "- JSON required fields: task_id, owner, status, acceptance_criteria, artifacts, risks, handoff_to, next_role_action_items.\n"
        f"- task_id must be exactly {task['id']}.\n"
        f"- owner must be exactly {role}.\n"
    )


def build_handoff_context(state: dict[str, Any], task: dict[str, Any]) -> str:
    dep_ids = task_dependencies(task)
    if not dep_ids:
        return ""

    chunks: list[str] = []
    for dep_id in dep_ids:
        dep_task = get_task(state, dep_id)
        if not dep_task:
            continue

        output_path = dep_task.get("output_path")
        if not output_path:
            continue

        abs_path = ROOT / output_path
        if not abs_path.exists():
            continue

        content = abs_path.read_text(encoding="utf-8")
        content = content[:4000].strip()
        if not content:
            continue

        chunks.append(
            f"Handoff from {dep_id} ({dep_task.get('role')}):\n"
            f"{content}"
        )

    if not chunks:
        return ""

    return "\n\n".join(chunks)


def run_codex_task(
    role: str,
    task: dict[str, Any],
    session_id: str | None,
    handoff_context: str,
    workdir: Path,
    correction_feedback: str = "",
) -> CodexResult:
    system_prompt = load_orchestrator_system_prompt()
    role_prompt = load_role_prompt(role)
    contract_prompt = build_output_contract_prompt(task, role)
    prompt = (
        f"Role: {role}\n"
        f"Task ID: {task['id']}\n"
        f"Title: {task['title']}\n"
        f"Description:\n{task['description']}\n\n"
        f"Work directory: {workdir}\n"
        "Work in the current repository.\n"
        f"{build_low_spec_prompt_rules()}\n"
        f"{build_role_gate_guidance(role)}\n"
        f"{contract_prompt}\n"
    )

    if handoff_context:
        prompt += "\nPipeline handoff context from previous stages:\n"
        prompt += handoff_context + "\n"

    if correction_feedback:
        prompt += "\nContract correction request:\n"
        prompt += correction_feedback + "\n"

    prefix_parts: list[str] = []
    if system_prompt:
        prefix_parts.append(system_prompt)
    if role_prompt:
        prefix_parts.append(role_prompt)
    if prefix_parts:
        prompt = "\n\n".join(prefix_parts + [prompt])

    cmd = codex_command(prompt, session_id)
    process = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir)

    out_lines = process.stdout.splitlines()
    messages: list[str] = []
    new_session_id = session_id

    for line in out_lines:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        if data.get("type") == "thread.started" and data.get("thread_id"):
            new_session_id = data["thread_id"]

        if data.get("type") == "item.completed":
            item = data.get("item", {})
            if item.get("type") == "agent_message" and item.get("text"):
                messages.append(item["text"].strip())

    message = "\n\n".join(msg for msg in messages if msg).strip()
    return CodexResult(
        return_code=process.returncode,
        session_id=new_session_id,
        message=message,
        stderr=(process.stderr or "").strip(),
    )


def write_task_output(task_id: str, content: str) -> str:
    ensure_dirs()
    out_file = TASK_OUTPUT_DIR / f"{task_id}.md"
    out_file.write_text(content.strip() + "\n", encoding="utf-8")
    return str(out_file.relative_to(ROOT))


def recover_inflight_tasks(state: dict[str, Any], reason: str) -> int:
    recovered = 0
    for task in state.get("tasks", []):
        if task.get("status") == "running":
            task["status"] = "queued"
            task["updated_at"] = utc_now()
            task["started_at"] = None
            task["finished_at"] = None
            task["error"] = f"Recovered inflight task: {reason}"
            recovered += 1
            append_event(
                "task_requeued_from_recovery",
                {"task_id": task.get("id"), "reason": reason},
            )
    return recovered


def recompute_pipeline_status(state: dict[str, Any], pipeline_id: str) -> str | None:
    pipeline = get_pipeline(state, pipeline_id)
    if not pipeline:
        return None

    task_ids = pipeline.get("task_ids", [])
    statuses: list[str] = []
    for task_id in task_ids:
        task = get_task(state, task_id)
        statuses.append(task.get("status") if task else "missing")

    if any(status == "failed" for status in statuses):
        next_status = "failed"
    elif statuses and all(status == "done" for status in statuses):
        next_status = "done"
    elif any(status == "running" for status in statuses):
        next_status = "running"
    elif any(status == "done" for status in statuses):
        next_status = "in_progress"
    elif any(status == "queued" for status in statuses):
        next_status = "queued"
    else:
        next_status = "queued"

    previous = pipeline.get("status")
    pipeline["status"] = next_status
    pipeline["updated_at"] = utc_now()

    if previous != next_status:
        append_event(
            "pipeline_status_changed",
            {
                "pipeline_id": pipeline_id,
                "from": previous,
                "to": next_status,
            },
        )

    return next_status


def refresh_all_pipelines(state: dict[str, Any]) -> None:
    for pipeline in state.get("pipelines", []):
        recompute_pipeline_status(state, pipeline["id"])


def recompute_debate_status(state: dict[str, Any], debate_id: str) -> str | None:
    debate = get_debate(state, debate_id)
    if not debate:
        return None

    task_ids = debate.get("task_ids", [])
    statuses: list[str] = []
    for task_id in task_ids:
        task = get_task(state, task_id)
        statuses.append(task.get("status") if task else "missing")

    if any(status == "failed" for status in statuses):
        next_status = "failed"
    elif statuses and all(status == "done" for status in statuses):
        next_status = "done"
    elif any(status == "running" for status in statuses):
        next_status = "running"
    elif any(status == "done" for status in statuses):
        next_status = "in_progress"
    elif any(status == "queued" for status in statuses):
        next_status = "queued"
    else:
        next_status = "queued"

    previous = debate.get("status")
    debate["status"] = next_status
    debate["updated_at"] = utc_now()

    if previous != next_status:
        append_event(
            "debate_status_changed",
            {
                "debate_id": debate_id,
                "from": previous,
                "to": next_status,
            },
        )

    return next_status


def refresh_all_debates(state: dict[str, Any]) -> None:
    for debate in state.get("debates", []):
        recompute_debate_status(state, debate["id"])


def start_team(args: argparse.Namespace) -> int:
    state = load_state()

    ok, errors = auth_check()
    if not ok and not args.skip_auth_check:
        print("Auth checks failed:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    if not ok and args.skip_auth_check:
        append_event("auth_check_skipped_with_errors", {"errors": errors})

    state["status"] = "running"
    if not state.get("started_at"):
        state["started_at"] = utc_now()
    state["stopped_at"] = None
    state["config"] = base_config()

    for role in read_role_ids():
        ensure_role(state, role)
    for role_data in state["roles"].values():
        role_data["state"] = "idle"

    recovered = recover_inflight_tasks(state, "team start")
    if recovered:
        append_event("recovery_applied", {"count": recovered, "reason": "team start"})

    refresh_all_pipelines(state)
    refresh_all_debates(state)
    save_state(state)
    append_event("team_started", {"profile": state["config"].get("profile")})

    print("Team status: running")
    print(f"Profile: {state['config'].get('profile')}")
    print(f"State file: {STATE_FILE}")
    return 0


def stop_team(_args: argparse.Namespace) -> int:
    state = load_state()
    recovered = recover_inflight_tasks(state, "team stop")
    state["status"] = "stopped"
    state["stopped_at"] = utc_now()
    for role_data in state["roles"].values():
        role_data["state"] = "idle"
    refresh_all_pipelines(state)
    refresh_all_debates(state)
    save_state(state)
    append_event("team_stopped", {"stopped_at": state["stopped_at"]})
    if recovered:
        append_event("recovery_applied", {"count": recovered, "reason": "team stop"})
    print("Team status: stopped")
    return 0


def resume_team(args: argparse.Namespace) -> int:
    state = load_state()

    ok, errors = auth_check()
    if not ok and not args.skip_auth_check:
        print("Auth checks failed:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    state["status"] = "running"
    state["stopped_at"] = None
    for role_data in state["roles"].values():
        role_data["state"] = "idle"
    recovered = recover_inflight_tasks(state, "team resume")
    if recovered:
        append_event("recovery_applied", {"count": recovered, "reason": "team resume"})
    refresh_all_pipelines(state)
    refresh_all_debates(state)
    save_state(state)
    append_event("team_resumed", {})
    print("Team status: running (resumed)")
    return 0


def status_team(args: argparse.Namespace) -> int:
    state = load_state()
    refresh_all_pipelines(state)
    refresh_all_debates(state)
    save_state(state)

    queued = sum(1 for task in state["tasks"] if task["status"] == "queued")
    running = sum(1 for task in state["tasks"] if task["status"] == "running")
    failed = sum(1 for task in state["tasks"] if task["status"] == "failed")
    done = sum(1 for task in state["tasks"] if task["status"] == "done")

    queued_pipes = sum(1 for pipe in state["pipelines"] if pipe.get("status") == "queued")
    running_pipes = sum(1 for pipe in state["pipelines"] if pipe.get("status") in {"running", "in_progress"})
    done_pipes = sum(1 for pipe in state["pipelines"] if pipe.get("status") == "done")
    failed_pipes = sum(1 for pipe in state["pipelines"] if pipe.get("status") == "failed")

    queued_debates = sum(1 for debate in state["debates"] if debate.get("status") == "queued")
    running_debates = sum(
        1 for debate in state["debates"] if debate.get("status") in {"running", "in_progress"}
    )
    done_debates = sum(1 for debate in state["debates"] if debate.get("status") == "done")
    failed_debates = sum(1 for debate in state["debates"] if debate.get("status") == "failed")

    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=True))
        return 0

    print(f"Team status: {state['status']}")
    print(f"Profile: {state['config'].get('profile')}")
    print(f"Started at: {state.get('started_at')}")
    print(f"Stopped at: {state.get('stopped_at')}")
    print(f"Tasks: queued={queued} running={running} done={done} failed={failed}")
    print(f"Pipelines: queued={queued_pipes} running={running_pipes} done={done_pipes} failed={failed_pipes}")
    print(
        "Debates: "
        f"queued={queued_debates} running={running_debates} done={done_debates} failed={failed_debates}"
    )
    print("Roles:")
    for role, info in sorted(state["roles"].items()):
        sid = info.get("session_id")
        short_sid = sid[:8] + "..." if sid else "-"
        print(
            f"- {role}: state={info.get('state')} session={short_sid} "
            f"completed={info.get('tasks_completed', 0)}"
        )

    return 0


def enqueue(args: argparse.Namespace) -> int:
    state = load_state()
    task = enqueue_task(state, args.role, args.title, args.description)
    save_state(state)
    print(f"Enqueued {task['id']} for role={task['role']}")
    return 0


def enqueue_pipeline(args: argparse.Namespace) -> int:
    state = load_state()
    roles = [part.strip() for part in (args.roles or "").split(",") if part.strip()]
    if not roles:
        roles = read_default_pipeline()

    pipeline = create_pipeline(state, args.title, args.brief, roles)
    refresh_all_pipelines(state)
    save_state(state)

    print(f"Created {pipeline['id']} with {len(pipeline['task_ids'])} task(s)")
    for task_id in pipeline["task_ids"]:
        task = get_task(state, task_id)
        role = task["role"] if task else "unknown"
        print(f"- {task_id} [{role}]")
    return 0


def enqueue_debate(args: argparse.Namespace) -> int:
    state = load_state()
    roles = [part.strip() for part in (args.roles or "").split(",") if part.strip()]
    if not roles:
        roles = read_default_debate_roles()

    moderator = (args.moderator or read_default_debate_moderator()).strip()
    debate = create_debate(state, args.title, args.topic, roles, moderator)
    refresh_all_debates(state)
    save_state(state)

    print(f"Created {debate['id']} with {len(debate['task_ids'])} task(s)")
    for task_id in debate["task_ids"]:
        task = get_task(state, task_id)
        role = task["role"] if task else "unknown"
        print(f"- {task_id} [{role}]")
    return 0


def _dispatch_task_object(state: dict[str, Any], task: dict[str, Any]) -> int:
    role = task["role"]
    ensure_role(state, role)
    workdir = resolve_role_workdir(role)

    task["status"] = "running"
    task["started_at"] = utc_now()
    task["updated_at"] = utc_now()

    role_state = state["roles"][role]
    role_state["state"] = "busy"

    metadata = task.get("metadata") or {}
    pipeline_id = metadata.get("pipeline_id")
    debate_id = metadata.get("debate_id")
    save_state(state)
    append_event(
        "task_started",
        {
            "task_id": task["id"],
            "role": role,
            "pipeline_id": pipeline_id,
            "debate_id": debate_id,
            "workdir": str(workdir),
        },
    )

    handoff_context = build_handoff_context(state, task)
    attempts = 0
    result: CodexResult | None = None
    contract: dict[str, Any] | None = None
    contract_errors: list[str] = []
    correction_feedback = ""

    while attempts <= MAX_OUTPUT_FORMAT_RETRIES:
        attempts += 1
        result = run_codex_task(
            role,
            task,
            role_state.get("session_id"),
            handoff_context,
            workdir,
            correction_feedback=correction_feedback,
        )

        if result.session_id:
            role_state["session_id"] = result.session_id

        if result.return_code != 0:
            break

        contract = extract_output_contract(result.message)
        contract_errors = validate_task_output(role, task, result.message, contract)
        if not contract_errors:
            break

        append_event(
            "task_output_contract_invalid",
            {
                "task_id": task["id"],
                "role": role,
                "attempt": attempts,
                "errors": contract_errors,
            },
        )
        correction_feedback = format_contract_error_feedback(contract_errors, task, role)

    if not result:
        task["status"] = "failed"
        task["error"] = "Internal error: task execution did not produce a result"
        task["finished_at"] = utc_now()
        role_state["state"] = "idle"
        role_state["last_active_at"] = utc_now()
        save_state(state)
        return 1

    if result.return_code == 0 and not contract_errors:
        task["status"] = "done"
        task["error"] = None
        content = result.message or "No message returned by Codex."
        output_path = write_task_output(task["id"], content)
        task["output_path"] = output_path
        task["finished_at"] = utc_now()
        task.setdefault("metadata", {})["output_contract"] = contract
        role_state["tasks_completed"] = int(role_state.get("tasks_completed", 0)) + 1
        append_event(
            "task_completed",
            {
                "task_id": task["id"],
                "role": role,
                "pipeline_id": pipeline_id,
                "debate_id": debate_id,
                "workdir": str(workdir),
                "output_path": output_path,
                "attempts": attempts,
            },
        )
        print(f"Completed {task['id']} ({role})")
        print(f"Output: {output_path}")
    else:
        task["status"] = "failed"
        if contract_errors:
            task["error"] = "Output contract invalid: " + "; ".join(contract_errors)
        else:
            task["error"] = result.stderr or "Codex execution failed"
        task["finished_at"] = utc_now()
        append_event(
            "task_failed",
            {
                "task_id": task["id"],
                "role": role,
                "pipeline_id": pipeline_id,
                "debate_id": debate_id,
                "workdir": str(workdir),
                "error": task["error"],
                "attempts": attempts,
            },
        )
        print(f"Failed {task['id']} ({role})", file=sys.stderr)
        print(task["error"], file=sys.stderr)

    task["session_id"] = role_state.get("session_id")
    task["updated_at"] = utc_now()
    role_state["state"] = "idle"
    role_state["last_active_at"] = utc_now()

    if pipeline_id:
        pipeline = get_pipeline(state, str(pipeline_id))
        if pipeline and task["status"] == "failed":
            pipeline["last_error"] = task["error"]
        recompute_pipeline_status(state, str(pipeline_id))

    if debate_id:
        debate = get_debate(state, str(debate_id))
        if debate and task["status"] == "failed":
            debate["last_error"] = task["error"]
        recompute_debate_status(state, str(debate_id))

    save_state(state)
    return 0 if result.return_code == 0 else result.return_code


def dispatch(args: argparse.Namespace) -> int:
    state = load_state()
    if state["status"] != "running":
        print("Team is not running. Use start/resume first.", file=sys.stderr)
        return 1

    task: dict[str, Any] | None
    if args.task_id:
        task = get_task(state, args.task_id)
        if not task:
            print(f"Task not found: {args.task_id}", file=sys.stderr)
            return 1
        if task["status"] != "queued":
            print(f"Task {task['id']} is not queued (status={task['status']}).")
            return 1
        if not is_task_ready(state, task):
            print(f"Task {task['id']} is blocked by unfinished dependencies.")
            return 1
    else:
        task = next_queued_task(state)

    if not task:
        blocked = queued_but_blocked(state)
        if blocked:
            print("No ready queued task. Blocked tasks:")
            for item in blocked[:5]:
                deps = ", ".join(task_dependencies(item)) or "-"
                print(f"- {item['id']} [{item['role']}] waiting for {deps}")
            if len(blocked) > 5:
                print(f"... and {len(blocked) - 5} more")
        else:
            print("No queued task found.")
        return 0

    return _dispatch_task_object(state, task)


def run_pipeline_by_id(pipeline_id: str, stop_on_failure: bool) -> int:
    state = load_state()
    if state["status"] != "running":
        print("Team is not running. Use start/resume first.", file=sys.stderr)
        return 1

    pipeline = get_pipeline(state, pipeline_id)
    if not pipeline:
        print(f"Pipeline not found: {pipeline_id}", file=sys.stderr)
        return 1

    append_event("pipeline_run_started", {"pipeline_id": pipeline_id})

    for task_id in pipeline.get("task_ids", []):
        state = load_state()
        task = get_task(state, task_id)
        if not task:
            print(f"Missing task in pipeline: {task_id}", file=sys.stderr)
            if stop_on_failure:
                return 1
            continue

        if task["status"] == "done":
            continue

        if task["status"] == "failed":
            print(f"Task already failed: {task_id}", file=sys.stderr)
            if stop_on_failure:
                append_event(
                    "pipeline_run_stopped",
                    {"pipeline_id": pipeline_id, "reason": f"failed task {task_id}"},
                )
                return 1
            continue

        code = dispatch(argparse.Namespace(task_id=task_id))
        if code != 0 and stop_on_failure:
            append_event(
                "pipeline_run_stopped",
                {"pipeline_id": pipeline_id, "reason": f"dispatch failure on {task_id}"},
            )
            return code

    state = load_state()
    final_status = recompute_pipeline_status(state, pipeline_id)
    save_state(state)
    append_event("pipeline_run_finished", {"pipeline_id": pipeline_id, "status": final_status})
    print(f"Pipeline {pipeline_id} status: {final_status}")
    return 0


def run_pipeline(args: argparse.Namespace) -> int:
    return run_pipeline_by_id(args.pipeline_id, stop_on_failure=not args.continue_on_failure)


def run_debate_by_id(debate_id: str, stop_on_failure: bool) -> int:
    state = load_state()
    if state["status"] != "running":
        print("Team is not running. Use start/resume first.", file=sys.stderr)
        return 1

    debate = get_debate(state, debate_id)
    if not debate:
        print(f"Debate not found: {debate_id}", file=sys.stderr)
        return 1

    append_event("debate_run_started", {"debate_id": debate_id})

    for task_id in debate.get("task_ids", []):
        state = load_state()
        task = get_task(state, task_id)
        if not task:
            print(f"Missing task in debate: {task_id}", file=sys.stderr)
            if stop_on_failure:
                return 1
            continue

        if task["status"] == "done":
            continue

        if task["status"] == "failed":
            print(f"Task already failed: {task_id}", file=sys.stderr)
            if stop_on_failure:
                append_event(
                    "debate_run_stopped",
                    {"debate_id": debate_id, "reason": f"failed task {task_id}"},
                )
                return 1
            continue

        code = dispatch(argparse.Namespace(task_id=task_id))
        if code != 0 and stop_on_failure:
            append_event(
                "debate_run_stopped",
                {"debate_id": debate_id, "reason": f"dispatch failure on {task_id}"},
            )
            return code

    state = load_state()
    final_status = recompute_debate_status(state, debate_id)
    save_state(state)
    append_event("debate_run_finished", {"debate_id": debate_id, "status": final_status})
    print(f"Debate {debate_id} status: {final_status}")
    return 0


def run_debate(args: argparse.Namespace) -> int:
    return run_debate_by_id(args.debate_id, stop_on_failure=not args.continue_on_failure)


def drain_queue(args: argparse.Namespace) -> int:
    state = load_state()
    if state["status"] != "running":
        print("Team is not running. Use start/resume first.", file=sys.stderr)
        return 1

    max_tasks = args.max_tasks if args.max_tasks and args.max_tasks > 0 else 10_000
    executed = 0

    while executed < max_tasks:
        state = load_state()
        task = next_queued_task(state)
        if not task:
            blocked = queued_but_blocked(state)
            if blocked:
                print("Queue has blocked tasks only.")
                for item in blocked[:5]:
                    deps = ", ".join(task_dependencies(item)) or "-"
                    print(f"- {item['id']} [{item['role']}] waiting for {deps}")
                if len(blocked) > 5:
                    print(f"... and {len(blocked) - 5} more")
            else:
                print("Queue drained.")
            break

        code = dispatch(argparse.Namespace(task_id=task["id"]))
        executed += 1
        if code != 0 and not args.continue_on_failure:
            print(f"Drain stopped after failure on {task['id']}", file=sys.stderr)
            return code

    print(f"Drain executed {executed} task(s).")
    return 0


def pipelines_view(state: dict[str, Any]) -> None:
    pipelines = state.get("pipelines", [])
    if not pipelines:
        print("No pipelines found.")
        return

    for pipeline in pipelines:
        task_count = len(pipeline.get("task_ids", []))
        print(f"- {pipeline['id']} [{pipeline.get('status')}] {pipeline.get('title')} ({task_count} tasks)")


def debates_view(state: dict[str, Any]) -> None:
    debates = state.get("debates", [])
    if not debates:
        print("No debates found.")
        return

    for debate in debates:
        task_count = len(debate.get("task_ids", []))
        print(f"- {debate['id']} [{debate.get('status')}] {debate.get('title')} ({task_count} tasks)")


def pipelines_status(_args: argparse.Namespace) -> int:
    state = load_state()
    refresh_all_pipelines(state)
    save_state(state)
    pipelines_view(state)
    return 0


def debates_status(_args: argparse.Namespace) -> int:
    state = load_state()
    refresh_all_debates(state)
    save_state(state)
    debates_view(state)
    return 0


def print_chat_help() -> None:
    print("Commands:")
    print("/help")
    print("/status")
    print("/agents")
    print("/queue")
    print("/pipelines")
    print("/debates")
    print("/task <role> | <title> | <description>")
    print("/run <role> | <title> | <description>")
    print("/pipeline <title> | <brief>")
    print("/run-pipeline <title> | <brief>")
    print("/debate <title> | <topic>")
    print("/run-debate <title> | <topic>")
    print("/dispatch [TASK-ID]")
    print("/drain [max_tasks]")
    print("/stop")
    print("/exit")


def queue_view(state: dict[str, Any]) -> None:
    queued = [task for task in state["tasks"] if task["status"] == "queued"]
    if not queued:
        print("Queue is empty.")
        return

    for task in queued:
        deps = task_dependencies(task)
        dep_text = f" deps={','.join(deps)}" if deps else ""
        print(f"- {task['id']} [{task['role']}] {task['title']}{dep_text}")


def agents_view(state: dict[str, Any]) -> None:
    for role, info in sorted(state["roles"].items()):
        sid = info.get("session_id")
        short = sid[:8] + "..." if sid else "-"
        print(f"- {role}: state={info.get('state')} session={short}")


def print_task_report(task_id: str, max_chars: int = 5000) -> None:
    state = load_state()
    task = get_task(state, task_id)
    if not task:
        print(f"Task output unavailable: {task_id}")
        return

    output_path = task.get("output_path")
    if not output_path:
        print(f"No output path for {task_id}.")
        return

    file_path = ROOT / output_path
    if not file_path.exists():
        print(f"Output file not found: {output_path}")
        return

    content = file_path.read_text(encoding="utf-8").strip()
    contract = extract_output_contract(content)
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n[truncated]"

    print(f"--- {task_id} report ({task.get('role')}) ---")
    print(content)
    if contract:
        status = contract.get("status", "-")
        handoff_to = contract.get("handoff_to", [])
        print("--- parsed contract ---")
        print(f"status={status} handoff_to={handoff_to}")
    print("--- end report ---")


def chat(_args: argparse.Namespace) -> int:
    state = load_state()
    if state["status"] != "running":
        print("Team is not running. Starting automatically.")
        code = start_team(argparse.Namespace(skip_auth_check=False))
        if code != 0:
            return code

    print("Team chat started. /help for commands.")

    while True:
        try:
            raw = input("team> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting chat.")
            return 0

        if not raw:
            continue

        if raw == "/help":
            print_chat_help()
            continue

        if raw == "/exit":
            return 0

        if raw == "/status":
            status_team(argparse.Namespace(json=False))
            continue

        if raw == "/queue":
            queue_view(load_state())
            continue

        if raw == "/agents":
            agents_view(load_state())
            continue

        if raw == "/pipelines":
            pipelines_view(load_state())
            continue

        if raw == "/debates":
            debates_view(load_state())
            continue

        if raw.startswith("/task ") or raw.startswith("/run "):
            run_now = raw.startswith("/run ")
            payload = raw.split(" ", 1)[1]
            parts = [part.strip() for part in payload.split("|", 2)]
            if len(parts) != 3:
                print("Format: /task <role> | <title> | <description>")
                continue

            role, title, description = parts
            state = load_state()
            task = enqueue_task(state, role, title, description)
            save_state(state)
            print(f"Enqueued {task['id']} for {role}")

            if run_now:
                dispatch(argparse.Namespace(task_id=task["id"]))
            continue

        if raw.startswith("/pipeline ") or raw.startswith("/run-pipeline "):
            run_now = raw.startswith("/run-pipeline ")
            payload = raw.split(" ", 1)[1]
            parts = [part.strip() for part in payload.split("|", 1)]
            if len(parts) != 2:
                print("Format: /pipeline <title> | <brief>")
                continue

            title, brief = parts
            state = load_state()
            pipeline = create_pipeline(state, title, brief, read_default_pipeline())
            refresh_all_pipelines(state)
            save_state(state)

            print(f"Created {pipeline['id']} with {len(pipeline['task_ids'])} tasks")
            if run_now:
                run_pipeline_by_id(pipeline["id"], stop_on_failure=True)
            continue

        if raw.startswith("/debate ") or raw.startswith("/run-debate "):
            run_now = raw.startswith("/run-debate ")
            payload = raw.split(" ", 1)[1]
            parts = [part.strip() for part in payload.split("|", 1)]
            if len(parts) != 2:
                print("Format: /debate <title> | <topic>")
                continue

            title, topic = parts
            state = load_state()
            debate = create_debate(
                state,
                title,
                topic,
                read_default_debate_roles(),
                read_default_debate_moderator(),
            )
            refresh_all_debates(state)
            save_state(state)

            print(f"Created {debate['id']} with {len(debate['task_ids'])} tasks")
            if run_now:
                run_debate_by_id(debate["id"], stop_on_failure=True)
                print_task_report(debate["moderator_task_id"])
            continue

        if raw.startswith("/dispatch"):
            parts = raw.split(" ", 1)
            task_id = parts[1].strip() if len(parts) == 2 else None
            dispatch(argparse.Namespace(task_id=task_id or None))
            continue

        if raw.startswith("/drain"):
            parts = raw.split(" ", 1)
            max_tasks = None
            if len(parts) == 2 and parts[1].strip():
                try:
                    max_tasks = int(parts[1].strip())
                except ValueError:
                    print("Format: /drain [max_tasks]")
                    continue
            drain_queue(argparse.Namespace(max_tasks=max_tasks, continue_on_failure=False))
            continue

        if raw == "/stop":
            stop_team(argparse.Namespace())
            continue

        state = load_state()
        task = enqueue_task(
            state,
            "orchestrator",
            "User chat input",
            f"Respond to user input and produce actionable next tasks:\n{raw}",
        )
        save_state(state)
        code = dispatch(argparse.Namespace(task_id=task["id"]))
        if code == 0:
            print_task_report(task["id"])
        else:
            print(f"Failed to process chat message task {task['id']}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex multi-session team orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start the team")
    start.add_argument("--skip-auth-check", action="store_true")
    start.set_defaults(func=start_team)

    stop = sub.add_parser("stop", help="Stop the team")
    stop.set_defaults(func=stop_team)

    resume = sub.add_parser("resume", help="Resume the team")
    resume.add_argument("--skip-auth-check", action="store_true")
    resume.set_defaults(func=resume_team)

    status = sub.add_parser("status", help="Show status")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=status_team)

    task = sub.add_parser("enqueue", help="Enqueue a task")
    task.add_argument("role")
    task.add_argument("title")
    task.add_argument("description")
    task.set_defaults(func=enqueue)

    pipeline = sub.add_parser("pipeline", help="Create a role chain pipeline")
    pipeline.add_argument("title")
    pipeline.add_argument("brief")
    pipeline.add_argument("--roles", help="Comma-separated role list")
    pipeline.set_defaults(func=enqueue_pipeline)

    debate = sub.add_parser("debate", help="Create a multi-agent debate bundle")
    debate.add_argument("title")
    debate.add_argument("topic")
    debate.add_argument("--roles", help="Comma-separated role list")
    debate.add_argument("--moderator", help="Moderator role")
    debate.set_defaults(func=enqueue_debate)

    run = sub.add_parser("dispatch", help="Dispatch one queued task")
    run.add_argument("task_id", nargs="?")
    run.set_defaults(func=dispatch)

    run_pipe = sub.add_parser("run-pipeline", help="Run tasks of one pipeline in order")
    run_pipe.add_argument("pipeline_id")
    run_pipe.add_argument("--continue-on-failure", action="store_true")
    run_pipe.set_defaults(func=run_pipeline)

    run_debate_cmd = sub.add_parser("run-debate", help="Run tasks of one debate in order")
    run_debate_cmd.add_argument("debate_id")
    run_debate_cmd.add_argument("--continue-on-failure", action="store_true")
    run_debate_cmd.set_defaults(func=run_debate)

    drain = sub.add_parser("drain", help="Drain all ready tasks from queue")
    drain.add_argument("--max-tasks", type=int)
    drain.add_argument("--continue-on-failure", action="store_true")
    drain.set_defaults(func=drain_queue)

    pipes = sub.add_parser("pipelines", help="List pipelines")
    pipes.set_defaults(func=pipelines_status)

    debates_cmd = sub.add_parser("debates", help="List debates")
    debates_cmd.set_defaults(func=debates_status)

    chat_cmd = sub.add_parser("chat", help="Interactive terminal chat")
    chat_cmd.set_defaults(func=chat)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
