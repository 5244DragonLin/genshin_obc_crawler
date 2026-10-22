#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""武器词条 → 语义化 JSON。

- ``equipment_base_info`` —— 类别（单手剑 / 法器…）、星级、图片
- ``good_desc`` —— 技能说明与背景文案：``rich_text`` 以 ``<hr>`` 分隔，
  前半是「精炼阶 + 技能名 + 效果」，后半是武器描述；``attr`` 是
  「获取途径」等标签
- ``equipment_growth_info`` —— 按突破档位给出初始数值、每级成长与材料
- ``multi_table``（模块「推荐角色」）—— 方表，保留行列
- ``map_desc`` —— 武器外观展示图
"""

from model_utils import (base_attrs, find_components, first_component,
                         materials, tables)
from richtext import html_to_text


def _split_skill(rich_text):
    """good_desc 正文按 ``<hr>`` 分成「技能」与「描述」两半。"""
    parts = str(rich_text or "").split("<hr")
    skill_html = parts[0]
    flavor_html = parts[1] if len(parts) > 1 else ""
    return (html_to_text(skill_html).strip(),
            html_to_text(flavor_html).strip())


def _parse_skill(skill_text):
    """技能段落首行是精炼阶说明，紧随其后的首行是技能名。"""
    lines = [line.strip() for line in skill_text.split("\n") if line.strip()]
    info = {}
    if lines and "精炼" in lines[0]:
        info["refinement"] = lines.pop(0)
    if lines:
        info["name"] = lines.pop(0)
    if lines:
        info["desc"] = "\n".join(lines)
    return info


def build(card, page):
    from obc_api import ENTRY_URL, Client

    base = first_component(page, "equipment_base_info") or {}
    desc_component = first_component(page, "good_desc") or {}
    skill_text, flavor_text = _split_skill(desc_component.get("rich_text") or "")

    record = {
        "id": Client.card_id(card),
        "name": str(base.get("name") or Client.card_name(card)).strip(),
        "type": str(base.get("category") or "").strip() or None,
        "url": ENTRY_URL.format(Client.card_id(card)),
    }
    if isinstance(base.get("star"), int):
        record["rarity"] = base["star"]
    else:
        star = Client.card_filter(card, "星级")
        if star:
            record["rarity"] = int(star) if star.isdigit() else star
    icon = Client.card_icon(card) or str(base.get("image") or "").strip()
    if icon:
        record["icon"] = icon

    skill = _parse_skill(skill_text)
    if skill:
        record["skill"] = skill
    if flavor_text:
        record["desc"] = flavor_text

    attrs = base_attrs(desc_component)
    if attrs:
        record["attrs"] = attrs

    growth, ascension = [], []
    for data in find_components(page, "equipment_growth_info"):
        for item in data.get("list") or []:
            if not isinstance(item, dict):
                continue
            entry = {"level": str(item.get("tab_name") or "").strip() or None}
            attrs_at_level = base_attrs(item)
            if attrs_at_level:
                entry["attrs"] = attrs_at_level
            mats = materials(item)
            if mats:
                entry["materials"] = mats
            growth.append(entry)
    if growth:
        record["growth"] = growth

    recommend = []
    for module_name, comp in _iter_modules(page):
        if comp.get("component_id") == "multi_table" and module_name == "推荐角色":
            recommend.extend(tables(comp.get("data") or {}))
    if recommend:
        record["recommend"] = recommend

    displays = []
    for data in find_components(page, "map_desc"):
        for item in data.get("list") or []:
            name = str((item or {}).get("tab_name") or "").strip()
            image = str((item or {}).get("image") or "").strip()
            if name and image:
                displays.append({"name": name, "image": image})
    if displays:
        record["displays"] = displays

    record = {key: value for key, value in record.items() if value not in (None, [], {})}
    return record


def _iter_modules(page):
    for module in (page or {}).get("modules") or []:
        for comp in module.get("components") or []:
            yield str(module.get("name") or ""), comp
