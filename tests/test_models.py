#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三类图鉴建模测试：用 tests/fixtures/ 下的真实词条样本。

样本截取自观测枢接口的实际响应（角色 = 丝柯克、武器 = 苍耀、
圣遗物 = 影中沉凝的幻灭），只保留建模用到的组件。
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import artifact_model
import character_md
import character_model
import weapon_model

def load_fixture(name):
    with open(os.path.join(FIXTURES, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

CARD = {"content_id": 999, "title": "测试",
        "ext": '{"c_25":{"filter":{"text":"[\\"地区/纳塔\\",\\"星级/五星\\",\\"元素/冰\\",\\"武器/单手剑\\"]"}}}',
        "icon": "http://icon/test.png", "summary": "测试简介", "alias_name": ""}


class TestCharacterModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = load_fixture("character")
        cls.record = character_model.build(CARD, cls.page)

    def test_base(self):
        record = self.record
        self.assertEqual(record["id"], "999")
        self.assertEqual(record["name"], "丝柯克")
        self.assertEqual(record["element"], "冰")
        self.assertEqual(record["weapon_type"], "单手剑")
        self.assertEqual(record["region"], "纳塔")
        self.assertEqual(record["rarity"], 5)

    def test_cv(self):
        self.assertEqual(self.record["cv"]["中"], "谢莹")
        self.assertEqual(self.record["cv"]["日"], "能登麻美子")

    def test_talent(self):
        talent = self.record["talents"][0]
        self.assertEqual(talent["name"], "极恶技·断")
        self.assertIn("普通攻击", talent["desc"])
        self.assertIn("LV1", talent["multipliers"]["header"])

    def test_constellations(self):
        names = [item["name"] for item in self.record["constellations"]]
        self.assertEqual(len(names), 6)
        self.assertEqual(names[0], "湮远")
        self.assertTrue(self.record["constellations"][0]["desc"])

    def test_ascension_materials(self):
        stage = self.record["ascension"][0]
        self.assertTrue(stage["materials"])
        first = stage["materials"][0]
        self.assertEqual(first["name"], "哀叙冰玉碎屑")
        self.assertEqual(first["count"], 1)
        self.assertEqual(first["id"], "857")

    def test_voices_and_stories(self):
        self.assertIn("汉语", self.record["voices"])
        self.assertIn("初次见面…", [v["name"] for v in self.record["voices"]["汉语"]])
        self.assertIn("角色故事1", self.record["stories"])

    def test_markdown(self):
        text = character_md.render(self.record)
        self.assertIn("# 丝柯克", text)
        self.assertIn("## 基础信息", text)
        self.assertIn("命之座", text)
        self.assertIn("角色故事1", text)


class TestWeaponModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = weapon_model.build(CARD, load_fixture("weapon"))

    def test_base(self):
        record = self.record
        self.assertEqual(record["name"], "苍耀")
        self.assertEqual(record["type"], "单手剑")
        self.assertEqual(record["rarity"], 5)

    def test_skill(self):
        skill = record = self.record["skill"]
        self.assertEqual(skill["name"], "白山的馈赐")
        self.assertIn("攻击力提升", skill["desc"])
        self.assertIn("精炼", skill["refinement"])

    def test_flavor_and_obtain(self):
        self.assertTrue(self.record["desc"])
        self.assertEqual(self.record["attrs"].get("获取途径"), "限时祈愿")

    def test_growth(self):
        stage = self.record["growth"][0]
        self.assertTrue(stage["materials"])
        self.assertTrue(stage["attrs"])


class TestArtifactModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = artifact_model.build(CARD, load_fixture("artifact"))

    def test_base(self):
        record = self.record
        self.assertEqual(record["name"], "影中沉凝的幻灭")
        self.assertIn("星", record["rarity"])

    def test_set_effects(self):
        self.assertIn("2件套效果", self.record["set_effects"])
        self.assertIn("4件套效果", self.record["set_effects"])

    def test_pieces(self):
        pieces = self.record["pieces"]
        self.assertEqual(list(pieces.keys()),
                         ["生之花", "死之羽", "时之沙", "空之杯", "理之冠"])
        self.assertTrue(pieces["生之花"]["name"])
        self.assertTrue(pieces["生之花"]["story"])


if __name__ == "__main__":
    unittest.main()
