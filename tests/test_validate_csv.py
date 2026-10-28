import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_csv.py"
HEADER = ["学校", "英文项目名称", "中文项目名称", "分级标签"]
ROWS = [
    ["学校甲", "Master of Science in AI, Data and Systems", "人工智能、数据与系统理学硕士", "求稳"],
    ["学校乙", "Master of Computing", "计算学硕士", "冲刺（资格待核）"],
    ["学校丙", "Master of Data Science", "数据科学硕士", "保底"],
]


class CsvValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source.csv"
        self.target = Path(self.temp.name) / "target.csv"
        self.write(self.source, ROWS)

    def write(self, path, rows, header=HEADER, bom=True):
        with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)

    def run_check(self, *extra):
        before = self.source.read_bytes()
        result = subprocess.run([sys.executable, str(SCRIPT), "--source", str(self.source),
                                 "--target", str(self.target), *extra], capture_output=True, text=True)
        self.assertEqual(before, self.source.read_bytes())
        return result

    def test_valid_exclusion_and_embedded_comma(self):
        self.write(self.target, ROWS[:2])
        result = self.run_check("--exclude-school", "学校丙")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["projects"], 2)
        self.assertEqual(data["labels"], {"求稳": 1, "冲刺（资格待核）": 1})

    def test_multiple_disciplines_and_conditional_labels(self):
        rows = [
            ["学校甲", "Master of Arts in Comparative Literature", "比较文学文学硕士", "冲刺"],
            ["学校乙", "Master of Design", "设计硕士", "待定位（作品集待核）"],
            ["学校丙", "Master of Education", "教育硕士", "求稳（实习资格待核）"],
            ["学校丁", "Master of Science in Brand Management", "品牌管理理学硕士", "求稳"],
            ["学校戊", "Master of Public Health", "公共卫生硕士", "冲刺"],
        ]
        self.write(self.source, rows)
        self.write(self.target, rows)
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["projects"], 5)
        self.assertEqual(json.loads(result.stdout)["labels"]["待定位（作品集待核）"], 1)

    def test_changed_label_rejected(self):
        changed = [row[:] for row in ROWS]
        changed[1][3] = "冲刺"
        self.write(self.target, changed)
        self.assertEqual(self.run_check().returncode, 1)

    def test_changed_name_rejected(self):
        changed = [row[:] for row in ROWS]
        changed[0][1] = "MSc AI"
        self.write(self.target, changed)
        self.assertEqual(self.run_check().returncode, 1)

    def test_duplicate_rejected(self):
        self.write(self.target, ROWS + [ROWS[0]])
        self.assertEqual(self.run_check().returncode, 1)

    def test_unremoved_school_rejected(self):
        self.write(self.target, ROWS)
        self.assertEqual(self.run_check("--exclude-school", "学校丙").returncode, 1)

    def test_missing_bom_rejected(self):
        self.write(self.target, ROWS, bom=False)
        self.assertEqual(self.run_check().returncode, 1)

    def test_missing_label_column_rejected(self):
        self.write(self.target, [row[:3] for row in ROWS], header=HEADER[:3])
        self.assertEqual(self.run_check().returncode, 1)

    def test_source_label_alias_and_extra_column(self):
        self.write(self.source, [row + ["备注"] for row in ROWS],
                   header=HEADER[:3] + ["申请分级（策略判断）", "说明"])
        self.write(self.target, ROWS)
        self.assertEqual(self.run_check("--source-label", "申请分级（策略判断）").returncode, 0)

    def test_missing_file_error_is_actionable(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["status"], "failed")
        self.assertNotIn("Traceback", result.stderr)

    def test_unknown_exclusion_rejected(self):
        self.write(self.target, ROWS)
        self.assertEqual(self.run_check("--exclude-school", "拼错的学校").returncode, 1)

    def test_all_removed_is_valid_empty_shortlist(self):
        self.write(self.target, [])
        result = self.run_check("--exclude-school", "学校甲", "--exclude-school", "学校乙",
                                "--exclude-school", "学校丙")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["projects"], 0)


if __name__ == "__main__":
    unittest.main()
