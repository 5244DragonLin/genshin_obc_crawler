#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用图鉴建模：把 :mod:`component_blocks` 的区块拼成条目记录。

快捷导航里的频道（材料 / 家具 / 秘境 / 成就 / 名片 / 卡牌……）正文都是同一套
组件的不同组合，没必要每个频道写一个建模器。这个建模器做三件事：

1. **顶层字段**：``id`` / ``name`` / ``url`` / ``summary`` 固定，筛选标签按
   分类定义里的 ``filters`` 摊成英文键（一格能挂多个值的给数组）；
2. **按区块归位**：承载「条目本体」的那一块（图标、星级、名称）提到顶层，
   其余区块按站点顺序进 ``sections``，每块保留 ``kind`` 与 ``tab``（模块名）；
3. **相邻合并**：同一 ``tab`` + 同一 ``kind`` 的相邻区块合并，避免「任务概述」
   因站点重复挂载而在产物里出现三次。

各频道的差异只在「哪些标签映射到哪个键」，由 :mod:`catalogs` 声明，
建模器本身不写死任何频道。
"""

from component_blocks import blocks_of
from obc_api import ENTRY_URL, Client

# 中文数字星级 → int；「无」这类非星级写法落到 None
_CN_STAR = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}


def _convert(value, style):
    """筛选标签取值转换，见 :mod:`catalogs` 里 ``filters`` 的 ``as``。"""
    if style == "star":
        text = str(value or "").strip().rstrip("星")
        if text.isdigit():
            return int(text)
        return _CN_STAR.get(text)
    if style == "bool":
        return str(value or "").strip() in ("是", "有")
    return value


def _apply_filters(record, card, catalog):
    """按分类定义的 ``filters`` 把卡片筛选标签写进记录。"""
    for spec in catalog.get("filters") or ():
        prefix = spec.get("prefix")
        key = spec.get("key")
        if not prefix or not key:
            continue
        style = spec.get("as")
        if spec.get("many"):
            values = Client.card_filter_all(card, prefix)
            if style:
                values = [_convert(v, style) for v in values]
                values = [v for v in values if v is not None]
            if values:
                record[key] = values
            continue
        value = _convert(Client.card_filter(card, prefix), style)
        if value not in (None, ""):
            record[key] = value


def _merge_consecutive(sections):
    """同 ``kind`` + 同 ``tab`` 的相邻区块合并成一段。"""
    out = []
    for section in sections:
        last = out[-1] if out else None
        if (last is not None
                and last.get("kind") == section.get("kind")
                and last.get("tab") == section.get("tab")):
            for key, value in section.items():
                if key in ("kind", "tab"):
                    continue
                if key == "text":
                    last[key] = f"{last.get(key, '')}\n\n{value}".strip()
                elif key == "attrs":
                    last.setdefault(key, {}).update(value)
                elif isinstance(value, list):
                    last.setdefault(key, []).extend(value)
                elif key not in last:
                    last[key] = value
            continue
        out.append(dict(section))
    return out


def primary_image(blocks):
    """条目的主图，用作封面。

    站点把主图放在不同组件里，按以下顺序取第一张：

    1. 物品块的图标（材料 / 头像 / 家具 / 衣装等绝大多数频道）；
    2. 信息块的主图（秘境的立绘、家具的图标）；
    3. 图片陈列里名为「卡面」的那张（名片给出长图与卡面两张，
       长图是横幅，卡面才是竖图）；
    4. 图片陈列的第一张。
    """
    for block in blocks or ():
        if block.get("kind") == "item":
            image = block.get("icon") or block.get("image")
            if image:
                return image
    for block in blocks or ():
        if block.get("kind") == "info" and block.get("image"):
            return block["image"]
    galleries = [b for b in (blocks or ()) if b.get("kind") == "gallery"]
    for gallery in galleries:
        for item in gallery.get("items") or ():
            if "卡面" in str(item.get("tab") or ""):
                return item.get("image")
    for gallery in galleries:
        for item in gallery.get("items") or ():
            if item.get("image"):
                return item["image"]
    return None


def build(card, page, catalog=None):
    """单条词条 → 记录。

    ``catalog`` 是该频道的定义（见 :mod:`catalogs`）；不传时只出公共字段与
    正文区块。
    """
    catalog = catalog or {}
    entry_id = Client.card_id(card)
    title = Client.card_name(card)

    blocks = blocks_of(page)
    head = next((blk for blk in blocks if blk.get("kind") == "item"), None)
    body = [blk for blk in blocks if blk is not head]

    record = {
        "id": entry_id,
        "name": str((page or {}).get("name") or title).strip() or title,
        "url": ENTRY_URL.format(entry_id),
    }
    if record["name"] != title:
        record["card_name"] = title
    summary = Client.card_summary(card)
    if summary and summary != record["name"]:
        record["summary"] = summary

    _apply_filters(record, card, catalog)

    # 首个物品块承载条目本身：图标、星级、描述提到顶层，正文里不再重复
    if head is not None:
        for key in ("icon", "image", "rarity", "desc", "attrs", "note", "entries"):
            if key in head:
                record[key] = head[key]

    sections = _merge_consecutive(body)
    if sections:
        record["sections"] = sections
    # 秘境 / 名片这些频道的主图不在物品块里，补一个 image 给封面用；
    # 物品块已经给出 icon / image 时不重复写
    if not record.get("icon") and not record.get("image"):
        image = primary_image(blocks)
        if image:
            record["image"] = image
    return record
