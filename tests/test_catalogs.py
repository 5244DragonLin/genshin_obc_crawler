#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接口客户端纯逻辑测试（deep_parse、卡片字段、分类解析），不联网。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from obc_api import Client, deep_parse
from catalogs import CATALOGS, normalize_catalogs
from exporter import _subchannel, is_preview


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

    def test_filters_all(self):
        # 一个词条可以挂多个同类标签：敌人常有两种元素
        card = {"content_id": 1, "title": "丘林",
                "ext": '{"c_6":{"filter":{"text":"[\\"类型/普通\\",\\"元素/风\\",\\"元素/冰\\"]"}}}'}
        client = Client()
        self.assertEqual(client.card_filter_all(card, "元素"), ["风", "冰"])
        self.assertEqual(client.card_filter_all(card, "类型"), ["普通"])
        self.assertEqual(client.card_filter_all(card, "攻击方式"), [])

    def test_int_content_id(self):
        client = Client()
        self.assertEqual(client.card_id({"content_id": 54}), "54")

    def test_card_is_preview(self):
        client = Client()
        self.assertTrue(client.card_is_preview({"title": "米提亚【预告】"}))
        self.assertFalse(client.card_is_preview({"title": "丝柯克"}))
        self.assertFalse(client.card_is_preview({}))


class TestNormalizeCatalogs(unittest.TestCase):
    ALL = [c["key"] for c in CATALOGS]

    def test_default_all(self):
        self.assertEqual([c["key"] for c in normalize_catalogs(None)], self.ALL)
        self.assertEqual([c["key"] for c in normalize_catalogs([])], self.ALL)

    def test_the_six_dedicated_first(self):
        # 六类专用图鉴固定排在最前，其余通用分类跟随其后
        self.assertEqual(self.ALL[:6], ["character", "weapon", "artifact",
                                        "enemy", "food", "book"])

    def test_alias(self):
        keys = [c["key"] for c in normalize_catalogs(["角色"])]
        self.assertEqual(keys, ["character"])
        keys = [c["key"] for c in normalize_catalogs(["武器", "artifact"])]
        self.assertEqual(keys, ["weapon", "artifact"])

    def test_new_catalog_alias(self):
        self.assertEqual([c["key"] for c in normalize_catalogs(["敌人"])], ["enemy"])
        self.assertEqual([c["key"] for c in normalize_catalogs(["食物图鉴"])], ["food"])
        self.assertEqual([c["key"] for c in normalize_catalogs(["书籍"])], ["book"])

    def test_quicknav_aliases(self):
        # 快捷导航上的中文名与频道名都要能认出来
        cases = {
            "材料一览": "material", "家具一览": "furnishing", "秘境": "domain",
            "成就": "achievement", "名片": "namecard", "头像": "avatar",
            "动物": "animal", "书籍": "book", "深境螺旋": "abyss",
            "幻想真境剧诗": "imaginarium", "幽境危战": "perilous",
            "冒险家协会": "guild", "卡牌资料": "card", "千星奇域": "theater",
            "影音回廊": "media", "「灰眸」": "ashen_eye", "组织": "organization",
            "考据": "lore", "活动": "event", "任务": "quest",
            "NPC＆商店": "npc", "敌人一览": "enemy", "角色图鉴": "character",
        }
        for alias, expected in cases.items():
            self.assertEqual([c["key"] for c in normalize_catalogs([alias])],
                             [expected], alias)

    def test_dedup_and_order(self):
        # 输出顺序固定为内置顺序（角色 → 武器 → 圣遗物 …），不跟随命令行顺序
        keys = [c["key"] for c in normalize_catalogs(["圣遗物", "角色", "角色图鉴"])]
        self.assertEqual(keys, ["character", "artifact"])
        keys = [c["key"] for c in normalize_catalogs(["书籍", "敌人", "食物"])]
        self.assertEqual(keys, ["enemy", "food", "book"])

    def test_unknown(self):
        with self.assertRaises(ValueError):
            normalize_catalogs(["不存在的分类"])

    def test_every_catalog_has_channel(self):
        for catalog in CATALOGS:
            self.assertTrue(catalog["name"].endswith("图鉴"), catalog["name"])
            self.assertIsInstance(catalog["channel"], int)
            # 专用建模给 model，通用建模给 generic
            self.assertTrue(catalog.get("model") or catalog.get("generic"),
                            catalog["key"])


class TestSubchannel(unittest.TestCase):
    SUBS = {264: "衣装套装", 266: "衣装部件"}

    def test_identify(self):
        card = {"content_id": 1, "ext": {"c_266": {"filter": {"text": []}}}}
        self.assertEqual(_subchannel(card, self.SUBS), "衣装部件")

    def test_no_match(self):
        self.assertIsNone(_subchannel({"ext": {"c_999": {}}}, self.SUBS))
        self.assertIsNone(_subchannel({"ext": {}}, self.SUBS))
        self.assertIsNone(_subchannel({}, self.SUBS))
        # 没声明子频道表时一律不认
        self.assertIsNone(_subchannel({"ext": {"c_264": {}}}, None))


class TestPreviewSkip(unittest.TestCase):
    CARD = {"title": "米提亚【预告】"}

    def test_skip_by_default(self):
        self.assertTrue(is_preview(self.CARD))
        self.assertTrue(is_preview(self.CARD, {"name": "角色图鉴"}))
        self.assertFalse(is_preview({"title": "丝柯克"}))
        self.assertFalse(is_preview({}))

    def test_media_catalog_keeps_pv(self):
        # 影音类频道的「角色预告 PV」是正经片名，不能当未上线占位跳过
        media = {"name": "影音回廊图鉴", "previews": False}
        self.assertFalse(is_preview({"title": "角色预告-「薇斯纳」"}, media))
        self.assertFalse(is_preview({"title": "剧情PV-「往日」"}, media))


if __name__ == "__main__":
    unittest.main()
