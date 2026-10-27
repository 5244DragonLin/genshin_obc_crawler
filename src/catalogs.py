#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图鉴分类注册表。

一个分类 = 观测枢的一个频道（``channel``）。频道 id 来自站点首页的
「快捷导航」（频道 194）与「图鉴」树（频道 189），子频道单独成类。

两类建模器：

- **专用**：前六类图鉴（角色 / 武器 / 圣遗物 / 敌人 / 食物 / 书籍）信息量大、
  组件组合特殊，各有 :mod:`character_model` 等专用建模器；
- **通用**：其余频道正文都是同一套组件的不同组合，统一走
  :mod:`generic_model`，差异只在 ``filters`` —— 卡片上的筛选标签怎么映射成
  记录的字段。``filters`` 每项是::

      {"prefix": "星级", "key": "rarity", "many": False, "as": "star"}

  ``prefix`` 是标签前缀（标签形如 ``星级/五星``），``key`` 是产物键名，
  ``many`` 表示一格能挂多个同类标签（给数组），``as`` 是取值转换
  （``star`` 中文数字 → 星级，``bool`` 是 / 否 → 布尔）。
"""

import re

import artifact_model
import book_model
import character_model
import enemy_model
import food_model
import generic_model
import weapon_model

# 千星奇域 / 卡牌图鉴 / 影音回廊三个频道在站点上是「聚合频道」，
# 列表接口一次给全子频道的卡片，卡片 ``ext`` 里的 ``c_<子频道id>`` 指明来路。
THEATER_SUBCHANNELS = {
    267: "道具", 264: "衣装套装", 266: "衣装部件", 270: "妆容",
    268: "互动表情与动作", 265: "典藏模板",
}
CARD_SUBCHANNELS = {233: "角色牌", 234: "行动牌", 235: "魔物牌"}
MEDIA_SUBCHANNELS = {
    212: "角色视频", 84: "角色语音展示", 81: "过场动画", 238: "其他视频",
    254: "原神OST", 256: "千音雅集", 242: "WIKI编辑教程", 83: "手书&创作",
}

CATALOGS = [
    # ---------------- 专用建模 ----------------
    {"key": "character", "name": "角色图鉴", "channel": 25,
     "model": character_model, "md": True},
    {"key": "weapon", "name": "武器图鉴", "channel": 5,
     "model": weapon_model},
    {"key": "artifact", "name": "圣遗物图鉴", "channel": 218,
     "model": artifact_model},
    {"key": "enemy", "name": "敌人图鉴", "channel": 6,
     "model": enemy_model},
    {"key": "food", "name": "食物图鉴", "channel": 21,
     "model": food_model},
    {"key": "book", "name": "书籍图鉴", "channel": 68,
     "model": book_model},

    # ---------------- 通用建模：图鉴树 ----------------
    {"key": "ashen_eye", "name": "灰眸图鉴", "channel": 278,
     "generic": True,
     "filters": [{"prefix": "类型", "key": "types", "many": True}]},
    {"key": "organization", "name": "组织图鉴", "channel": 255,
     "generic": True,
     "filters": [{"prefix": "地区", "key": "regions", "many": True}]},
    {"key": "avatar", "name": "头像图鉴", "channel": 244,
     "generic": True,
     "filters": [{"prefix": "分类", "key": "category"}]},
    {"key": "material", "name": "材料图鉴", "channel": 13,
     "generic": True,
     "filters": [
         {"prefix": "道具类型", "key": "types", "many": True},
         {"prefix": "获取方式", "key": "sources", "many": True},
         {"prefix": "星级", "key": "rarity", "as": "star"},
     ]},
    {"key": "furnishing", "name": "家具图鉴", "channel": 130,
     "generic": True,
     "filters": [
         {"prefix": "区域", "key": "zones", "many": True},
         {"prefix": "类型", "key": "types", "many": True},
         {"prefix": "品质", "key": "rarity", "as": "star"},
         {"prefix": "摆设获取方式", "key": "sources", "many": True},
         {"prefix": "图纸获取方式", "key": "blueprint_sources", "many": True},
     ]},
    {"key": "domain", "name": "秘境图鉴", "channel": 54,
     "generic": True,
     "filters": [
         {"prefix": "秘境类型", "key": "types", "many": True},
         {"prefix": "推荐元素", "key": "elements", "many": True},
         {"prefix": "秘境消耗", "key": "cost"},
         {"prefix": "是否可联机", "key": "coop", "as": "bool"},
         {"prefix": "是否为任务本", "key": "quest_domain", "as": "bool"},
     ]},
    {"key": "npc", "name": "NPC与商店图鉴", "channel": 20,
     "generic": True,
     "filters": [
         {"prefix": "地区", "key": "regions", "many": True},
         {"prefix": "类型", "key": "types", "many": True},
         {"prefix": "特殊效果", "key": "specials", "many": True},
         {"prefix": "对话奖励", "key": "dialogue_reward", "as": "bool"},
         {"prefix": "牌手挑战", "key": "card_challenge", "as": "bool"},
     ]},
    {"key": "achievement", "name": "成就图鉴", "channel": 252,
     "generic": True,
     "filters": [
         {"prefix": "成就集", "key": "set"},
         {"prefix": "上线版本", "key": "version"},
         {"prefix": "每日委托成就", "key": "daily_commission", "as": "bool"},
         {"prefix": "隐藏成就", "key": "hidden", "as": "bool"},
     ]},
    {"key": "event", "name": "活动图鉴", "channel": 105,
     "generic": True,
     "filters": [
         {"prefix": "活动类型", "key": "types", "many": True},
         {"prefix": "版本", "key": "versions", "many": True},
     ]},
    {"key": "quest", "name": "任务图鉴", "channel": 43,
     "generic": True,
     "filters": [
         {"prefix": "任务类型", "key": "types", "many": True},
         {"prefix": "任务区域", "key": "regions", "many": True},
         {"prefix": "版本号", "key": "versions", "many": True},
     ]},
    {"key": "animal", "name": "动物图鉴", "channel": 49,
     "generic": True,
     "filters": [
         {"prefix": "动物类型", "key": "types", "many": True},
         {"prefix": "是否可捕获", "key": "catchable", "as": "bool"},
     ]},
    {"key": "abyss", "name": "深境螺旋图鉴", "channel": 65,
     "generic": True, "filters": []},
    {"key": "imaginarium", "name": "幻想真境剧诗图鉴", "channel": 249,
     "generic": True,
     "filters": [{"prefix": "类别", "key": "types", "many": True}]},
    {"key": "perilous", "name": "幽境危战图鉴", "channel": 275,
     "generic": True, "filters": []},
    {"key": "guild", "name": "冒险家协会图鉴", "channel": 55,
     "generic": True,
     "filters": [
         {"prefix": "委托类型", "key": "types", "many": True},
         {"prefix": "区域", "key": "regions", "many": True},
         {"prefix": "有无成就", "key": "has_achievement", "as": "bool"},
     ]},
    {"key": "namecard", "name": "名片图鉴", "channel": 109,
     "generic": True,
     "filters": [{"prefix": "名片类型", "key": "types", "many": True}]},
    {"key": "lore", "name": "考据图鉴", "channel": 62,
     "generic": True, "filters": []},

    # ---------------- 通用建模：聚合频道 ----------------
    # 「千星奇域」首页入口指到衣装套装，这里取父频道，一次收全部子频道，
    # 每条记录的 channel 标明来路（道具 / 衣装套装 / 妆容 …）
    {"key": "theater", "name": "千星奇域图鉴", "channel": 263,
     "generic": True, "subchannels": THEATER_SUBCHANNELS,
     "filters": [
         {"prefix": "类别", "key": "types", "many": True},
         {"prefix": "部位", "key": "parts", "many": True},
         {"prefix": "适用性别", "key": "gender"},
         {"prefix": "品阶", "key": "tier"},
         {"prefix": "色系", "key": "colors", "many": True},
         {"prefix": "获取方式", "key": "sources", "many": True},
         {"prefix": "形录获取方式", "key": "shape_sources", "many": True},
     ]},
    {"key": "card", "name": "卡牌图鉴", "channel": 231,
     "generic": True, "subchannels": CARD_SUBCHANNELS,
     "filters": [
         {"prefix": "类型", "key": "types", "many": True},
         {"prefix": "标签", "key": "tags", "many": True},
         {"prefix": "元素", "key": "elements", "many": True},
         {"prefix": "武器", "key": "weapon_types", "many": True},
         {"prefix": "阵营", "key": "factions", "many": True},
         {"prefix": "花费", "key": "cost"},
         {"prefix": "特殊模式", "key": "modes", "many": True},
     ]},
    # 「影音回廊」标题里的「预告」是正经片名（角色预告 PV），不能当未上线占位跳过
    {"key": "media", "name": "影音回廊图鉴", "channel": 80,
     "generic": True, "subchannels": MEDIA_SUBCHANNELS, "previews": False,
     "filters": [
         {"prefix": "类型", "key": "types", "many": True},
         {"prefix": "区域", "key": "regions", "many": True},
         {"prefix": "专辑", "key": "albums", "many": True},
         {"prefix": "乐曲分类", "key": "music_types", "many": True},
         {"prefix": "乐曲每分钟节拍数范围", "key": "bpm_range"},
         {"prefix": "所属国家", "key": "countries", "many": True},
     ]},
]

# ``--only`` / 配置里的分类别名
_ALIASES = {
    "character": "character", "角色": "character", "角色图鉴": "character",
    "weapon": "weapon", "武器": "weapon", "武器图鉴": "weapon",
    "artifact": "artifact", "圣遗物": "artifact", "圣遗物图鉴": "artifact",
    "enemy": "enemy", "敌人": "enemy", "敌人图鉴": "enemy", "魔物": "enemy",
    "敌人一览": "enemy",
    "food": "food", "食物": "food", "食物图鉴": "food", "食谱": "food",
    "食物一览": "food",
    "book": "book", "书籍": "book", "书籍图鉴": "book",

    "ashen_eye": "ashen_eye", "灰眸": "ashen_eye", "「灰眸」": "ashen_eye",
    "organization": "organization", "组织": "organization",
    "avatar": "avatar", "头像": "avatar", "头像图鉴": "avatar",
    "material": "material", "材料": "material", "材料图鉴": "material",
    "材料一览": "material", "背包": "material", "道具": "material",
    "furnishing": "furnishing", "家具": "furnishing", "家具一览": "furnishing",
    "家具图鉴": "furnishing", "摆设": "furnishing", "洞天": "furnishing",
    "domain": "domain", "秘境": "domain", "秘境图鉴": "domain",
    "npc": "npc", "npc与商店": "npc", "npc商店": "npc", "商店": "npc",
    "npc＆商店": "npc", "npc&商店": "npc",
    "achievement": "achievement", "成就": "achievement", "成就图鉴": "achievement",
    "event": "event", "活动": "event", "活动图鉴": "event",
    "quest": "quest", "任务": "quest", "任务图鉴": "quest",
    "animal": "animal", "动物": "animal", "动物图鉴": "animal",
    "abyss": "abyss", "深境螺旋": "abyss", "深渊": "abyss",
    "imaginarium": "imaginarium", "幻想真境剧诗": "imaginarium",
    "幻想真境": "imaginarium", "幻想真境剧诗图鉴": "imaginarium",
    "perilous": "perilous", "幽境危战": "perilous", "幽境": "perilous",
    "guild": "guild", "冒险家协会": "guild", "冒险家": "guild",
    "namecard": "namecard", "名片": "namecard", "名片图鉴": "namecard",
    "lore": "lore", "考据": "lore", "观测考据": "lore", "观测·考据": "lore",
    "theater": "theater", "千星奇域": "theater", "衣装": "theater",
    "card": "card", "卡牌": "card", "卡牌资料": "card", "卡牌图鉴": "card",
    "七圣召唤": "card",
    "media": "media", "影音回廊": "media", "影音": "media", "视频": "media",
}


def normalize_catalogs(only):
    """``--only`` 别名列表 → CATALOGS 子集；空列表 = 全部。

    写 ``全部`` / ``all`` / ``*`` 时忽略 ``catalogs`` 段的开关，导出全部 26 类。
    """
    if not only:
        return list(CATALOGS)
    wanted = []
    for token in only:
        for part in re.split(r"[,，\s]+", str(token)):
            if not part:
                continue
            part = part.lower().strip()
            if part in ("全部", "所有", "全量", "all", "*"):
                return list(CATALOGS)
            key = _ALIASES.get(part)
            if key is None:
                raise ValueError(f"未知分类：{part}")
            if key not in wanted:
                wanted.append(key)
    # 输出顺序固定为内置顺序，不跟随命令行顺序
    return [c for c in CATALOGS if c["key"] in wanted]
