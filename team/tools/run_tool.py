#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from team.tools.adapter import (
    cancel_job,
    jobs_summary,
    load_jobs,
    parse_kv_params,
    process_one_job,
    read_config,
    read_manifest,
    resolve_paths,
    run_worker,
    submit_job,
)


def _print_job(job: dict[str, object]) -> None:
    print(
        f"{job.get('id')} [{job.get('status')}] tool={job.get('tool')} "
        f"output={job.get('output_path')} attempts={job.get('attempts')}"
    )
    error = job.get("error")
    if error:
        print(f"  error: {error}")


def cmd_list_tools(_args: argparse.Namespace) -> int:
    paths = resolve_paths()
    cfg = read_config(paths)
    tools = cfg.get("tools", {})
    print("Available tools:")
    for tool_id, tool_cfg in tools.items():
        if not isinstance(tool_cfg, dict):
            continue
        kind = tool_cfg.get("kind", "-")
        out_dir = tool_cfg.get("default_output_dir", "-")
        model = tool_cfg.get("model", "-")
        print(f"- {tool_id}: kind={kind} output_dir={out_dir} model={model}")
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    params = parse_kv_params(args.param or [])
    try:
        job = submit_job(
            tool=args.tool,
            prompt=args.prompt,
            output_path=args.output or "",
            params=params,
            task_id=args.task_id or "",
            role=args.role or "",
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"Submitted {job['id']} tool={job['tool']} output={job['output_path']}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    paths = resolve_paths()
    jobs_state = load_jobs(paths)
    summary = jobs_summary(jobs_state)
    manifest = read_manifest(paths)
    jobs = jobs_state.get("jobs", [])
    recent = jobs[-args.limit :] if args.limit > 0 else jobs

    payload = {
        "jobs_file": str(paths.jobs_file),
        "manifest_file": str(paths.manifest_file),
        "project_root": str(paths.project_root),
        "summary": summary,
        "jobs": recent,
        "assets_count": len(manifest.get("assets", [])),
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0

    print(f"Project root: {paths.project_root}")
    print(f"Tool jobs: queued={summary['queued']} running={summary['running']} done={summary['done']} failed={summary['failed']}")
    print(f"Asset manifest entries: {payload['assets_count']}")
    if recent:
        print("Recent jobs:")
        for job in recent:
            _print_job(job)
    else:
        print("No jobs.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    paths = resolve_paths()
    poll_interval = args.poll_interval
    if poll_interval is None:
        cfg = read_config(paths)
        poll_interval = float(cfg.get("worker", {}).get("poll_interval_sec", 2))

    executed = run_worker(
        loop=args.loop,
        max_jobs=args.max_jobs,
        poll_interval_sec=poll_interval,
        paths=paths,
    )
    print(f"Tool worker executed {executed} job(s).")
    return 0


def cmd_run_one(_args: argparse.Namespace) -> int:
    job = process_one_job(paths=resolve_paths())
    if not job:
        print("No queued tool job.")
        return 0
    _print_job(job)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    jobs = load_jobs(resolve_paths()).get("jobs", [])
    for job in jobs:
        if job.get("id") == args.job_id:
            print(json.dumps(job, indent=2, ensure_ascii=True))
            return 0
    print(f"Job not found: {args.job_id}", file=sys.stderr)
    return 1


def cmd_cancel(args: argparse.Namespace) -> int:
    ok = cancel_job(args.job_id, paths=resolve_paths())
    if ok:
        print(f"Cancelled {args.job_id}")
        return 0
    print(f"Unable to cancel {args.job_id} (not found or not queued)", file=sys.stderr)
    return 1


def cmd_manifest(args: argparse.Namespace) -> int:
    manifest = read_manifest(resolve_paths())
    assets = manifest.get("assets", [])
    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=True))
        return 0

    print(f"Asset entries: {len(assets)}")
    for item in assets[-args.limit :]:
        print(
            f"- {item.get('asset_id')} tool={item.get('tool')} "
            f"path={item.get('output_path')} sha256={str(item.get('sha256', ''))[:10]}..."
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tool adapter queue for generated assets")
    sub = parser.add_subparsers(dest="command", required=True)

    list_tools = sub.add_parser("list-tools", help="List configured tools")
    list_tools.set_defaults(func=cmd_list_tools)

    submit = sub.add_parser("submit", help="Submit a tool job")
    submit.add_argument("--tool", required=True)
    submit.add_argument("--prompt", required=True)
    submit.add_argument("--output", help="Output path relative to TEAM_PROJECT_ROOT")
    submit.add_argument("--task-id", help="Source task id")
    submit.add_argument("--role", help="Source role")
    submit.add_argument(
        "--param",
        action="append",
        help="Parameter in key=value format (repeatable)",
    )
    submit.set_defaults(func=cmd_submit)

    run = sub.add_parser("run", help="Run queued jobs")
    run.add_argument("--loop", action="store_true", help="Keep worker running")
    run.add_argument("--max-jobs", type=int, default=1, help="Max jobs to execute (0 means unlimited)")
    run.add_argument("--poll-interval", type=float, help="Polling seconds for --loop")
    run.set_defaults(func=cmd_run)

    run_one = sub.add_parser("run-one", help="Run one queued job")
    run_one.set_defaults(func=cmd_run_one)

    status = sub.add_parser("status", help="Show queue status")
    status.add_argument("--limit", type=int, default=10, help="Recent jobs count")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    show = sub.add_parser("show", help="Show one job JSON")
    show.add_argument("job_id")
    show.set_defaults(func=cmd_show)

    cancel = sub.add_parser("cancel", help="Cancel one queued job")
    cancel.add_argument("job_id")
    cancel.set_defaults(func=cmd_cancel)

    manifest = sub.add_parser("manifest", help="Show asset manifest")
    manifest.add_argument("--limit", type=int, default=20)
    manifest.add_argument("--json", action="store_true")
    manifest.set_defaults(func=cmd_manifest)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
