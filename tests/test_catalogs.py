#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接口客户端纯逻辑测试（deep_parse、卡片字段、分类解析），不联网。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from obc_api import Client, deep_parse
from exporter import normalize_catalogs


class TestDeepParse(unittest.TestCase):
    def test_python_literal(self):
        text = "{'a': 1, 'b': ['甲', True, None]}"
        self.assertEqual(deep_parse(text), {"a": 1, "b": ["甲", True, None]})

    def test_json_string(self):
        self.assertEqual(deep_parse('{"x": "y"}'), {"x": "y"})

    def test_nested(self):
        value = {"ext": '{"filter": "[\\"元素/冰\\"]"}'}
        self.assertEqual(deep_parse(value), {"ext": {"filter": ["元素/冰"]}})

    def test_untouched(self):
        self.assertEqual(deep_parse("普通文本"), "普通文本")
        self.assertEqual(deep_parse(123), 123)
        self.assertEqual(deep_parse(None), None)


class TestCardHelpers(unittest.TestCase):
    CARD = {"content_id": 505417, "title": "丝柯克", "icon": "http://icon.png",
            "summary": "简介", "alias_name": "别称",
            "ext": '{"c_25":{"filter":{"text":"[\\"地区/纳塔\\",\\"元素/冰\\",\\"武器/单手剑\\",\\"星级/五星\\"]"}}}'}

    def test_fields(self):
        client = Client()
        self.assertEqual(client.card_id(self.CARD), "505417")
        self.assertEqual(client.card_name(self.CARD), "丝柯克")
        self.assertEqual(client.card_icon(self.CARD), "http://icon.png")
        self.assertEqual(client.card_summary(self.CARD), "简介")
        self.assertEqual(client.card_alias(self.CARD), "别称")

    def test_filters(self):
        client = Client()
        self.assertEqual(client.card_filters(self.CARD),
                         ["地区/纳塔", "元素/冰", "武器/单手剑", "星级/五星"])
        self.assertEqual(client.card_filter(self.CARD, "元素"), "冰")
        self.assertEqual(client.card_filter(self.CARD, "武器"), "单手剑")
        self.assertIsNone(client.card_filter(self.CARD, "神之眼"))

    def test_int_content_id(self):
        client = Client()
        self.assertEqual(client.card_id({"content_id": 54}), "54")


class TestNormalizeCatalogs(unittest.TestCase):
    def test_default_all(self):
        self.assertEqual([c["key"] for c in normalize_catalogs(None)],
                         ["character", "weapon", "artifact"])
        self.assertEqual([c["key"] for c in normalize_catalogs([])],
                         ["character", "weapon", "artifact"])

    def test_alias(self):
        keys = [c["key"] for c in normalize_catalogs(["角色"])]
        self.assertEqual(keys, ["character"])
        keys = [c["key"] for c in normalize_catalogs(["武器", "artifact"])]
        self.assertEqual(keys, ["weapon", "artifact"])

    def test_dedup_and_order(self):
        # 输出顺序固定为内置顺序（角色 → 武器 → 圣遗物），不跟随命令行顺序
        keys = [c["key"] for c in normalize_catalogs(["圣遗物", "角色", "角色图鉴"])]
        self.assertEqual(keys, ["character", "artifact"])

    def test_unknown(self):
        with self.assertRaises(ValueError):
            normalize_catalogs(["不存在的分类"])


if __name__ == "__main__":
    unittest.main()
