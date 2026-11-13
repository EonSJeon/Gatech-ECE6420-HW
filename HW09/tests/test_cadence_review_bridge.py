import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import cadence_review_bridge as bridge


class NativeReviewWorkflowTests(unittest.TestCase):
    def fixture(self, root):
        result = {"status": "complete", "run_id": "baseline-original", "config": {},
                  "circuits": {"active": {}, "passive": {}}}
        source = root / "results/hw9_results.json"
        source.parent.mkdir(parents=True)
        source.write_text(json.dumps(result) + "\n")
        return source

    def test_snapshot_retains_original_exact_bytes_after_cached_baseline_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.fixture(root)
            original = source.read_bytes()
            saved = bridge.preserve_python_baseline(root)
            source.write_text(source.read_text().replace("baseline-original", "baseline-later"))
            again = bridge.preserve_python_baseline(root)
            self.assertEqual(Path(saved["path"]).read_bytes(), original)
            self.assertEqual(saved, again)

    def test_snapshot_modification_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            saved = bridge.preserve_python_baseline(root)
            with Path(saved["path"]).open("a") as stream:
                stream.write(" ")
            with self.assertRaisesRegex(ValueError, "immutable.*modified"):
                bridge.preserve_python_baseline(root)

    def test_incomplete_or_gui_data_cannot_be_standalone_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.fixture(root)
            result = json.loads(source.read_text())
            result["origin"] = "cadence_ade_gui"
            source.write_text(json.dumps(result))
            with self.assertRaises(ValueError):
                bridge.preserve_python_baseline(root)

    def test_fetch_has_no_push_delete_or_simulation_and_excludes_live_locks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0,
                    "cadence\nsimulation/cadence_gui\ncds.lib\nade_native_paths.tsv\n" if command[0] == "ssh" else "", "")
            with patch.object(bridge.subprocess, "run", side_effect=run):
                record = bridge.fetch_gui_artifacts(root, bridge.RemoteConfig())
            transfers = [c for c in calls if c[0] == "rsync"]
            self.assertEqual(len(transfers), 4)
            for command in transfers:
                self.assertIn("--safe-links", command)
                self.assertIn("--exclude=*.cdslck*", command)
                self.assertIn("--exclude=*manifest.json", command)
                self.assertNotIn("--delete", command)
                self.assertTrue(command[-2].startswith("gt-ece:/nethome/sjeon84/Gatech-ECE6420/HW09/"))
                self.assertTrue(command[-1].startswith(str(root.resolve())))
            joined = " ".join(" ".join(c) for c in calls)
            self.assertNotIn("remote_worker", joined)
            self.assertNotIn("spectre", joined)
            self.assertFalse(record["simulator_invoked"])
            self.assertFalse(record["source_push"])

    def test_fetch_rejects_unexpected_remote_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.CompletedProcess([], 0, "cadence\nsimulation/cadence_gui\n../other\n", "")
            with patch.object(bridge.subprocess, "run", return_value=result):
                with self.assertRaisesRegex(ValueError, "Unexpected"):
                    bridge.fetch_gui_artifacts(Path(tmp), bridge.RemoteConfig())

    def test_manifest_path_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                bridge.project_path(Path(tmp), "../outside.json")
            with self.assertRaises(ValueError):
                bridge.project_path(Path(tmp), "/tmp/absolute.json")

    def test_gui_export_mode_displays_supplied_images_without_python_plotting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"results").mkdir()
            result={"origin":"cadence_ade_gui","status":"complete","plot_figure_mode":"cadence_gui_export",
                    "numerical_plot_figures":[{"kind":"active","role":"transient","image_path":"actual.png"}]}
            (root/"results/cadence_gui_results.json").write_text(json.dumps(result))
            checks=[]
            with patch.dict(sys.modules,{"cadence_gui_figures":SimpleNamespace(validate=lambda *args:checks.append(args)),
                                         "plots":SimpleNamespace(_plots_one=lambda *args,**kwargs:self.fail("Python plot fallback"))}):
                figures=bridge.render_gui_figures(root,show=False)
            self.assertEqual(figures,{"active_transient":root.resolve()/"actual.png"});self.assertEqual(len(checks),1)

    def test_missing_gui_exports_are_rejected_without_python_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"results").mkdir()
            result={"origin":"cadence_ade_gui","status":"complete","run_id":"test",
                    "plot_figure_mode":"cadence_gui_export","numerical_plot_figures":[]}
            (root/"results/cadence_gui_results.json").write_text(json.dumps(result))
            sys.path.insert(0,str(ROOT/"tools"))
            with patch.dict(sys.modules,{"plots":SimpleNamespace(_plots_one=lambda *args,**kwargs:self.fail("Python plot fallback"))}):
                with self.assertRaisesRegex(ValueError,"Complete12"):bridge.render_gui_figures(root,show=False)


if __name__ == "__main__":
    unittest.main()
