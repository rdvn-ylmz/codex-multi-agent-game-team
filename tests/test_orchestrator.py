from __future__ import annotations

import unittest
from pathlib import Path

import team.orchestrator as orchestrator


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_append_event = orchestrator.append_event
        orchestrator.append_event = lambda *args, **kwargs: None

    def tearDown(self) -> None:
        orchestrator.append_event = self._original_append_event

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


if __name__ == "__main__":
    unittest.main()
