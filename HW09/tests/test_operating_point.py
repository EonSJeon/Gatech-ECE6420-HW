"""PSF STRUCT field order, strict counts, integer fields, and NaN omission."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from operating_point import read_operating_points


FIELDS = [("region", "INT BYTE"), ("gm", "FLOAT DOUBLE"), ("id", "FLOAT DOUBLE"),
          ("vds", "FLOAT DOUBLE"), ("gds", "FLOAT DOUBLE"), ("vth", "FLOAT DOUBLE"),
          ("vdsat", "FLOAT DOUBLE"), ("vgs", "FLOAT DOUBLE"), ("optional", "FLOAT DOUBLE")]


def fixture(fields=FIELDS, values=None, extra="", marker="TYPE"):
    values = values or ["2", ".012", ".001", ".4", ".0002", ".45", ".12", ".6", "nan"]
    declaration = "\n".join('"%s" %s PROP(\n"description" "A property (with parentheses)"\n)' % pair for pair in fields)
    return ('HEADER\n"analysis type" "info"\n' + marker + '\n"bsim4" STRUCT(\n' + declaration +
            '\n) PROP(\n"key" "inst"\n)\nVALUE\n"I0.M1" "bsim4" (\n' + '\n'.join(values) +
            '\n) PROP(\n"model" "NMOS_VTH"\n)\n' + extra + 'END\n')


class OperatingPointTests(unittest.TestCase):
    def read(self, text):
        with patch.object(Path, "read_text", return_value=text):
            return read_operating_points("fixture.info")

    def test_uses_declared_field_order_and_omits_nan_explicitly(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = self.read(fixture())
        self.assertEqual(result["I0.M1"]["gm"], .012)
        self.assertEqual(result["I0.M1"]["id"], .001)
        self.assertEqual(result["I0.M1"]["region"], 2)
        self.assertIsInstance(result["I0.M1"]["region"], int)
        self.assertNotIn("optional", result["I0.M1"])
        self.assertEqual(len(caught), 1)
        self.assertIn("optional", str(caught[0].message))

    def test_field_reordering_changes_mapping_without_hardcoded_indices(self):
        order = list(reversed(FIELDS))
        values = ["0", ".61", ".13", ".46", ".0003", ".41", ".002", ".013", "1"]
        result = self.read(fixture(order, values, marker="TYPES"))
        self.assertEqual(result["I0.M1"]["gm"], .013)
        self.assertEqual(result["I0.M1"]["id"], .002)
        self.assertEqual(result["I0.M1"]["region"], 1)

    def test_truncated_or_extra_values_fail_instead_of_shifting_labels(self):
        for values in (["0"] * 8, ["0"] * 10):
            with self.subTest(count=len(values)), self.assertRaisesRegex(ValueError, "count mismatch"):
                self.read(fixture(values=values))

    def test_duplicate_fields_and_instances_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate field"):
            self.read(fixture(fields=FIELDS + [FIELDS[0]], values=["0"] * 10))
        duplicate = '"I0.M1" "bsim4" (\n' + "\n".join(["0"] * 9) + '\n) PROP("model" "NMOS_VTH")\n'
        with self.assertRaisesRegex(ValueError, "Duplicate PSF instance"):
            self.read(fixture(values=["0"] * 9, extra=duplicate))

    def test_invalid_numbers_missing_end_and_nonintegral_region_fail(self):
        with self.assertRaisesRegex(ValueError, "Invalid numeric"):
            self.read(fixture(values=["broken"] + ["0"] * 8))
        with self.assertRaisesRegex(ValueError, "Nonintegral"):
            self.read(fixture(values=["1.5"] + ["0"] * 8))
        with self.assertRaisesRegex(ValueError, "Truncated"):
            self.read(fixture(values=["0"] * 9).replace("END\n", ""))


if __name__ == "__main__":
    unittest.main()
