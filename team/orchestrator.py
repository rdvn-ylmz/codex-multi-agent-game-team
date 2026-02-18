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
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASK_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


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
        "version": 1,
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
    }


def load_state() -> dict[str, Any]:
    ensure_dirs()
    if not STATE_FILE.exists():
        state = new_state()
        save_state(state)
        return state

    with STATE_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def ensure_role(state: dict[str, Any], role: str) -> None:
    if role not in state["roles"]:
        state["roles"][role] = {
            "session_id": None,
            "state": "idle",
            "last_active_at": None,
            "tasks_completed": 0,
        }


def enqueue_task(state: dict[str, Any], role: str, title: str, description: str) -> dict[str, Any]:
    ensure_role(state, role)
    now = utc_now()
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
    }
    state["tasks"].append(task)
    append_event("task_enqueued", {"task_id": task["id"], "role": role, "title": title})
    return task


def get_task(state: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for task in state["tasks"]:
        if task["id"] == task_id:
            return task
    return None


def next_queued_task(state: dict[str, Any]) -> dict[str, Any] | None:
    for task in state["tasks"]:
        if task["status"] == "queued":
            return task
    return None


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


@dataclass
class CodexResult:
    return_code: int
    session_id: str | None
    message: str
    stderr: str


def run_codex_task(role: str, task: dict[str, Any], session_id: str | None) -> CodexResult:
    role_prompt = load_role_prompt(role)
    prompt = (
        f"Role: {role}\n"
        f"Task ID: {task['id']}\n"
        f"Title: {task['title']}\n"
        f"Description:\n{task['description']}\n\n"
        "Work in the current repository.\n"
        "Return a concise execution report with:\n"
        "1) Summary\n2) Files changed\n3) Risks and next handoff\n"
    )
    if role_prompt:
        prompt = role_prompt + "\n\n" + prompt

    cmd = codex_command(prompt, session_id)
    process = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)

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

    save_state(state)
    append_event("team_started", {"profile": state["config"].get("profile")})

    print("Team status: running")
    print(f"Profile: {state['config'].get('profile')}")
    print(f"State file: {STATE_FILE}")
    return 0


def stop_team(_args: argparse.Namespace) -> int:
    state = load_state()
    state["status"] = "stopped"
    state["stopped_at"] = utc_now()
    for role_data in state["roles"].values():
        role_data["state"] = "idle"
    save_state(state)
    append_event("team_stopped", {"stopped_at": state["stopped_at"]})
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
    save_state(state)
    append_event("team_resumed", {})
    print("Team status: running (resumed)")
    return 0


def status_team(args: argparse.Namespace) -> int:
    state = load_state()
    queued = sum(1 for task in state["tasks"] if task["status"] == "queued")
    running = sum(1 for task in state["tasks"] if task["status"] == "running")
    failed = sum(1 for task in state["tasks"] if task["status"] == "failed")
    done = sum(1 for task in state["tasks"] if task["status"] == "done")

    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=True))
        return 0

    print(f"Team status: {state['status']}")
    print(f"Profile: {state['config'].get('profile')}")
    print(f"Started at: {state.get('started_at')}")
    print(f"Stopped at: {state.get('stopped_at')}")
    print(f"Tasks: queued={queued} running={running} done={done} failed={failed}")
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


def dispatch(args: argparse.Namespace) -> int:
    state = load_state()
    if state["status"] != "running":
        print("Team is not running. Use start/resume first.", file=sys.stderr)
        return 1

    task = get_task(state, args.task_id) if args.task_id else next_queued_task(state)
    if not task:
        print("No queued task found.")
        return 0

    role = task["role"]
    ensure_role(state, role)

    task["status"] = "running"
    task["started_at"] = utc_now()
    task["updated_at"] = utc_now()
    role_state = state["roles"][role]
    role_state["state"] = "busy"
    save_state(state)
    append_event("task_started", {"task_id": task["id"], "role": role})

    result = run_codex_task(role, task, role_state.get("session_id"))

    if result.session_id:
        role_state["session_id"] = result.session_id

    if result.return_code == 0:
        task["status"] = "done"
        task["error"] = None
        content = result.message or "No message returned by Codex."
        output_path = write_task_output(task["id"], content)
        task["output_path"] = output_path
        task["finished_at"] = utc_now()
        role_state["tasks_completed"] = int(role_state.get("tasks_completed", 0)) + 1
        append_event(
            "task_completed",
            {"task_id": task["id"], "role": role, "output_path": output_path},
        )
        print(f"Completed {task['id']} ({role})")
        print(f"Output: {output_path}")
    else:
        task["status"] = "failed"
        task["error"] = result.stderr or "Codex execution failed"
        task["finished_at"] = utc_now()
        append_event(
            "task_failed",
            {"task_id": task["id"], "role": role, "error": task["error"]},
        )
        print(f"Failed {task['id']} ({role})", file=sys.stderr)
        print(task["error"], file=sys.stderr)

    task["session_id"] = role_state.get("session_id")
    task["updated_at"] = utc_now()
    role_state["state"] = "idle"
    role_state["last_active_at"] = utc_now()
    save_state(state)

    return 0 if result.return_code == 0 else result.return_code


def print_chat_help() -> None:
    print("Commands:")
    print("/help")
    print("/status")
    print("/queue")
    print("/agents")
    print("/task <role> | <title> | <description>")
    print("/run <role> | <title> | <description>")
    print("/dispatch [TASK-ID]")
    print("/stop")
    print("/exit")


def queue_view(state: dict[str, Any]) -> None:
    queued = [task for task in state["tasks"] if task["status"] == "queued"]
    if not queued:
        print("Queue is empty.")
        return
    for task in queued:
        print(f"- {task['id']} [{task['role']}] {task['title']}")


def agents_view(state: dict[str, Any]) -> None:
    for role, info in sorted(state["roles"].items()):
        sid = info.get("session_id")
        short = sid[:8] + "..." if sid else "-"
        print(f"- {role}: state={info.get('state')} session={short}")


def chat(_args: argparse.Namespace) -> int:
    state = load_state()
    if state["status"] != "running":
        print("Team is not running. Starting automatically.")
        start_args = argparse.Namespace(skip_auth_check=False)
        code = start_team(start_args)
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

        if raw.startswith("/dispatch"):
            parts = raw.split(" ", 1)
            task_id = parts[1].strip() if len(parts) == 2 else None
            dispatch(argparse.Namespace(task_id=task_id or None))
            continue

        if raw == "/stop":
            stop_team(argparse.Namespace())
            continue

        # Default message route: create PM task.
        state = load_state()
        task = enqueue_task(
            state,
            "orchestrator",
            "User chat input",
            f"Respond to user input and produce actionable next tasks:\n{raw}",
        )
        save_state(state)
        print(f"Message converted to {task['id']}. Use /dispatch {task['id']} to run.")


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

    run = sub.add_parser("dispatch", help="Dispatch one queued task")
    run.add_argument("task_id", nargs="?")
    run.set_defaults(func=dispatch)

    chat_cmd = sub.add_parser("chat", help="Interactive terminal chat")
    chat_cmd.set_defaults(func=chat)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
