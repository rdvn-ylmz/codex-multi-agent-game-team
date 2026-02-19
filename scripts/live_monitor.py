#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from team.tools.adapter import load_json_object, load_jobs, read_manifest, resolve_paths


ROOT = Path(__file__).resolve().parents[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _runtime_state_path() -> Path:
    env_path = Path(
        __import__("os").getenv("TEAM_STATE_PATH", str(ROOT / "team" / "state" / "runtime_state.json"))
    ).expanduser()
    return env_path.resolve()


def _events_path() -> Path:
    env_path = Path(
        __import__("os").getenv("TEAM_EVENTS_PATH", str(ROOT / "team" / "state" / "events.jsonl"))
    ).expanduser()
    return env_path.resolve()


def _read_events(limit: int = 60) -> list[dict[str, Any]]:
    path = _events_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except OSError:
        return []
    return rows[-limit:]


def _state_summary() -> dict[str, Any]:
    state = load_json_object(_runtime_state_path())
    tasks = state.get("tasks", [])
    pipes = state.get("pipelines", [])
    debates = state.get("debates", [])
    roles = state.get("roles", {})
    task_counts = Counter(str(task.get("status", "unknown")) for task in tasks)
    pipe_counts = Counter(str(pipe.get("status", "unknown")) for pipe in pipes)
    debate_counts = Counter(str(item.get("status", "unknown")) for item in debates)

    role_rows = []
    if isinstance(roles, dict):
        for role_id, role in sorted(roles.items()):
            if not isinstance(role, dict):
                continue
            role_rows.append(
                {
                    "id": role_id,
                    "state": role.get("state"),
                    "session_id": role.get("session_id"),
                    "backend": role.get("session_backend"),
                    "model": role.get("session_model"),
                    "completed": role.get("tasks_completed"),
                }
            )

    return {
        "status": state.get("status"),
        "profile": (state.get("config") or {}).get("profile"),
        "tasks": dict(task_counts),
        "pipelines": dict(pipe_counts),
        "debates": dict(debate_counts),
        "roles": role_rows,
    }


def build_snapshot() -> dict[str, Any]:
    paths = resolve_paths()
    jobs_state = load_jobs(paths)
    manifest = read_manifest(paths)
    return {
        "generated_at": _now_iso(),
        "project_root": str(paths.project_root),
        "runtime_state_path": str(_runtime_state_path()),
        "events_path": str(_events_path()),
        "state": _state_summary(),
        "tool_jobs": jobs_state,
        "asset_manifest": manifest,
        "recent_events": _read_events(),
    }


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Team Live Monitor</title>
  <style>
    :root {
      --bg: #0f1625;
      --card: #1b2438;
      --text: #edf2ff;
      --muted: #97a8c9;
      --line: #33425f;
      --ok: #57d28c;
      --warn: #f3be55;
      --bad: #ff7a7a;
      --accent: #6ec8ff;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font-family: Segoe UI, sans-serif; }
    .wrap { padding: 16px; display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0,1fr)); }
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 12px; }
    h2 { margin: 0 0 8px; font-size: 1.05rem; color: var(--accent); }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 0.86rem; }
    .muted { color: var(--muted); }
    .wide { grid-column: 1 / -1; }
    @media (max-width: 980px) { .wrap { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="card"><h2>State</h2><pre id="state">loading...</pre></section>
    <section class="card"><h2>Tool Jobs</h2><pre id="jobs">loading...</pre></section>
    <section class="card"><h2>Roles</h2><pre id="roles">loading...</pre></section>
    <section class="card"><h2>Assets</h2><pre id="assets">loading...</pre></section>
    <section class="card wide"><h2>Recent Events</h2><pre id="events">loading...</pre></section>
  </div>
  <script>
    function fmtCounts(obj) {
      const keys = Object.keys(obj || {});
      if (keys.length === 0) return "-";
      return keys.sort().map((k) => `${k}: ${obj[k]}`).join("\\n");
    }
    function short(val, size=12) {
      if (!val) return "-";
      const s = String(val);
      return s.length > size ? s.slice(0, size) + "..." : s;
    }
    async function refresh() {
      const res = await fetch("/api/snapshot", { cache: "no-store" });
      const data = await res.json();
      const st = data.state || {};
      document.getElementById("state").textContent =
        `generated_at: ${data.generated_at}\\n` +
        `project_root: ${data.project_root}\\n` +
        `team_status: ${st.status || "-"}\\n` +
        `profile: ${st.profile || "-"}\\n\\n` +
        `tasks\\n${fmtCounts(st.tasks)}\\n\\n` +
        `pipelines\\n${fmtCounts(st.pipelines)}\\n\\n` +
        `debates\\n${fmtCounts(st.debates)}`;

      const jobs = (data.tool_jobs && data.tool_jobs.jobs) || [];
      const jcounts = { queued: 0, running: 0, done: 0, failed: 0 };
      for (const j of jobs) if (jcounts[j.status] !== undefined) jcounts[j.status] += 1;
      const recentJobs = jobs.slice(-8).map((j) => `${j.id} [${j.status}] ${j.tool} -> ${j.output_path}`).join("\\n");
      document.getElementById("jobs").textContent =
        `queued=${jcounts.queued} running=${jcounts.running} done=${jcounts.done} failed=${jcounts.failed}\\n\\n` +
        (recentJobs || "No tool jobs.");

      const roles = (st.roles || []).map((r) =>
        `${r.id}: ${r.state} backend=${r.backend || "-"} model=${r.model || "-"} session=${short(r.session_id, 10)} completed=${r.completed || 0}`
      ).join("\\n");
      document.getElementById("roles").textContent = roles || "No roles.";

      const assets = ((data.asset_manifest && data.asset_manifest.assets) || []).slice(-10)
        .map((a) => `${a.asset_id} ${a.tool} ${a.output_path} (${a.bytes} bytes)`).join("\\n");
      document.getElementById("assets").textContent = assets || "No assets.";

      const events = (data.recent_events || []).slice(-40)
        .map((e) => `[${e.timestamp}] ${e.event} ${JSON.stringify(e.payload || {})}`).join("\\n");
      document.getElementById("events").textContent = events || "No events.";
    }
    refresh().catch((e) => console.error(e));
    setInterval(() => refresh().catch((e) => console.error(e)), 2000);
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, html: str, status: int = 200) -> None:
        raw = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self._send_html(HTML_PAGE)
            return
        if parsed.path == "/api/snapshot":
            self._send_json(build_snapshot())
            return
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Live monitor for multi-agent team + tool jobs")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Live monitor: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
