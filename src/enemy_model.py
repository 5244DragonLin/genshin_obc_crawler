#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""敌人词条 → 语义化 JSON。

词条组件（component_id）与取值：

- ``monster_base_info`` —— 「标签-值」基础信息（元素 / 攻击方式 / 所在区域）、
  招式动图（``list``，每项一招）、掉落物（``feedback``，与材料条目同形）
- ``collapse_panel``（模块「攻略方法」）—— 打法长文
- ``good_desc``（模块「背景故事」）—— 背景故事
- ``equipment_growth_info``（模块「数据参考」）—— 按战役或等级分档的生命值、
  相对生命值、抗性；原文里的 ``[1]`` 脚注落到 ``notes`` 里
- ``timeline_base_info``（模块「位置导览」）—— 分页签的路线说明与配图
- ``map_desc`` —— 少数词条另挂的展示图

类型 / 元素 / 攻击方式取分类卡片上的筛选标签。一个敌人常挂两种元素
（如「冰、风」），所以 ``elements`` 与 ``attack_types`` 是列表。
"""

from model_utils import base_attrs, collapse_panels, find_components, first_component, materials
from richtext import extract_images, extract_notes, html_to_text


def _skills(data):
    """招式：``list`` 里每项是「招式名 + 动图」。"""
    out = []
    for item in (data or {}).get("list") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("tab_name") or "").strip()
        image = str(item.get("image") or "").strip()
        if name and image:
            out.append({"name": name, "image": image})
    return out


def _notes(item):
    """该档位属性里的脚注，``{编号: 注释正文}``；正文里的 ``[1]`` 由此对上。"""
    out = {}
    for attr in (item or {}).get("attr") or []:
        for chunk in attr.get("value") or []:
            if not isinstance(chunk, str):
                continue
            for number, text in extract_notes(chunk).items():
                out.setdefault(number, text)
    return out


def _stats(page):
    """数据参考：每个战役 / 等级档位一条，属性键为原文行标题。"""
    out = []
    for data in find_components(page, "equipment_growth_info"):
        for item in data.get("list") or []:
            if not isinstance(item, dict):
                continue
            attrs = base_attrs(item)
            notes = _notes(item)
            if not attrs and not notes:
                continue
            entry = {}
            tab = str(item.get("tab_name") or "").strip()
            if tab:
                entry["tab"] = tab
            if attrs:
                entry["attrs"] = attrs
            if notes:
                entry["notes"] = notes
            out.append(entry)
    return out


def _locations(page):
    """位置导览：页签（如「大世界」）+ 路线说明 + 说明里嵌的配图。"""
    out = []
    for data in find_components(page, "timeline_base_info"):
        for item in data.get("list") or []:
            if not isinstance(item, dict):
                continue
            attrs = base_attrs(item)
            images = []
            for attr in item.get("attr") or []:
                for chunk in attr.get("value") or []:
                    if isinstance(chunk, str):
                        images.extend(extract_images(chunk))
            if not attrs and not images:
                continue
            entry = {}
            tab = str(item.get("tab_name") or "").strip()
            if tab:
                entry["tab"] = tab
            if attrs:
                entry["attrs"] = attrs
            images = list(dict.fromkeys(images))
            if images:
                entry["images"] = images
            out.append(entry)
    return out


def _guide(page):
    """攻略方法：折叠面板里的打法长文，多段时按顺序拼接。"""
    texts = [panel["text"] for panel in collapse_panels(page, "攻略方法") if panel["text"]]
    return "\n\n".join(texts)


def _story(page):
    """背景故事：``good_desc`` 的富文本正文（``attr`` 部分为空，忽略）。"""
    component = first_component(page, "good_desc") or {}
    return html_to_text(component.get("rich_text") or "").strip()


def _galleries(page):
    out = []
    for data in find_components(page, "map_desc"):
        for item in data.get("list") or []:
            name = str((item or {}).get("tab_name") or "").strip()
            image = str((item or {}).get("image") or "").strip()
            if name and image:
                out.append({"name": name, "image": image})
    return out


def build(card, page):
    from obc_api import ENTRY_URL, Client

    base = first_component(page, "monster_base_info") or {}

    record = {
        "id": Client.card_id(card),
        "name": str((page or {}).get("name") or Client.card_name(card)).strip(),
        "url": ENTRY_URL.format(Client.card_id(card)),
    }
    if record["name"] != Client.card_name(card):
        record["card_name"] = Client.card_name(card)
    summary = Client.card_summary(card)
    if summary:
        record["summary"] = summary

    kind = Client.card_filter(card, "类型")
    if kind:
        record["type"] = kind
    elements = Client.card_filter_all(card, "元素")
    if elements:
        record["elements"] = elements
    attacks = Client.card_filter_all(card, "攻击方式")
    if attacks:
        record["attack_types"] = attacks

    icon = Client.card_icon(card) or str(base.get("image") or "").strip()
    if icon:
        record["icon"] = icon

    attrs = base_attrs(base)
    if attrs:
        record["basic"] = attrs

    skills = _skills(base)
    if skills:
        record["skills"] = skills
    drops = materials(base, "feedback")
    if drops:
        record["drops"] = drops

    guide = _guide(page)
    if guide:
        record["guide"] = guide
    story = _story(page)
    if story:
        record["story"] = story

    stats = _stats(page)
    if stats:
        record["stats"] = stats
    locations = _locations(page)
    if locations:
        record["locations"] = locations
    galleries = _galleries(page)
    if galleries:
        record["galleries"] = galleries

    return {key: value for key, value in record.items() if value not in (None, [], {})}
