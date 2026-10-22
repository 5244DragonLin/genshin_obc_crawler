#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""增量对账测试：指纹稳定性、cover 忽略、变更记录。"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from state import Changes, fingerprint, load_old_records


class TestFingerprint(unittest.TestCase):
    def test_stable(self):
        record = {"id": "1", "name": "甲", "skills": ["a", "b"]}
        self.assertEqual(fingerprint(record), fingerprint(dict(record)))

    def test_key_order_ignored(self):
        a = fingerprint({"id": "1", "name": "甲"})
        b = fingerprint({"name": "甲", "id": "1"})
        self.assertEqual(a, b)

    def test_cover_ignored(self):
        base = {"id": "1", "name": "甲"}
        with_cover = dict(base, cover="assets/character/甲.png")
        self.assertEqual(fingerprint(base), fingerprint(with_cover))

    def test_content_change_detected(self):
        a = fingerprint({"id": "1", "name": "甲"})
        b = fingerprint({"id": "1", "name": "乙"})
        self.assertNotEqual(a, b)


class TestLoadOldRecords(unittest.TestCase):
    def test_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = {"name": "角色图鉴"}
            data = {"catalog": "角色图鉴", "count": 1,
                    "items": [{"id": "1", "name": "甲"}, {"id": "2", "name": "乙"}]}
            with open(os.path.join(tmp, "角色图鉴.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            records = load_old_records(tmp, catalog)
            self.assertEqual(set(records), {"1", "2"})

    def test_missing_or_broken(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_old_records(tmp, {"name": "角色图鉴"}), {})
            with open(os.path.join(tmp, "角色图鉴.json"), "w", encoding="utf-8") as f:
                f.write("{broken")
            self.assertEqual(load_old_records(tmp, {"name": "角色图鉴"}), {})


class TestChanges(unittest.TestCase):
    def test_totals_and_dump(self):
        changes = Changes()
        changes.add("character", "角色图鉴", added=2, updated=1, removed=0,
                    failed=0, unchanged=3)
        changes.add("weapon", "武器图鉴", added=0, updated=0, removed=1,
                    failed=2, unchanged=0)
        totals = changes.totals()
        self.assertEqual(totals["added"], 2)
        self.assertEqual(totals["updated"], 1)
        self.assertEqual(totals["removed"], 1)
        self.assertEqual(totals["failed"], 2)
        self.assertEqual(totals["unchanged"], 3)
        with tempfile.TemporaryDirectory() as tmp:
            path = changes.dump(tmp)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data["catalogs"]), 2)
            self.assertEqual(data["totals"]["added"], 2)


if __name__ == "__main__":
    unittest.main()
