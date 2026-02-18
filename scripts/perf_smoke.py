#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import os
import sys
import tempfile
import time
from pathlib import Path


def run_benchmark(iterations: int, stages: int, threshold_ms: float) -> int:
    root_dir = Path(__file__).resolve().parents[1]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    with tempfile.TemporaryDirectory(prefix="codex-team-perf-") as tmpdir:
        tmp_path = Path(tmpdir)
        os.environ["TEAM_STATE_PATH"] = str(tmp_path / "runtime_state.json")
        os.environ["TEAM_EVENTS_PATH"] = str(tmp_path / "events.jsonl")

        orchestrator = importlib.import_module("team.orchestrator")
        orchestrator.append_event = lambda *args, **kwargs: None

        roles = orchestrator.DEFAULT_PIPELINE_ROLES[:stages]
        state = orchestrator.new_state()

        start = time.perf_counter()
        for index in range(iterations):
            pipeline = orchestrator.create_pipeline(
                state,
                f"Perf Pipeline {index}",
                "Synthetic benchmark payload",
                roles,
            )
            orchestrator.recompute_pipeline_status(state, pipeline["id"])
            task = orchestrator.next_queued_task(state)
            if not task:
                raise RuntimeError("benchmark expected a queued task but none was found")
            task["status"] = "done"

        elapsed_ms = (time.perf_counter() - start) * 1000.0

    print(
        f"perf-smoke elapsed={elapsed_ms:.2f}ms "
        f"iterations={iterations} stages={stages} threshold={threshold_ms:.2f}ms"
    )
    if elapsed_ms > threshold_ms:
        print("Performance budget exceeded", flush=True)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic performance smoke for orchestrator")
    parser.add_argument("--iterations", type=int, default=120)
    parser.add_argument("--stages", type=int, default=6)
    parser.add_argument("--threshold-ms", type=float, default=2500.0)
    args = parser.parse_args()

    return run_benchmark(args.iterations, args.stages, args.threshold_ms)


if __name__ == "__main__":
    raise SystemExit(main())
