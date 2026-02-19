from __future__ import annotations

import hashlib
import html
import json
import math
import os
import struct
import subprocess
import time
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "team" / "config" / "tools.json"

DEFAULT_CONFIG = {
    "version": 1,
    "worker": {
        "poll_interval_sec": 2,
        "max_attempts": 2,
        "timeout_sec": 180,
    },
    "tools": {
        "music_tone": {
            "kind": "builtin_music_tone",
            "default_output_dir": "assets/audio",
            "default_ext": ".wav",
            "license": "generated-by-tool",
            "model": "builtin/music_tone/v1",
        },
        "image_svg": {
            "kind": "builtin_image_svg",
            "default_output_dir": "assets/images",
            "default_ext": ".svg",
            "license": "generated-by-tool",
            "model": "builtin/image_svg/v1",
        },
    },
}


@dataclass
class ToolPaths:
    project_root: Path
    state_dir: Path
    jobs_file: Path
    events_file: Path
    manifest_file: Path
    config_file: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_paths() -> ToolPaths:
    project_root_env = os.getenv("TEAM_PROJECT_ROOT", "").strip()
    project_root = (
        Path(project_root_env).expanduser().resolve()
        if project_root_env
        else ROOT
    )

    team_state_path_env = os.getenv("TEAM_STATE_PATH", "").strip()
    if team_state_path_env:
        state_dir = Path(team_state_path_env).expanduser().resolve().parent
    else:
        state_dir = ROOT / "team" / "state"

    jobs_file = Path(
        os.getenv("TOOL_JOBS_PATH", str(state_dir / "tool_jobs.json"))
    ).expanduser().resolve()
    events_file = Path(
        os.getenv("TEAM_EVENTS_PATH", str(state_dir / "events.jsonl"))
    ).expanduser().resolve()
    manifest_file = Path(
        os.getenv("ASSET_MANIFEST_PATH", str(project_root / "assets" / "manifest.json"))
    ).expanduser().resolve()
    config_file = Path(
        os.getenv("TEAM_TOOLS_CONFIG", str(CONFIG_FILE))
    ).expanduser().resolve()

    return ToolPaths(
        project_root=project_root,
        state_dir=state_dir,
        jobs_file=jobs_file,
        events_file=events_file,
        manifest_file=manifest_file,
        config_file=config_file,
    )


def ensure_dirs(paths: ToolPaths) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.jobs_file.parent.mkdir(parents=True, exist_ok=True)
    paths.events_file.parent.mkdir(parents=True, exist_ok=True)
    paths.manifest_file.parent.mkdir(parents=True, exist_ok=True)
    paths.project_root.mkdir(parents=True, exist_ok=True)


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if isinstance(raw, dict):
        return raw
    return {}


def read_config(paths: ToolPaths) -> dict[str, Any]:
    data = load_json_object(paths.config_file)
    if not data:
        data = DEFAULT_CONFIG.copy()

    tools = data.get("tools")
    if not isinstance(tools, dict) or not tools:
        data["tools"] = DEFAULT_CONFIG["tools"].copy()

    worker = data.get("worker")
    if not isinstance(worker, dict):
        worker = {}
    default_worker = DEFAULT_CONFIG["worker"]
    data["worker"] = {
        "poll_interval_sec": int(worker.get("poll_interval_sec", default_worker["poll_interval_sec"])),
        "max_attempts": int(worker.get("max_attempts", default_worker["max_attempts"])),
        "timeout_sec": int(worker.get("timeout_sec", default_worker["timeout_sec"])),
    }
    return data


def append_event(paths: ToolPaths, event_type: str, payload: dict[str, Any]) -> None:
    ensure_dirs(paths)
    row = {
        "timestamp": utc_now(),
        "event": event_type,
        "payload": payload,
    }
    with paths.events_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def new_jobs_state() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": utc_now(),
        "jobs": [],
    }


def load_jobs(paths: ToolPaths) -> dict[str, Any]:
    ensure_dirs(paths)
    data = load_json_object(paths.jobs_file)
    if not data:
        data = new_jobs_state()

    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        jobs = []
    data["jobs"] = jobs
    if "version" not in data:
        data["version"] = 1
    if "updated_at" not in data:
        data["updated_at"] = utc_now()
    return data


