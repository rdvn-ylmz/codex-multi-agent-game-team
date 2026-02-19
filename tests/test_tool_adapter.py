from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from team.tools import adapter


class ToolAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = {key: os.environ.get(key) for key in self._tracked_env_keys()}
        self._tmp = tempfile.TemporaryDirectory(prefix="tool-adapter-")
        base = Path(self._tmp.name)
        self.project_root = base / "project"
        self.state_dir = base / "state"
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        os.environ["TEAM_PROJECT_ROOT"] = str(self.project_root)
        os.environ["TEAM_STATE_PATH"] = str(self.state_dir / "runtime_state.json")
        os.environ["TEAM_EVENTS_PATH"] = str(self.state_dir / "events.jsonl")
        os.environ.pop("TOOL_JOBS_PATH", None)
        os.environ.pop("ASSET_MANIFEST_PATH", None)
        os.environ.pop("TEAM_TOOLS_CONFIG", None)

    def tearDown(self) -> None:
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    @staticmethod
    def _tracked_env_keys() -> list[str]:
        return [
            "TEAM_PROJECT_ROOT",
            "TEAM_STATE_PATH",
            "TEAM_EVENTS_PATH",
            "TOOL_JOBS_PATH",
            "ASSET_MANIFEST_PATH",
            "TEAM_TOOLS_CONFIG",
        ]

    def test_submit_unknown_tool_raises(self) -> None:
        with self.assertRaises(ValueError):
            adapter.submit_job(tool="missing_tool", prompt="x")

    def test_music_job_creates_wav_and_manifest_entry(self) -> None:
        job = adapter.submit_job(
            tool="music_tone",
            prompt="space combat loop",
            params={"duration_sec": "1.0", "frequency_hz": "330"},
            task_id="TASK-1111",
            role="narrative",
        )
        self.assertEqual(job["status"], "queued")

        processed = adapter.process_one_job()
        self.assertIsNotNone(processed)
        self.assertEqual(processed["status"], "done")

        paths = adapter.resolve_paths()
        output_path = paths.project_root / processed["output_path"]
        self.assertTrue(output_path.exists())
        self.assertTrue(output_path.suffix.lower() == ".wav")

        manifest = adapter.read_manifest(paths)
        asset_ids = [item.get("asset_id") for item in manifest.get("assets", [])]
        self.assertIn(processed["id"], asset_ids)

    def test_image_job_creates_svg(self) -> None:
        adapter.submit_job(
            tool="image_svg",
            prompt="Sky city concept frame",
            params={"width": "640", "height": "360"},
        )
        processed = adapter.process_one_job()
        self.assertIsNotNone(processed)
        self.assertEqual(processed["status"], "done")

        paths = adapter.resolve_paths()
        output_path = paths.project_root / processed["output_path"]
        self.assertTrue(output_path.exists())
        self.assertTrue(output_path.suffix.lower() == ".svg")

    def test_cancel_job_marks_failed(self) -> None:
        job = adapter.submit_job(tool="music_tone", prompt="ambient loop")
        cancelled = adapter.cancel_job(job["id"])
        self.assertTrue(cancelled)

        jobs_state = adapter.load_jobs(adapter.resolve_paths())
        statuses = {entry["id"]: entry["status"] for entry in jobs_state.get("jobs", [])}
        self.assertEqual(statuses.get(job["id"]), "failed")


if __name__ == "__main__":
    unittest.main()

