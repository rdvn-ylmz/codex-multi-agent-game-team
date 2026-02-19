from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import team.orchestrator as orchestrator


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_append_event = orchestrator.append_event
        self._original_workspace_config_file = orchestrator.WORKSPACE_CONFIG_FILE
        self._original_model_router_file = orchestrator.MODEL_ROUTER_FILE
        self._original_quota_policy_file = orchestrator.QUOTA_POLICY_FILE
        orchestrator.append_event = lambda *args, **kwargs: None

    def tearDown(self) -> None:
        orchestrator.append_event = self._original_append_event
        orchestrator.WORKSPACE_CONFIG_FILE = self._original_workspace_config_file
        orchestrator.MODEL_ROUTER_FILE = self._original_model_router_file
        orchestrator.QUOTA_POLICY_FILE = self._original_quota_policy_file
        os.environ.pop("TEAM_PROJECT_ROOT", None)

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

    def test_read_default_debate_roles_falls_back_to_available_roles(self) -> None:
        with tempfile.TemporaryDirectory(prefix="debate-roles-") as tmp:
            tmp_path = Path(tmp)
            config_dir = tmp_path / "config"
            config_dir.mkdir(parents=True, exist_ok=True)

            (config_dir / "roles.yaml").write_text(
                (
                    "version: 1\n"
                    "roles:\n"
                    "  - id: orchestrator\n"
                    "  - id: concept\n"
                    "  - id: reviewer\n"
                    "  - id: security\n"
                ),
                encoding="utf-8",
            )
            (config_dir / "workflow.yaml").write_text(
                (
                    "workflow:\n"
                    "  default_debate:\n"
                    "    - council_red\n"
                    "    - council_blue\n"
                    "    - council_green\n"
                ),
                encoding="utf-8",
            )

            original_config_dir = orchestrator.CONFIG_DIR
            orchestrator.CONFIG_DIR = config_dir
            try:
                roles = orchestrator.read_default_debate_roles()
                self.assertEqual(roles, ["concept", "reviewer", "security"])
            finally:
                orchestrator.CONFIG_DIR = original_config_dir

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

    def test_resolve_role_workdir_uses_project_root_override(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-root-") as tmp:
            project_root = Path(tmp).resolve()
            os.environ["TEAM_PROJECT_ROOT"] = str(project_root)
            resolved = orchestrator.resolve_role_workdir("coder")
            self.assertEqual(resolved, project_root)

    def test_recover_inflight_tasks_requeues_running_items(self) -> None:
        state = orchestrator.new_state()
        task = orchestrator.enqueue_task(state, "coder", "Recover me", "Synthetic running task")
        task["status"] = "running"
        task["started_at"] = orchestrator.utc_now()

        recovered = orchestrator.recover_inflight_tasks(state, "unit test")
        self.assertEqual(recovered, 1)
        self.assertEqual(task["status"], "queued")
        self.assertIsNone(task["started_at"])

    def test_extract_output_contract_from_fenced_json(self) -> None:
        report = """
## Task Meta
...

```json
{
  "task_id": "TASK-0001",
  "owner": "coder",
  "status": "done",
  "acceptance_criteria": ["ac1"],
  "artifacts": [{"type": "files_changed", "value": ["docs/a.md"]}],
  "risks": [],
  "handoff_to": ["reviewer"],
  "next_role_action_items": [{"role": "reviewer", "items": ["check docs/a.md"]}]
}
```
"""
        contract = orchestrator.extract_output_contract(report)
        self.assertIsNotNone(contract)
        self.assertEqual(contract["task_id"], "TASK-0001")

    def test_validate_output_contract_requires_role_artifacts(self) -> None:
        task = {"id": "TASK-7777"}
        contract = {
            "task_id": "TASK-7777",
            "owner": "game_design",
            "status": "done",
            "acceptance_criteria": ["ac1"],
            "artifacts": [{"type": "files_changed", "value": ["docs/other.md"]}],
            "risks": [],
            "handoff_to": ["narrative"],
            "next_role_action_items": [{"role": "narrative", "items": ["do x"]}],
        }
        errors = orchestrator.validate_output_contract("game_design", task, contract)
        self.assertTrue(any("docs/game_design.md" in err for err in errors))

    def test_validate_report_structure_requires_all_sections(self) -> None:
        message = "## Task Meta\nx\n"
        errors = orchestrator.validate_report_structure(message)
        self.assertTrue(any("acceptance criteria" in err for err in errors))
        self.assertTrue(any("artifacts" in err for err in errors))
        self.assertTrue(any("handoff" in err for err in errors))

    def test_stage_templates_have_contract_compliant_json_footer(self) -> None:
        roles = [
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
        for role in roles:
            template_path = orchestrator.STAGE_TEMPLATE_DIR / f"{role}.md"
            template_text = template_path.read_text(encoding="utf-8")
            contract = orchestrator.extract_output_contract(template_text)
            self.assertIsNotNone(contract, f"{role} template JSON footer missing")
            errors = orchestrator.validate_output_contract(role, {"id": "TASK-0001"}, contract)
            self.assertEqual(errors, [], f"{role} template footer invalid: {errors}")

    def test_build_task_compression_summary_outputs_valid_json_footer(self) -> None:
        task = {"id": "TASK-9999", "title": "Implement API endpoint"}
        contract = {
            "task_id": "TASK-9999",
            "owner": "coder",
            "status": "needs_review",
            "acceptance_criteria": ["criterion 1 PASS", "criterion 2 PASS"],
            "artifacts": [
                {"type": "files_changed", "value": ["src/api.py"]},
                {"type": "commands", "value": ["./scripts/test.sh"]},
            ],
            "risks": ["rate limit not load-tested"],
            "handoff_to": ["reviewer"],
            "next_role_action_items": [{"role": "reviewer", "items": ["verify edge cases"]}],
        }
        summary = orchestrator.build_task_compression_summary(task, contract)
        self.assertIn("IMMUTABLE SUMMARY", summary)
        footer = orchestrator.extract_output_contract(summary)
        self.assertIsNotNone(footer)
        self.assertEqual(footer["type"], "compression_summary")
        self.assertEqual(footer["next_owner"], "reviewer")

    def test_model_chain_for_role_respects_configured_limit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="model-router-") as tmp:
            tmp_path = Path(tmp)
            router_file = tmp_path / "model_router.json"
            router_file.write_text(
                json.dumps(
                    {
                        "default_chain": [
                            {"backend": "codex", "model": ""},
                            {"backend": "opencode", "model": "opencode/glm-5-free"},
                        ],
                        "roles": {
                            "coder": [
                                {"backend": "codex", "model": ""},
                                {"backend": "opencode", "model": "opencode/kimi-k2.5-free"},
                                {"backend": "opencode", "model": "opencode/minimax-m2.5-free"},
                            ]
                        },
                        "max_model_attempts_per_task": 2,
                    }
                ),
                encoding="utf-8",
            )
            orchestrator.MODEL_ROUTER_FILE = router_file

            coder_chain = orchestrator.model_chain_for_role("coder")
            qa_chain = orchestrator.model_chain_for_role("qa")

            self.assertEqual(len(coder_chain), 2)
            self.assertEqual(coder_chain[1]["model"], "opencode/kimi-k2.5-free")
            self.assertEqual(qa_chain[0]["backend"], "codex")

    def test_set_task_retry_marks_deferred_and_blocks_queue_pick(self) -> None:
        state = orchestrator.new_state()
        task = orchestrator.enqueue_task(state, "coder", "Retry later", "Quota exhausted")
        orchestrator.set_task_retry(task, defer_minutes=5, reason="rate limit")
        self.assertTrue(orchestrator.is_task_deferred(task))
        self.assertIsNone(orchestrator.next_queued_task(state))
        blocked = orchestrator.queued_but_blocked(state)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["id"], task["id"])

    def test_is_quota_error_uses_custom_markers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="quota-policy-") as tmp:
            tmp_path = Path(tmp)
            quota_file = tmp_path / "quota_policy.json"
            quota_file.write_text(
                json.dumps(
                    {
                        "quota_error_markers": ["my-limit-marker"],
                        "defer_on_exhausted_models": True,
                        "defer_minutes_on_exhausted_models": 12,
                    }
                ),
                encoding="utf-8",
            )
            orchestrator.QUOTA_POLICY_FILE = quota_file

            self.assertTrue(orchestrator.is_quota_error("request failed: MY-LIMIT-MARKER"))
            self.assertFalse(orchestrator.is_quota_error("syntax error"))

    def test_dispatch_defers_task_when_all_models_are_quota_exhausted(self) -> None:
        state = orchestrator.new_state()
        task = orchestrator.enqueue_task(state, "coder", "Quota fallback", "Test defer behavior")

        original_run_model_task = orchestrator.run_model_task
        original_model_chain_for_role = orchestrator.model_chain_for_role
        original_save_state = orchestrator.save_state
        original_resolve_role_workdir = orchestrator.resolve_role_workdir

        try:
            def fake_run_model_task(
                *,
                role,
                task,
                session_id,
                handoff_context,
                workdir,
                backend,
                model,
                correction_feedback="",
            ):
                return orchestrator.CodexResult(
                    return_code=1,
                    session_id=None,
                    message="",
                    stderr="429 rate limit",
                    backend=backend,
                    model=model,
                )

            orchestrator.run_model_task = fake_run_model_task
            orchestrator.model_chain_for_role = lambda _role: [
                {"backend": "codex", "model": ""},
                {"backend": "opencode", "model": "opencode/kimi-k2.5-free"},
            ]
            orchestrator.save_state = lambda _state: None
            orchestrator.resolve_role_workdir = lambda _role: Path.cwd()

            with redirect_stdout(StringIO()):
                code = orchestrator._dispatch_task_object(state, task)

            self.assertEqual(code, 0)
            self.assertEqual(task["status"], "queued")
            self.assertTrue(orchestrator.is_task_deferred(task))
        finally:
            orchestrator.run_model_task = original_run_model_task
            orchestrator.model_chain_for_role = original_model_chain_for_role
            orchestrator.save_state = original_save_state
            orchestrator.resolve_role_workdir = original_resolve_role_workdir


if __name__ == "__main__":
    unittest.main()