def save_jobs(paths: ToolPaths, jobs_state: dict[str, Any]) -> None:
    ensure_dirs(paths)
    jobs_state["updated_at"] = utc_now()
    paths.jobs_file.write_text(
        json.dumps(jobs_state, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def next_job_id(jobs_state: dict[str, Any]) -> str:
    jobs = jobs_state.get("jobs", [])
    if not jobs:
        return "TOOL-0001"
    last_num = max(int(str(job.get("id", "TOOL-0000")).split("-")[-1]) for job in jobs)
    return f"TOOL-{last_num + 1:04d}"


def _safe_output_path(paths: ToolPaths, rel_path: str) -> Path:
    candidate = (paths.project_root / rel_path).resolve()
    project_root_str = str(paths.project_root.resolve())
    if not str(candidate).startswith(project_root_str + os.sep) and str(candidate) != project_root_str:
        raise ValueError(f"Output path escapes project root: {rel_path}")
    return candidate


def default_output_path(tool_id: str, tool_cfg: dict[str, Any], job_id: str) -> str:
    output_dir = str(tool_cfg.get("default_output_dir", "assets")).strip() or "assets"
    ext = str(tool_cfg.get("default_ext", "")).strip()
    if ext and not ext.startswith("."):
        ext = "." + ext
    return f"{output_dir}/{tool_id}_{job_id.lower()}{ext}"


def submit_job(
    tool: str,
    prompt: str,
    output_path: str = "",
    params: dict[str, Any] | None = None,
    task_id: str = "",
    role: str = "",
    metadata: dict[str, Any] | None = None,
    *,
    paths: ToolPaths | None = None,
) -> dict[str, Any]:
    paths = paths or resolve_paths()
    cfg = read_config(paths)
    tools = cfg.get("tools", {})
    tool_cfg = tools.get(tool)
    if not isinstance(tool_cfg, dict):
        raise ValueError(f"Unknown tool: {tool}")

    jobs_state = load_jobs(paths)
    job_id = next_job_id(jobs_state)
    rel_output = output_path.strip() or default_output_path(tool, tool_cfg, job_id)
    _safe_output_path(paths, rel_output)

    job = {
        "id": job_id,
        "tool": tool,
        "prompt": prompt.strip(),
        "params": params or {},
        "output_path": rel_output,
        "status": "queued",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "attempts": 0,
        "error": None,
        "task_id": task_id.strip() or None,
        "role": role.strip() or None,
        "metadata": metadata or {},
    }
    jobs_state["jobs"].append(job)
    save_jobs(paths, jobs_state)
    append_event(
        paths,
        "tool_job_submitted",
        {
            "job_id": job_id,
            "tool": tool,
            "task_id": job.get("task_id"),
            "role": job.get("role"),
            "output_path": rel_output,
        },
    )
    return job


def read_manifest(paths: ToolPaths) -> dict[str, Any]:
    data = load_json_object(paths.manifest_file)
    if not data:
        data = {"version": 1, "assets": []}
    assets = data.get("assets")
    if not isinstance(assets, list):
        assets = []
    data["assets"] = assets
    if "version" not in data:
        data["version"] = 1
    return data


def write_manifest(paths: ToolPaths, data: dict[str, Any]) -> None:
    ensure_dirs(paths)
    paths.manifest_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def infer_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".ogg":
        return "audio/ogg"
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".png":
        return "image/png"
    if suffix == ".jpg" or suffix == ".jpeg":
        return "image/jpeg"
    return "application/octet-stream"


def append_manifest_asset(
    paths: ToolPaths,
    job: dict[str, Any],
    tool_cfg: dict[str, Any],
    abs_output_path: Path,
) -> None:
    manifest = read_manifest(paths)
    assets = manifest["assets"]

    entry = {
        "asset_id": job["id"],
        "tool": job["tool"],
        "model": tool_cfg.get("model", ""),
        "license": tool_cfg.get("license", "unknown"),
        "prompt": job.get("prompt", ""),
        "output_path": job.get("output_path", ""),
        "mime_type": infer_mime(abs_output_path),
        "sha256": file_sha256(abs_output_path),
        "bytes": abs_output_path.stat().st_size,
        "created_at": utc_now(),
        "task_id": job.get("task_id"),
        "role": job.get("role"),
    }

    filtered = [item for item in assets if item.get("asset_id") != job["id"]]
    filtered.append(entry)
    manifest["assets"] = filtered
    write_manifest(paths, manifest)


def _param_float(params: dict[str, Any], key: str, default: float) -> float:
    raw = params.get(key, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _param_int(params: dict[str, Any], key: str, default: int) -> int:
    raw = params.get(key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def render_builtin_music_tone(output_path: Path, prompt: str, params: dict[str, Any]) -> None:
    sample_rate = max(8000, min(_param_int(params, "sample_rate", 22050), 48000))
    duration = max(0.5, min(_param_float(params, "duration_sec", 8.0), 60.0))
    freq = max(80.0, min(_param_float(params, "frequency_hz", 220.0), 1200.0))
    volume = max(0.05, min(_param_float(params, "volume", 0.35), 0.95))
    attack = 0.03
    release = 0.08
    total_frames = int(sample_rate * duration)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)

        for n in range(total_frames):
            t = n / sample_rate
            env = 1.0
            if t < attack:
                env = t / attack
            if t > duration - release:
                env = max(0.0, (duration - t) / release)
            tone = math.sin(2.0 * math.pi * freq * t)
            overtone = 0.45 * math.sin(2.0 * math.pi * (freq * 2.0) * t)
            sample = (tone + overtone) * 0.5 * env * volume
            packed = struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 32767))
            handle.writeframesraw(packed)

    note_file = output_path.with_suffix(output_path.suffix + ".txt")
    note_file.write_text(
        f"Prompt: {prompt}\n"
        f"duration_sec={duration}\n"
        f"frequency_hz={freq}\n"
        f"sample_rate={sample_rate}\n",
        encoding="utf-8",
    )


def render_builtin_image_svg(output_path: Path, prompt: str, params: dict[str, Any]) -> None:
    width = max(320, min(_param_int(params, "width", 1280), 3840))
    height = max(180, min(_param_int(params, "height", 720), 2160))
    palette = str(params.get("palette", "aurora")).strip().lower()
    escaped = html.escape(prompt.strip() or "Generated concept frame")

    if palette == "desert":
        c1, c2, c3 = "#2a120a", "#d2693c", "#f5d58b"
    elif palette == "ice":
        c1, c2, c3 = "#09152a", "#3f8ec8", "#e3f7ff"
    else:
        c1, c2, c3 = "#0b1020", "#2a6b7a", "#a7f0ff"

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{c1}" />
      <stop offset="50%" stop-color="{c2}" />
      <stop offset="100%" stop-color="{c3}" />
    </linearGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="22"/></filter>
  </defs>
  <rect width="{width}" height="{height}" fill="url(#bg)" />
  <circle cx="{int(width * 0.25)}" cy="{int(height * 0.3)}" r="{int(height * 0.16)}" fill="white" opacity="0.15" filter="url(#blur)" />
  <circle cx="{int(width * 0.7)}" cy="{int(height * 0.6)}" r="{int(height * 0.22)}" fill="white" opacity="0.12" filter="url(#blur)" />
  <rect x="36" y="{height - 140}" width="{width - 72}" height="92" rx="14" fill="rgba(0,0,0,0.35)" />
  <text x="56" y="{height - 92}" font-size="30" fill="white" font-family="Segoe UI, sans-serif">{escaped}</text>
</svg>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")


def run_shell_tool(
    command: str,
    prompt: str,
    output_path: Path,
    params: dict[str, Any],
    timeout_sec: int,
) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["TOOL_PROMPT"] = prompt
    env["TOOL_OUTPUT_PATH"] = str(output_path)
    env["TOOL_PARAMS_JSON"] = json.dumps(params, ensure_ascii=True)
    process = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        env=env,
    )
    return process.returncode, process.stdout.strip(), process.stderr.strip()


