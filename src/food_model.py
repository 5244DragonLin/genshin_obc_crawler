#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""食物词条 → 语义化 JSON。

一个词条 = 一道菜，正文里重复出现 ``material_base_info``，每次描述一个品级：
奇怪的 X / X / 美味的 X，另有角色特殊料理（名称与菜名无关，如「鳞光咏叹调」）。
每个品级给：

- ``name`` 品级名、``icon`` 成品图、``rarity`` 星级
- ``desc`` 描述；``attrs`` 里是原文的「使用效果 / 获得方式 / 食谱获得」
- ``ingredients`` 加工材料（名称、数量、材料词条 id、图标）

菜系、星级、获取方式取分类卡片上的筛选标签：一道菜可能同时属于两类
（如既是「攻击类」又是「暴击类」），所以 ``types`` / ``sources`` 是列表。
"""

from model_utils import base_attrs, collapse_panels, find_components
from richtext import extract_entries

# 「食物星级/四星」里的中文数字
_CN_STAR = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}


def _rarity(text):
    """「四星」→ 4；「其他」这类认不出的写法返回 None，不写该键。"""
    text = str(text or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return _CN_STAR.get(text.rstrip("星"))


def _ingredients(data):
    """加工材料：``materials`` 的富文本里包着带数量的材料词条。"""
    value = (data.get("materials") or {}).get("value")
    html = "\n".join(value) if isinstance(value, list) else str(value or "")
    out = []
    for item in extract_entries(html):
        entry = {}
        if item.get("name"):
            entry["name"] = item["name"]
        if item.get("count") is not None:
            entry["count"] = item["count"]
        if item.get("id"):
            entry["id"] = item["id"]
        if item.get("img"):
            entry["icon"] = item["img"]
        if entry:
            out.append(entry)
    return out


def _variants(page):
    """全部品级，按词条里的出现顺序（奇怪 / 普通 / 美味 / 特殊料理）。"""
    out = []
    for data in find_components(page, "material_base_info"):
        attrs = base_attrs(data)
        desc = attrs.pop("描述", "")

        variant = {}
        name = str(data.get("name") or "").strip()
        if name:
            variant["name"] = name
        if desc:
            variant["desc"] = desc
        if isinstance(data.get("star"), int):
            variant["rarity"] = data["star"]
        icon = str(data.get("img") or "").strip()
        if icon:
            variant["icon"] = icon
        if attrs:
            variant["attrs"] = attrs
        ingredients = _ingredients(data)
        if ingredients:
            variant["ingredients"] = ingredients
        if variant:
            out.append(variant)
    return out


def _extra(page):
    """折叠面板里的补充说明（食谱故事、活动说明等），多数词条没有。"""
    out = []
    for panel in collapse_panels(page):
        if not panel["text"]:
            continue
        entry = {}
        if panel["name"]:
            entry["name"] = panel["name"]
        entry["text"] = panel["text"]
        out.append(entry)
    return out


def build(card, page):
    from obc_api import ENTRY_URL, Client

    record = {
        "id": Client.card_id(card),
        "name": str((page or {}).get("name") or Client.card_name(card)).strip(),
        "url": ENTRY_URL.format(Client.card_id(card)),
    }
    if record["name"] != Client.card_name(card):
        record["card_name"] = Client.card_name(card)

    # 食物卡片的摘要统一写成「<菜名>介绍」，纯占位，不带信息量，不收录
    summary = Client.card_summary(card)
    if summary and summary != f"{record['name']}介绍":
        record["summary"] = summary

    types = Client.card_filter_all(card, "食物类型")
    if types:
        record["types"] = types
    rarity = _rarity(Client.card_filter(card, "食物星级"))
    if rarity:
        record["rarity"] = rarity
    sources = Client.card_filter_all(card, "食物获取方式")
    if sources:
        record["sources"] = sources
    special = Client.card_filter(card, "是否产出特殊料理")
    if special:
        record["special_dish"] = special == "是"

    icon = Client.card_icon(card)
    if icon:
        record["icon"] = icon

    variants = _variants(page)
    if variants:
        record["variants"] = variants
    extra = _extra(page)
    if extra:
        record["extra"] = extra

    return {key: value for key, value in record.items() if value not in (None, [], {})}
