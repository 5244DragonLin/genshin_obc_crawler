#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""圣遗物词条 → 语义化 JSON。

- ``rich_base_info`` —— 稀有度、获取途径、2 件套 / 4 件套效果
- ``artifact_list_v2`` —— 五个部位（生之花 / 死之羽 / 时之沙 / 空之杯 /
  理之冠）各一个组件：名称、描述、背景故事、部位图标
- ``multi_table``（模块「搭配推荐」）—— 方表，保留行列
"""

from model_utils import (find_components, first_component, rich_list, tables)
from richtext import clean_values

# 套装效果键归一：站点里「两件套效果 / 四件套效果」与「2件套效果 / 4件套效果」并存
_SET_KEY_NORMALIZE = {"两件套效果": "2件套效果", "四件套效果": "4件套效果",
                      "六件套效果": "6件套效果"}

PIECE_TITLES = ("生之花", "死之羽", "时之沙", "空之杯", "理之冠")


def _set_effects(info):
    """从「标签-值」表里抽套装效果，键名归一为「N件套效果」。"""
    out = {}
    for key in list(info):
        normalized = _SET_KEY_NORMALIZE.get(key, key)
        if normalized.endswith("件套效果") and normalized[:1].isdigit():
            out[normalized] = info.pop(key)
    return out


def _pieces(page):
    out = {}
    for data in find_components(page, "artifact_list_v2"):
        data = data or {}
        # 部位名优先取 title（「生之花：」），为空时退回 name.key
        title = str(data.get("title") or "").strip().rstrip("：:").strip()
        name_field = data.get("name")
        if isinstance(name_field, dict):
            if not title:
                title = str(name_field.get("key") or "").strip().rstrip("：:").strip()
            name = clean_values(name_field.get("value"))
        else:
            name = clean_values(name_field)
        if not title:
            continue
        desc = clean_values(data.get("desc"))
        story = clean_values(data.get("story"))
        piece = {}
        if name:
            piece["name"] = name
        if desc:
            piece["desc"] = desc
        if story:
            piece["story"] = story
        icon = str(data.get("icon_url") or "").strip()
        if icon:
            piece["icon"] = icon
        if piece:
            out[title] = piece
    return out


def build(card, page):
    from obc_api import ENTRY_URL, Client

    base = first_component(page, "rich_base_info") or {}
    info = rich_list(base)

    record = {
        "id": Client.card_id(card),
        "name": str((page or {}).get("name") or Client.card_name(card)).strip(),
        "url": ENTRY_URL.format(Client.card_id(card)),
    }
    summary = Client.card_summary(card)
    if summary:
        record["summary"] = summary
    icon = Client.card_icon(card)
    if icon:
        record["icon"] = icon

    if "稀有度" in info:
        record["rarity"] = info.pop("稀有度")
    set_effects = _set_effects(info)
    if set_effects:
        record["set_effects"] = set_effects
    if info:
        record["attrs"] = info

    pieces = _pieces(page)
    if pieces:
        record["pieces"] = pieces

    recommend = []
    for module_name, comp in ((str(m.get("name") or ""), c)
                              for m in (page.get("modules") or [])
                              for c in (m.get("components") or [])):
        if comp.get("component_id") == "multi_table" and module_name == "搭配推荐":
            recommend.extend(tables(comp.get("data") or {}))
    if recommend:
        record["recommend"] = recommend

    return {key: value for key, value in record.items() if value not in (None, [], {})}