def execute_job(paths: ToolPaths, job: dict[str, Any], cfg: dict[str, Any]) -> tuple[bool, str]:
    tools = cfg.get("tools", {})
    tool_cfg = tools.get(job["tool"])
    if not isinstance(tool_cfg, dict):
        return (False, f"Unknown tool: {job['tool']}")

    output_rel = str(job.get("output_path", "")).strip()
    if not output_rel:
        output_rel = default_output_path(job["tool"], tool_cfg, job["id"])
        job["output_path"] = output_rel
    output_path = _safe_output_path(paths, output_rel)
    params = job.get("params", {})
    if not isinstance(params, dict):
        params = {}
    prompt = str(job.get("prompt", "")).strip()
    kind = str(tool_cfg.get("kind", "")).strip()

    if kind == "builtin_music_tone":
        render_builtin_music_tone(output_path, prompt, params)
        return (True, "ok")
    if kind == "builtin_image_svg":
        render_builtin_image_svg(output_path, prompt, params)
        return (True, "ok")
    if kind == "shell_command":
        command = str(tool_cfg.get("command", "")).strip()
        if not command:
            return (False, "shell_command tool is missing command")
        timeout_sec = int(cfg.get("worker", {}).get("timeout_sec", 180))
        code, _stdout, stderr = run_shell_tool(command, prompt, output_path, params, timeout_sec)
        if code != 0:
            return (False, stderr or f"shell command failed ({code})")
        if not output_path.exists():
            return (False, f"shell command completed but output missing: {output_rel}")
        return (True, "ok")

    return (False, f"Unsupported tool kind: {kind}")


