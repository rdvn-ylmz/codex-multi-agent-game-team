from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import team.orchestrator as orchestrator


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_append_event = orchestrator.append_event
        self._original_workspace_config_file = orchestrator.WORKSPACE_CONFIG_FILE
        orchestrator.append_event = lambda *args, **kwargs: None

    def tearDown(self) -> None:
        orchestrator.append_event = self._original_append_event
        orchestrator.WORKSPACE_CONFIG_FILE = self._original_workspace_config_file

    def test_parse_yaml_id_list_reads_values(self) -> None:
        tmp_dir = Path(self._testMethodName)
        tmp_dir.mkdir(exist_ok=True)
        try:
            data = """
workflow:
  default_pipeline:
    - concept
    - game_design
    - coder
  other_key:
    - ignore_me
"""
            file_path = tmp_dir / "workflow.yaml"
            file_path.write_text(data, encoding="utf-8")

            values = orchestrator._parse_yaml_id_list(file_path, "default_pipeline")
            self.assertEqual(values, ["concept", "game_design", "coder"])
        finally:
            for child in tmp_dir.glob("*"):
                child.unlink()
            tmp_dir.rmdir()

    def test_pipeline_dependencies_block_until_previous_stage_done(self) -> None:
        state = orchestrator.new_state()

        pipeline = orchestrator.create_pipeline(
            state,
            "Test Pipeline",
            "Validate dependency handling",
            ["concept", "coder"],
        )

        first_task = orchestrator.get_task(state, pipeline["task_ids"][0])
        second_task = orchestrator.get_task(state, pipeline["task_ids"][1])

        self.assertIsNotNone(first_task)
        self.assertIsNotNone(second_task)
        self.assertEqual(orchestrator.task_dependencies(second_task), [first_task["id"]])
        self.assertEqual(orchestrator.next_queued_task(state)["id"], first_task["id"])

        first_task["status"] = "done"
        self.assertEqual(orchestrator.next_queued_task(state)["id"], second_task["id"])

    def test_stage_template_is_injected_into_pipeline_task(self) -> None:
        tmp_dir = Path(self._testMethodName)
        templates_dir = tmp_dir / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        (templates_dir / "concept.md").write_text(
            "Acceptance Criteria:\n- Produce 3 candidate concepts",
            encoding="utf-8",
        )

        original_template_dir = orchestrator.STAGE_TEMPLATE_DIR
        orchestrator.STAGE_TEMPLATE_DIR = templates_dir
        try:
            state = orchestrator.new_state()
            pipeline = orchestrator.create_pipeline(
                state,
                "Concept Pipeline",
                "Find top-level concept options",
                ["concept"],
            )
            task = orchestrator.get_task(state, pipeline["task_ids"][0])
            self.assertIsNotNone(task)
            self.assertIn("Stage template:", task["description"])
            self.assertIn("Produce 3 candidate concepts", task["description"])
        finally:
            orchestrator.STAGE_TEMPLATE_DIR = original_template_dir
            for child in templates_dir.glob("*"):
                child.unlink()
            templates_dir.rmdir()
            tmp_dir.rmdir()

    def test_recompute_pipeline_status_transitions(self) -> None:
        state = orchestrator.new_state()

        pipeline = orchestrator.create_pipeline(
            state,
            "Status Pipeline",
            "Validate status transitions",
            ["concept", "coder"],
        )

        status = orchestrator.recompute_pipeline_status(state, pipeline["id"])
        self.assertEqual(status, "queued")

        first_task = orchestrator.get_task(state, pipeline["task_ids"][0])
        second_task = orchestrator.get_task(state, pipeline["task_ids"][1])
        self.assertIsNotNone(first_task)
        self.assertIsNotNone(second_task)

        first_task["status"] = "running"
        self.assertEqual(orchestrator.recompute_pipeline_status(state, pipeline["id"]), "running")

        first_task["status"] = "done"
        second_task["status"] = "running"
        self.assertEqual(orchestrator.recompute_pipeline_status(state, pipeline["id"]), "running")

        second_task["status"] = "done"
        self.assertEqual(orchestrator.recompute_pipeline_status(state, pipeline["id"]), "done")

    def test_create_debate_sets_moderator_dependency(self) -> None:
        state = orchestrator.new_state()
        debate = orchestrator.create_debate(
            state,
            "Infra Tradeoff",
            "Should we prioritize delivery speed or resiliency first?",
            ["council_red", "council_blue", "council_green"],
            "orchestrator",
        )
        self.assertEqual(len(debate["task_ids"]), 4)

        moderator_task = orchestrator.get_task(state, debate["moderator_task_id"])
        self.assertIsNotNone(moderator_task)
        deps = orchestrator.task_dependencies(moderator_task)
        self.assertEqual(deps, debate["participant_task_ids"])

    def test_resolve_role_workdir_uses_config_when_directory_exists(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-test-") as tmp:
            tmp_path = Path(tmp)
            role_dir = tmp_path / "team" / "workspaces" / "coder"
            role_dir.mkdir(parents=True)

            cfg_path = tmp_path / "workspaces.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "use_role_workspaces_if_present": True,
                        "roles": {"coder": str(role_dir)},
                    }
                ),
                encoding="utf-8",
            )

            orchestrator.WORKSPACE_CONFIG_FILE = cfg_path
            resolved = orchestrator.resolve_role_workdir("coder")
            self.assertEqual(resolved, role_dir.resolve())

    def test_recover_inflight_tasks_requeues_running_items(self) -> None:
        state = orchestrator.new_state()
        task = orchestrator.enqueue_task(state, "coder", "Recover me", "Synthetic running task")
        task["status"] = "running"
        task["started_at"] = orchestrator.utc_now()

        recovered = orchestrator.recover_inflight_tasks(state, "unit test")
        self.assertEqual(recovered, 1)
        self.assertEqual(task["status"], "queued")
        self.assertIsNone(task["started_at"])


if __name__ == "__main__":
    unittest.main()
