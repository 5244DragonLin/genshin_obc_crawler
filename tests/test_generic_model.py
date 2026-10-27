#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用建模测试：组件 → 区块 → 记录。

样本与 ``test_models.py`` 同源，截取自观测枢接口的实际响应（材料 = 吞吞鲸、
家具 = 「常伴梦乡」、秘境 = 荒坠的圣迹、成就 = 无束的残月、
名片 = 至冬·冰沫、深境螺旋 = 深境螺旋第8层、语音展示 = 旅行者语音展示（空）），
只保留建模用到的组件，表格行数与语音条数已截断。
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import catalogs
import component_blocks
import generic_model
from exporter import _subchannel

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


def make_card(content_id, title, filters, channel, summary="", icon="http://icon/test.png"):
    """按频道拼一张分类卡片：``filters`` 是要挂的筛选标签。"""
    text = "[" + ",".join(f'\\"{tag}\\"' for tag in filters) + "]"
    ext = '{"c_%d":{"filter":{"text":"%s"}}}' % (channel, text)
    return {"content_id": content_id, "title": title, "summary": summary,
            "alias_name": "", "icon": icon, "ext": ext}


def catalog_of(key):
    return next(c for c in catalogs.CATALOGS if c["key"] == key)


CARD_MATERIAL = make_card(
    510128, "吞吞鲸",
    ["道具类型/任务道具", "获取方式/任务获取", "星级/二星"], 13,
    summary="吞吞鲸")
CARD_FURNISHING = make_card(
    510118, "「常伴梦乡」",
    ["区域/室内", "类型/摆件", "品质/三星", "摆设获取方式/制作摆设获取",
     "图纸获取方式/奇馈的宝箱获得"], 130, summary="「常伴梦乡」")
CARD_DOMAIN = make_card(
    509456, "荒坠的圣迹",
    ["秘境类型/天赋培养素材", "秘境消耗/原粹树脂*20", "是否可联机/是",
     "是否为任务本/否"], 54, summary="荒坠的圣迹")
CARD_ACHIEVEMENT = make_card(
    509145, "无束的残月",
    ["成就集/无束的残月", "上线版本/月之八", "每日委托成就/否", "隐藏成就/否"], 252,
    summary="无束的残月")
CARD_NAMECARD = make_card(510042, "至冬·冰沫", ["名片类型/成就"], 109,
                          summary="至冬·冰沫")
CARD_ABYSS = make_card(512, "深境螺旋第8层", [], 65, summary="深境螺旋第8层")
CARD_VOICE = make_card(505542, "旅行者语音展示（空）", [], 84,
                       summary="旅行者语音展示（空）")


class TestBlocks(unittest.TestCase):
    """组件 → 区块的逐类转换。"""

    def test_material_item(self):
        page = load_fixture("material")
        blocks = component_blocks.blocks_of(page)
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertEqual(block["kind"], "item")
        self.assertEqual(block["name"], "吞吞鲸")
        self.assertEqual(block["rarity"], 2)
        self.assertTrue(block["icon"].startswith("http"))
        self.assertIn("流行", block["desc"])
        # 材料栏是一个「标签-值」对，标签与值都原样保留
        self.assertEqual(block["note"]["label"], "获取方式")
        self.assertIn("世界任务", block["note"]["text"])

    def test_furnishing_blocks(self):
        page = load_fixture("furnishing")
        blocks = component_blocks.blocks_of(page)
        self.assertEqual([b["kind"] for b in blocks], ["info", "info", "gallery"])
        head = blocks[0]
        self.assertEqual(head["name"], "「常伴梦乡」")
        self.assertEqual(head["rarity"], 3)
        # 制作材料里的词条带数量
        names = [entry["name"] for entry in head["entries"]]
        self.assertIn("铁块", names)
        iron = next(e for e in head["entries"] if e["name"] == "铁块")
        self.assertEqual(iron["count"], 6)
        self.assertTrue(iron["id"])
        self.assertEqual(len(blocks[2]["items"]), 2)

    def test_domain_blocks(self):
        page = load_fixture("domain")
        blocks = component_blocks.blocks_of(page)
        kinds = [b["kind"] for b in blocks]
        self.assertEqual(kinds, ["info", "table", "gallery", "table"])
        info = blocks[0]
        self.assertEqual(info["name"], "荒坠的圣迹")
        self.assertIn("是否可联机", info["attrs"])
        # 秘境详情的表格保留原文列名与单位
        detail = blocks[3]
        self.assertTrue(detail["tables"])
        self.assertIn("tab", detail["tables"][0])
        self.assertIn("冒险等级要求", detail["tables"][0]["rows"][0][0])

    def test_achievement_table(self):
        page = load_fixture("achievement")
        blocks = component_blocks.blocks_of(page)
        self.assertEqual([b["kind"] for b in blocks], ["item", "table"])
        table = blocks[1]["tables"][0]
        self.assertEqual(table["header"], ["名称", "描述"])
        self.assertEqual(table["rows"][0][0], "月雾的寻宝者")
        # 名片纹饰是材料栏里的词条，带 id 与图标
        note = blocks[0]["note"]
        self.assertEqual(note["label"], "名片纹饰")
        self.assertEqual(note["entries"][0]["id"], "509009")

    def test_namecard_gallery(self):
        page = load_fixture("namecard")
        blocks = component_blocks.blocks_of(page)
        self.assertEqual(blocks[0]["kind"], "gallery")
        tabs = [item["tab"] for item in blocks[0]["items"]]
        self.assertEqual(tabs, ["长图", "卡面"])

    def test_abyss_levels(self):
        page = load_fixture("abyss")
        blocks = component_blocks.blocks_of(page)
        levels = blocks[0]
        self.assertEqual(levels["kind"], "levels")
        first = levels["items"][0]
        self.assertEqual(first["tab"], "8-1")
        self.assertIn("挑战剩余时间", first["target"])
        # 上下半各有轮次，轮次里是敌人词条
        half = first["first_half"][0]
        self.assertEqual(half["tab"], "第一轮")
        names = [entry["name"] for entry in half["entries"]]
        self.assertIn("冰深渊法师", names)
        entry = next(e for e in half["entries"] if e["name"] == "冰深渊法师")
        self.assertEqual(entry["id"], "154")

    def test_voice_languages(self):
        page = load_fixture("voice")
        blocks = component_blocks.blocks_of(page)
        languages = blocks[0]["languages"]
        self.assertIn("汉语", languages)
        row = languages["汉语"][0]
        self.assertTrue(row["name"])
        self.assertTrue(row["audio"].endswith(".mp3"))

    def test_unknown_component_ignored(self):
        # 站点新增没见过的组件时不炸，只是不产出区块
        page = {"name": "测试", "modules": [
            {"name": "", "components": [
                {"component_id": "brand_new_widget", "data": {"x": 1}}]}]}
        self.assertEqual(component_blocks.blocks_of(page), [])
        self.assertFalse(component_blocks.supports("brand_new_widget"))


