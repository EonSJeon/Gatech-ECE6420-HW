"""HW09-only deletion scope, protected results, and current-value transport."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import remote_bridge as bridge


class RemoteWorkflowTests(unittest.TestCase):
    def test_deletion_scope_cannot_point_to_another_homework_or_home(self):
        for path in ("/nethome/sjeon84", "/nethome/sjeon84/Gatech-ECE6420/HW05",
                     "/nethome/sjeon84/Gatech-ECE6420/HW09/..", "/tmp/HW09"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                bridge.RemoteConfig(directory=path)
        for host in ("-Fbad", "gt-ece;false", "gt ece"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                bridge.RemoteConfig(host=host)

    def test_source_delete_protects_current_data_and_private_configuration(self):
        calls = []
        with patch.object(bridge, "run_command"), patch.object(bridge, "rsync", side_effect=lambda *a, **kw: calls.append((a, kw))):
            bridge.push_sources(bridge.RemoteConfig(), dry_run=True)
        self.assertEqual(len(calls), 1)
        args, options = calls[0]
        self.assertTrue(options["delete"])
        self.assertEqual(args[2], "gt-ece:/nethome/sjeon84/Gatech-ECE6420/HW09/")
        for protected in ("/results/", "/simulation/", "/netlists/generated/", ".venv/", ".remote.env"):
            self.assertIn(protected, options["excludes"])

    def test_current_unsaved_parameters_are_json_not_shell_code(self):
        # A string containing shell syntax must stay inert in the JSON payload.
        config = {"common": {"vdd_v": 1.0}, "active": {"rf_bias_v": .537},
                  "measurement_label": "literal $(printf unwanted); `false`"}
        calls = []
        saved = {"status": "partial", "config": config, "run_id": "test-run"}
        with patch.object(bridge, "push_sources"), patch.object(bridge, "pull_data"), \
                patch.object(bridge, "run_command", side_effect=lambda command, payload=None: calls.append((command, payload))), \
                patch.object(bridge.Path, "is_file", return_value=True), \
                patch.object(bridge.Path, "read_text", return_value=json.dumps(saved)):
            result = bridge.run_remote(config, ["single_tone", "linearity"], bridge.RemoteConfig())
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["results_path"].endswith("results/hw9_results.json"))
        self.assertEqual(json.loads(calls[0][1]), {"config": config, "stages": ["single_tone", "linearity"]})
        self.assertNotIn("unwanted", " ".join(calls[0][0]))
        self.assertIn("bash -c", calls[0][0][-1])

    def test_missing_or_mismatched_result_metadata_is_rejected(self):
        with patch.object(bridge, "push_sources"), patch.object(bridge, "pull_data"), \
                patch.object(bridge, "run_command"), patch.object(bridge.Path, "is_file", return_value=False):
            with self.assertRaises(FileNotFoundError):
                bridge.run_remote({"expected": 1}, remote=bridge.RemoteConfig())
        with patch.object(bridge, "push_sources"), patch.object(bridge, "pull_data"), \
                patch.object(bridge, "run_command"), patch.object(bridge.Path, "is_file", return_value=True), \
                patch.object(bridge.Path, "read_text", return_value=json.dumps({"status": "complete", "config": {"expected": 2}})):
            with self.assertRaisesRegex(ValueError, "do not match"):
                bridge.run_remote({"expected": 1}, remote=bridge.RemoteConfig())

    def test_data_pull_cannot_replace_local_notebook_or_import_figures(self):
        calls = []
        with patch.object(bridge, "rsync", side_effect=lambda *a, **kw: calls.append((a, kw))):
            bridge.pull_data(bridge.RemoteConfig(), dry_run=True)
        self.assertEqual(len(calls), 3)
        for args, options in calls:
            self.assertNotIn("delete", options)
            self.assertIn("*.png", options["excludes"])
            self.assertIn("*.ipynb", options["excludes"])
            self.assertIn("*.pdf", options["excludes"])
            self.assertNotIn("/notebooks/", args[1])

    def test_failed_worker_preserves_error_and_attempts_log_fetch(self):
        error = RuntimeError("Spectre worker failed")
        with patch.object(bridge, "push_sources"), \
                patch.object(bridge, "run_command", side_effect=error), \
                patch.object(bridge, "pull_data", side_effect=RuntimeError("Network unavailable")) as pull:
            with self.assertRaisesRegex(RuntimeError, "Spectre worker failed"):
                bridge.run_remote({})
        pull.assert_called_once()


if __name__ == "__main__":
    unittest.main()
