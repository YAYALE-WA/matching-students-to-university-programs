#!/usr/bin/env python3
"""Read-only validation of a four-column admissions shortlist transformation."""
import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path
import sys

FIELDS = ["学校", "英文项目名称", "中文项目名称", "分级标签"]


def read_table(path, require_bom=False):
    raw = Path(path).read_bytes()
    if require_bom and not raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path}: target requires UTF-8 BOM")
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True))
    if not rows:
        raise ValueError(f"{path}: empty file")
    header, body = rows[0], rows[1:]
    if len(set(header)) != len(header):
        raise ValueError(f"{path}: duplicate column names")
    for number, row in enumerate(body, 2):
        if len(row) != len(header):
            raise ValueError(f"{path}: row {number} has inconsistent column count")
    return header, body


def project(header, rows, label):
    fields = FIELDS[:3] + [label]
    missing = [field for field in fields if field not in header]
    if missing:
        raise ValueError(f"missing source columns: {missing}")
    positions = [header.index(field) for field in fields]
    selected = [[row[i] for i in positions] for row in rows]
    keys = set()
    for number, row in enumerate(selected, 2):
        if any(not value.strip() for value in row):
            raise ValueError(f"row {number}: required field is blank")
        key = tuple(row[:2])
        if key in keys:
            raise ValueError(f"row {number}: duplicate school/programme")
        keys.add(key)
    return selected


def validate(source, target, excluded=(), source_label="分级标签"):
    header, body = read_table(source)
    original = project(header, body, source_label)
    excluded = set(excluded)
    unknown = excluded - {row[0] for row in original}
    if unknown:
        raise ValueError(f"excluded schools absent from source: {sorted(unknown)}")
    expected = [row for row in original if row[0] not in excluded]
    target_header, target_body = read_table(target, require_bom=True)
    if target_header != FIELDS:
        raise ValueError(f"target columns must be exactly {FIELDS}")
    actual = project(target_header, target_body, "分级标签")
    if actual != expected:
        raise ValueError("target differs from filtered source: check names, labels, rows and order")
    return {
        "status": "passed",
        "projects": len(actual),
        "schools": len({row[0] for row in actual}),
        "labels": dict(Counter(row[3] for row in actual)),
        "scope": "CSV structure and transformation only; no admissions verification",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Original UTF-8 CSV; extra columns are allowed")
    parser.add_argument("--target", required=True, help="Four-column UTF-8 BOM CSV to verify")
    parser.add_argument("--exclude-school", action="append", default=[], help="Exact school name; repeat as needed")
    parser.add_argument("--source-label", default="分级标签", help="Source tier column name, if different")
    args = parser.parse_args()
    try:
        result = validate(args.source, args.target, args.exclude_school, args.source_label)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