class TestGenericModel(unittest.TestCase):
    def test_material_record(self):
        record = generic_model.build(CARD_MATERIAL, load_fixture("material"),
                                     catalog_of("material"))
        self.assertEqual(record["id"], "510128")
        self.assertEqual(record["name"], "吞吞鲸")
        self.assertEqual(record["types"], ["任务道具"])
        self.assertEqual(record["sources"], ["任务获取"])
        # 中文数字星级摊成 int
        self.assertEqual(record["rarity"], 2)
        self.assertTrue(record["icon"].startswith("http"))
        self.assertIn("/510128/detail", record["url"])
        # 本体那一块提到顶层后不再进 sections
        self.assertNotIn("sections", record)

    def test_domain_record(self):
        record = generic_model.build(CARD_DOMAIN, load_fixture("domain"),
                                     catalog_of("domain"))
        self.assertEqual(record["types"], ["天赋培养素材"])
        self.assertEqual(record["cost"], "原粹树脂*20")
        # 是 / 否 摊成布尔
        self.assertIs(record["coop"], True)
        self.assertIs(record["quest_domain"], False)
        self.assertEqual(len(record["sections"]), 4)

    def test_furnishing_record(self):
        record = generic_model.build(CARD_FURNISHING, load_fixture("furnishing"),
                                     catalog_of("furnishing"))
        self.assertEqual(record["rarity"], 3)
        self.assertEqual(record["zones"], ["室内"])
        self.assertEqual(record["types"], ["摆件"])
        self.assertEqual(record["blueprint_sources"], ["奇馈的宝箱获得"])

    def test_achievement_record(self):
        record = generic_model.build(CARD_ACHIEVEMENT, load_fixture("achievement"),
                                     catalog_of("achievement"))
        self.assertEqual(record["set"], "无束的残月")
        self.assertEqual(record["version"], "月之八")
        self.assertIs(record["daily_commission"], False)
        self.assertIs(record["hidden"], False)
        self.assertEqual(record["note"]["label"], "名片纹饰")

    def test_absent_tags_not_written(self):
        # 卡片上没挂的标签不写键，不留 null / 空数组
        record = generic_model.build(CARD_ABYSS, load_fixture("abyss"),
                                     catalog_of("abyss"))
        self.assertNotIn("types", record)
        self.assertNotIn("rarity", record)

    def test_summary_dedup(self):
        # 摘要与名字相同时不重复收录（名片频道的摘要就是名片名）
        record = generic_model.build(CARD_NAMECARD, load_fixture("namecard"),
                                     catalog_of("namecard"))
        self.assertNotIn("summary", record)
        self.assertEqual(record["types"], ["成就"])

    def test_card_name_differs(self):
        # 列表标题与词条正式名不同时补一个 card_name
        card = dict(CARD_NAMECARD, title="至冬·冰沫（名片）")
        record = generic_model.build(card, load_fixture("namecard"),
                                     catalog_of("namecard"))
        self.assertEqual(record["name"], "至冬·冰沫")
        self.assertEqual(record["card_name"], "至冬·冰沫（名片）")

    def test_voice_record(self):
        record = generic_model.build(CARD_VOICE, load_fixture("voice"),
                                     catalog_of("media"))
        self.assertEqual(record["name"], "旅行者语音展示（空）")
        self.assertEqual(record["sections"][0]["kind"], "voice")
        self.assertIn("汉语", record["sections"][0]["languages"])

    def test_subchannel_record(self):
        # 聚合频道：卡片 ext 的 c_<子频道id> 落到记录的 channel
        card = make_card(510042, "至冬·冰沫", ["名片类型/成就"], 264,
                         summary="至冬·冰沫")
        sub = _subchannel(card, catalogs.THEATER_SUBCHANNELS)
        self.assertEqual(sub, "衣装套装")

    def test_no_catalog_passthrough(self):
        # 不传分类定义时只出公共字段与正文，不猜标签含义
        record = generic_model.build(CARD_MATERIAL, load_fixture("material"))
        self.assertEqual(sorted(record), ["desc", "icon", "id", "name", "note",
                                          "rarity", "url"])


class TestMerge(unittest.TestCase):
    def test_consecutive_merge(self):
        # 相邻且同 kind + 同 tab 的区块合并：站点把「任务概述」重复挂了三次
        sections = [
            {"kind": "text", "tab": "任务概述", "text": "甲"},
            {"kind": "text", "tab": "任务概述", "text": "乙"},
            {"kind": "text", "tab": "任务过程", "text": "丙"},
        ]
        merged = generic_model._merge_consecutive(sections)
        self.assertEqual([s["tab"] for s in merged], ["任务概述", "任务过程"])
        self.assertEqual(merged[0]["text"], "甲\n\n乙")

    def test_non_adjacent_kept(self):
        sections = [
            {"kind": "text", "tab": "任务概述", "text": "甲"},
            {"kind": "table", "tab": "任务奖励", "tables": [{"rows": [["1"]]}]},
            {"kind": "text", "tab": "任务概述", "text": "乙"},
        ]
        merged = generic_model._merge_consecutive(sections)
        self.assertEqual(len(merged), 3)


class TestPrimaryImage(unittest.TestCase):
    """封面主图的取法：各频道把主图存在不同组件里。"""

    def build(self, key, fixture):
        return generic_model.build(CARD_DOMAIN if key == "domain" else CARD_NAMECARD,
                                   load_fixture(fixture), catalog_of(key))

    def test_item_icon(self):
        # 材料这类把图标放在物品块，icon 已是主图，不再重复写 image
        record = generic_model.build(CARD_MATERIAL, load_fixture("material"),
                                     catalog_of("material"))
        self.assertTrue(record["icon"].startswith("http"))
        self.assertNotIn("image", record)

    def test_info_panel_image(self):
        # 秘境的立绘在「秘境信息」面板里，物品块是空的
        record = self.build("domain", "domain")
        self.assertNotIn("icon", record)
        self.assertTrue(record["image"].startswith("http"))

    def test_namecard_prefers_card_face(self):
        # 名片有长图与卡面两张，封面取竖版卡面而不是横幅长图
        record = self.build("namecard", "namecard")
        gallery = record["sections"][0]
        card_face = next(i for i in gallery["items"] if i["tab"] == "卡面")
        self.assertEqual(record["image"], card_face["image"])

    def test_no_image(self):
        # 深境螺旋词条本身没有配图，不写 image，封面留空
        blocks = component_blocks.blocks_of(load_fixture("abyss"))
        self.assertIsNone(generic_model.primary_image(blocks))
        record = generic_model.build(CARD_ABYSS, load_fixture("abyss"),
                                     catalog_of("abyss"))
        self.assertNotIn("image", record)
        self.assertNotIn("icon", record)


class TestFilterConvert(unittest.TestCase):
    def test_star(self):
        self.assertEqual(generic_model._convert("五星", "star"), 5)
        self.assertEqual(generic_model._convert("一星", "star"), 1)
        self.assertEqual(generic_model._convert("3", "star"), 3)
        # 「无」这类非星级写法不写键
        self.assertIsNone(generic_model._convert("无", "star"))

    def test_bool(self):
        self.assertIs(generic_model._convert("是", "bool"), True)
        self.assertIs(generic_model._convert("否", "bool"), False)
        self.assertIs(generic_model._convert("有", "bool"), True)

    def test_passthrough(self):
        self.assertEqual(generic_model._convert("蒙德", None), "蒙德")


if __name__ == "__main__":
    unittest.main()
