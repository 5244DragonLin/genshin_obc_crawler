#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图鉴建模测试：用 tests/fixtures/ 下的真实词条样本。

样本截取自观测枢接口的实际响应（角色 = 丝柯克、武器 = 苍耀、
圣遗物 = 影中沉凝的幻灭、敌人 = 丘林、食物 = 莫尔斯果酿、
书籍 = 至冬国通史），只保留建模用到的组件。
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import artifact_model
import book_model
import character_md
import character_model
import enemy_model
import food_model
import weapon_model

def load_fixture(name):
    with open(os.path.join(FIXTURES, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

CARD = {"content_id": 999, "title": "测试",
        "ext": '{"c_25":{"filter":{"text":"[\\"地区/纳塔\\",\\"星级/五星\\",\\"元素/冰\\",\\"武器/单手剑\\"]"}}}',
        "icon": "http://icon/test.png", "summary": "测试简介", "alias_name": ""}


def make_card(content_id, title, filters, channel, summary="", icon="http://icon/test.png"):
    """按频道拼一张分类卡片：``filters`` 是要挂的筛选标签。"""
    text = "[" + ",".join(f'\\"{tag}\\"' for tag in filters) + "]"
    ext = '{"c_%d":{"filter":{"text":"%s"}}}' % (channel, text)
    return {"content_id": content_id, "title": title, "summary": summary,
            "alias_name": "", "icon": icon, "ext": ext}


CARD_ENEMY = make_card(509331, "丘林",
                       ["类型/普通", "元素/风", "元素/冰", "攻击方式/混合"], 6,
                       summary="实习雕刻师但是武道大成")
CARD_FOOD = make_card(509950, "莫尔斯果酿",
                      ["食物类型/回复类", "食物星级/三星",
                       "食物获取方式/NPC购买", "是否产出特殊料理/是"], 21,
                      summary="莫尔斯果酿介绍\n沃雅妮莎特殊料理：鳞光咏叹调")
CARD_BOOK = make_card(509470, "至冬国通史",
                      ["书籍类型/学术作品", "获取方式/NPC购买"], 68,
                      summary="至冬国通史")


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
        # 默认只保留汉语语音
        self.assertEqual(list(self.record["voices"].keys()), ["汉语"])
        self.assertIn("初次见面…", [v["name"] for v in self.record["voices"]["汉语"]])
        self.assertIn("角色故事1", self.record["stories"])

    def test_voices_all_languages(self):
        page = load_fixture("character")
        record = character_model.build(CARD, page, voice_languages="all")
        self.assertEqual(set(record["voices"].keys()), {"汉语", "日语", "英语", "韩语"})

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


class TestEnemyModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = enemy_model.build(CARD_ENEMY, load_fixture("enemy"))

    def test_base(self):
        record = self.record
        self.assertEqual(record["name"], "丘林")
        self.assertEqual(record["type"], "普通")
        self.assertEqual(record["summary"], "实习雕刻师但是武道大成")
        self.assertTrue(record["url"].endswith("/509331/detail"))

    def test_multi_valued_filters(self):
        # 一个敌人可挂两种元素：卡片上的列表与正文里的「元素」写法顺序不同
        self.assertEqual(self.record["elements"], ["风", "冰"])
        self.assertEqual(self.record["attack_types"], ["混合"])
        self.assertEqual(self.record["basic"]["元素"], "冰、风")

    def test_skills(self):
        skills = self.record["skills"]
        self.assertEqual(len(skills), 6)
        self.assertEqual(skills[0]["name"], "风绻雪絮")
        self.assertTrue(skills[0]["image"].endswith(".gif"))

    def test_drops(self):
        drops = self.record["drops"]
        mora = next(item for item in drops if item["name"] == "摩拉")
        self.assertEqual(mora["count"], 100)
        self.assertEqual(mora["id"], "5565")
        self.assertTrue(mora["icon"].startswith("http"))

    def test_stats_with_notes(self):
        # 数据参考：属性里留 [1] 标记，脚注正文落在 notes
        stage = self.record["stats"][0]
        self.assertEqual(stage["tab"], "正常")
        self.assertIn("生命值", stage["attrs"])
        self.assertIn("[1]", stage["attrs"]["生命值"])
        self.assertIn("测算", stage["notes"]["1"])

    def test_guide_story_locations(self):
        self.assertIn("丘林", self.record["guide"])
        self.assertTrue(self.record["story"])
        location = self.record["locations"][0]
        self.assertEqual(location["tab"], "大世界")
        self.assertIn("路线说明", location["attrs"])
        self.assertTrue(location["images"])


class TestFoodModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = food_model.build(CARD_FOOD, load_fixture("food"))

    def test_base(self):
        record = self.record
        self.assertEqual(record["name"], "莫尔斯果酿")
        self.assertEqual(record["types"], ["回复类"])
        self.assertEqual(record["rarity"], 3)
        self.assertEqual(record["sources"], ["NPC购买"])
        self.assertTrue(record["special_dish"])

    def test_placeholder_summary_dropped(self):
        # 「<菜名>介绍」是站点的占位摘要，不收录；这条带着特殊料理说明则保留
        self.assertIn("特殊料理", self.record["summary"])
        plain = food_model.build(dict(CARD_FOOD, summary="莫尔斯果酿介绍"),
                                 load_fixture("food"))
        self.assertNotIn("summary", plain)

    def test_variants(self):
        variants = self.record["variants"]
        self.assertEqual([v["name"] for v in variants],
                         ["奇怪的莫尔斯果酿", "莫尔斯果酿", "美味的莫尔斯果酿", "鳞光咏叹调"])
        normal = variants[1]
        self.assertEqual(normal["rarity"], 3)
        self.assertIn("使用效果", normal["attrs"])
        self.assertTrue(normal["desc"])

    def test_ingredients(self):
        items = self.record["variants"][1]["ingredients"]
        self.assertEqual(len(items), 4)
        first = items[0]
        self.assertEqual(first["name"], "冰醋栗")
        self.assertEqual(first["count"], 3)
        self.assertTrue(first["id"])
        self.assertTrue(first["icon"].startswith("http"))


class TestBookModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = book_model.build(CARD_BOOK, load_fixture("book"))

    def test_base(self):
        record = self.record
        self.assertEqual(record["name"], "至冬国通史")
        self.assertEqual(record["types"], ["学术作品"])
        self.assertEqual(record["sources"], ["NPC购买"])

    def test_volumes(self):
        volumes = self.record["volumes"]
        self.assertEqual([v["title"] for v in volumes], ["第一卷", "第二卷"])
        self.assertEqual([v["name"] for v in volumes],
                         ["至冬国通史·卷一", "至冬国通史·卷二"])
        for volume in volumes:
            self.assertTrue(volume["content"])
            self.assertTrue(volume["desc"])


class TestVolumeOrder(unittest.TestCase):
    """卷名解析与配对规则（正文面板与卷信息块在站点里是分开排的）。"""

    def test_volume_no(self):
        self.assertEqual(book_model.volume_no("第一卷"), 11)
        self.assertEqual(book_model.volume_no("卷三"), 13)
        self.assertEqual(book_model.volume_no("其之二"), 12)
        self.assertEqual(book_model.volume_no("第零卷"), 10)
        self.assertEqual(book_model.volume_no("上本"), 1)
        self.assertEqual(book_model.volume_no("序"), 0)
        self.assertIsNone(book_model.volume_no("昆图尔的故事"))

    @staticmethod
    def _page(infos, panels):
        """拼一个只有卷信息块与全文面板的最小词条正文。"""
        modules = []
        for name in infos:
            modules.append({"name": "", "components": [
                {"component_id": "material_base_info",
                 "data": {"name": name, "star": 3, "attr": [{"key": "描述", "value": ["<p>简介</p>"]}]}}]})
        for name, text in panels:
            modules.append({"name": name, "components": [
                {"component_id": "collapse_panel", "data": {"rich_text": f"<p>{text}</p>"}}]})
        return {"name": "测试书", "modules": modules}

    def test_scrambled_volume_numbers(self):
        page = self._page(["书·卷一", "书·卷四", "书·卷二", "书·卷三"],
                          [("第一卷", "甲"), ("第三卷", "丙"), ("第四卷", "丁"), ("第二卷", "乙")])
        volumes = book_model._volumes(page)
        self.assertEqual([v["title"] for v in volumes], ["第一卷", "第二卷", "第三卷", "第四卷"])
        self.assertEqual([v["content"] for v in volumes], ["甲", "乙", "丙", "丁"])

    def test_panel_head_matches_book_tail(self):
        # 面板统一叫「书籍内容」，靠正文首行的「——石兽——」对上书名小节
        page = self._page(["合集·玉遁", "合集·石兽"],
                          [("书籍内容", "——石兽——"), ("书籍内容", "——玉遁——")])
        volumes = book_model._volumes(page)
        by_name = {v["name"]: v["content"] for v in volumes}
        self.assertEqual(by_name["合集·石兽"], "——石兽——")
        self.assertEqual(by_name["合集·玉遁"], "——玉遁——")

    def test_offset_numbering_falls_back_to_order(self):
        # 「序 + 卷一…」这类整体错位编号：卷序对不齐，退回出现顺序
        page = self._page(["书·序", "书·一"], [("第一卷", "开篇"), ("第二卷", "正文")])
        volumes = book_model._volumes(page)
        self.assertEqual([v["name"] for v in volumes], ["书·序", "书·一"])
        self.assertEqual(volumes[0]["content"], "开篇")

    def test_unmatched_panel_kept(self):
        # 多出来的全文不丢，单独成卷
        page = self._page(["书·卷一"], [("第一卷", "甲"), ("附录", "乙")])
        volumes = book_model._volumes(page)
        self.assertEqual([v["title"] for v in volumes], ["第一卷", "附录"])
        self.assertNotIn("name", volumes[1])


if __name__ == "__main__":
    unittest.main()