def next_ready_job(jobs_state: dict[str, Any]) -> dict[str, Any] | None:
    for job in jobs_state.get("jobs", []):
        if job.get("status") == "queued":
            return job
    return None


def process_one_job(*, paths: ToolPaths | None = None) -> dict[str, Any] | None:
    paths = paths or resolve_paths()
    cfg = read_config(paths)
    worker_cfg = cfg.get("worker", {})
    max_attempts = max(int(worker_cfg.get("max_attempts", 2)), 1)

    jobs_state = load_jobs(paths)
    job = next_ready_job(jobs_state)
    if not job:
        return None

    job["status"] = "running"
    job["started_at"] = utc_now()
    job["updated_at"] = utc_now()
    job["attempts"] = int(job.get("attempts", 0)) + 1
    job["error"] = None
    save_jobs(paths, jobs_state)
    append_event(
        paths,
        "tool_job_started",
        {"job_id": job["id"], "tool": job["tool"], "output_path": job.get("output_path")},
    )

    ok, message = execute_job(paths, job, cfg)
    output_abs = _safe_output_path(paths, str(job.get("output_path", "")).strip())
    if ok and output_abs.exists():
        tool_cfg = cfg.get("tools", {}).get(job["tool"], {})
        append_manifest_asset(paths, job, tool_cfg, output_abs)
        job["status"] = "done"
        job["finished_at"] = utc_now()
        job["updated_at"] = utc_now()
        job["error"] = None
        save_jobs(paths, jobs_state)
        append_event(
            paths,
            "tool_job_completed",
            {
                "job_id": job["id"],
                "tool": job["tool"],
                "output_path": job.get("output_path"),
            },
        )
        return job

    if int(job.get("attempts", 0)) < max_attempts:
        job["status"] = "queued"
        job["updated_at"] = utc_now()
        job["error"] = f"Retrying: {message}"
        save_jobs(paths, jobs_state)
        append_event(
            paths,
            "tool_job_retry",
            {
                "job_id": job["id"],
                "tool": job["tool"],
                "attempts": job.get("attempts"),
                "error": message,
            },
        )
        return job

    job["status"] = "failed"
    job["finished_at"] = utc_now()
    job["updated_at"] = utc_now()
    job["error"] = message
    save_jobs(paths, jobs_state)
    append_event(
        paths,
        "tool_job_failed",
        {"job_id": job["id"], "tool": job["tool"], "error": message},
    )
    return job


def run_worker(*, loop: bool, max_jobs: int, poll_interval_sec: float, paths: ToolPaths | None = None) -> int:
    paths = paths or resolve_paths()
    executed = 0
    while True:
        if max_jobs > 0 and executed >= max_jobs:
            break
        job = process_one_job(paths=paths)
        if job:
            executed += 1
            continue
        if not loop:
            break
        time.sleep(max(0.2, poll_interval_sec))
    return executed


def cancel_job(job_id: str, *, paths: ToolPaths | None = None) -> bool:
    paths = paths or resolve_paths()
    jobs_state = load_jobs(paths)
    for job in jobs_state.get("jobs", []):
        if job.get("id") != job_id:
            continue
        if job.get("status") != "queued":
            return False
        job["status"] = "failed"
        job["error"] = "Cancelled by user"
        job["finished_at"] = utc_now()
        job["updated_at"] = utc_now()
        save_jobs(paths, jobs_state)
        append_event(paths, "tool_job_cancelled", {"job_id": job_id})
        return True
    return False


def jobs_summary(jobs_state: dict[str, Any]) -> dict[str, int]:
    summary = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    for job in jobs_state.get("jobs", []):
        status = str(job.get("status", "")).strip()
        if status in summary:
            summary[status] += 1
    return summary


def parse_kv_params(raw_params: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for entry in raw_params:
        if "=" not in entry:
            parsed[entry] = True
            continue
        key, value = entry.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed

