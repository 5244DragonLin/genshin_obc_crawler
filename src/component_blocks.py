#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""词条正文组件 → 通用区块。

观测枢词条正文是 ``modules → components`` 两级结构，组件的 ``component_id``
跨频道复用且稳定：``material_base_info`` 是「图标 + 名称 + 星级 + 属性 +
制作材料」，``collapse_panel`` 是折叠长文，``multi_table`` 是表格，
``map_desc`` 是图片陈列……

前六类图鉴（角色 / 武器 / 圣遗物 / 敌人 / 食物 / 书籍）的信息取向各不同，
各有专用建模器；快捷导航里其余频道都是同一套组件的不同组合，统一由本模块
把每个组件转成一块带 ``kind`` 的区块，再由 :mod:`generic_model` 拼成记录。

区块的 ``kind`` 与载荷：

===============  =========================================================
``item``         单条物品：``name`` / ``rarity`` / ``icon`` / ``desc`` /
                 ``attrs`` / ``note``（材料栏的标签与值）/ ``entries``
``text``         长文：``text`` / ``images`` / ``videos``
``table``        表格：``tables``（``tab`` / ``header`` / ``rows``）/
                 ``options``（筛选表的字段取值）/ ``images``
``gallery``      图片陈列：``items``（``tab`` / ``image``）
``info``         「标签-值」面板：``attrs`` / ``image`` / ``rarity`` /
                 ``life`` / ``energy`` / ``gold_image`` /
                 ``skills`` / ``drops``
``skills``       卡牌技能：``items``（``name`` / ``type`` / ``icon`` /
                 ``life`` / ``energy`` / ``desc``）
``timeline``     分条事件：``items``（``tab`` / ``attrs`` / ``images``）
``levels``       分档数值：``items``（``tab`` / ``attrs`` / ``notes``）或
                 深境螺旋的 ``target`` / ``desc`` / ``first_half`` /
                 ``second_half``
``dialogue``     对话树：``lines``（``option`` / ``text`` / ``icon``）
``voice``        语音展示：``languages``（语言 → 台词列表）
``links``        站内攻略 / 条目链接：``items``（``name`` / ``cover`` /
                 ``link``）
===============  =========================================================
"""

import re

from model_utils import (base_attrs, materials, rich_list, table, tables)
from richtext import (clean_html, clean_values, extract_entries, extract_images,
                      extract_notes, html_to_text)

# 视频组件：``data-video-url`` 与 ``data-video-poster`` 同在一个 span 上
_VIDEO_URL_RE = re.compile(r'data-video-url="([^"]+)"')
_VIDEO_POSTER_RE = re.compile(r'data-video-poster="([^"]*)"')


def _clean(text):
    return str(text or "").strip()


def _put(block, key, value):
    """只有非空值才写键：产物里不留 ``null`` 与空容器。"""
    if value not in (None, "", [], {}):
        block[key] = value


def videos_of(html):
    """正文里的本地视频：``[{url, poster?}]``，按出现顺序去重。"""
    html = str(html or "")
    urls = _VIDEO_URL_RE.findall(html)
    posters = _VIDEO_POSTER_RE.findall(html)
    out, seen = [], set()
    for index, url in enumerate(urls):
        if url in seen:
            continue
        seen.add(url)
        item = {"url": url}
        if index < len(posters) and posters[index]:
            item["poster"] = posters[index]
        out.append(item)
    return out


def _walk_strings(value):
    """递归取出字段里的全部字符串，用来在表格里捞图标。"""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)


def _images_in(value):
    out, seen = [], set()
    for chunk in _walk_strings(value):
        for url in extract_images(chunk):
            if url not in seen:
                seen.add(url)
                out.append(url)
    return out


# ----------------------------------------------------------------------
# 各 component_id 的转区块规则
# ----------------------------------------------------------------------
def _material_item(tab, data):
    """``material_base_info``：图标 + 名称 + 星级 + 属性 + 材料栏。

    材料栏（``materials``）是一个「标签-值」对，不同频道写法不同：
    家具是「制作材料」，头像写「预估获取时长」，成就是「名片纹饰」，
    衣装写「缤纷评分」。标签与值原样保留，值里引用的词条单列到 ``entries``。
    """
    attrs = base_attrs(data)
    desc = attrs.pop("描述", "")
    block = {"kind": "item"}
    _put(block, "tab", _clean(tab))
    _put(block, "name", _clean(data.get("name")))
    if isinstance(data.get("star"), int) and data["star"] > 0:
        block["rarity"] = data["star"]
    _put(block, "icon", _clean(data.get("img")))
    _put(block, "desc", desc)
    _put(block, "attrs", attrs)

    raw = data.get("materials")
    if isinstance(raw, dict):
        value = raw.get("value")
        note = {"label": _clean(raw.get("key"))}
        _put(note, "text", clean_values(value))
        html = "\n".join(value) if isinstance(value, list) else str(value or "")
        entries = _entries(html)
        _put(note, "entries", entries)
        if note.get("label") or note.get("text") or entries:
            block["note"] = note
    return block


def _entries(html):
    """富文本里引用的词条 → ``[{name, count?, id?, icon?}]``。"""
    out = []
    for item in extract_entries(html):
        entry = {}
        _put(entry, "name", item.get("name"))
        _put(entry, "count", item.get("count"))
        _put(entry, "id", item.get("id"))
        _put(entry, "icon", item.get("img"))
        if entry:
            out.append(entry)
    return out


def _collapse_text(tab, data):
    """``collapse_panel``：折叠长文，可能带图与本地视频。"""
    html = data.get("rich_text") or ""
    cleaned = clean_html(html)
    block = {"kind": "text"}
    _put(block, "tab", _clean(tab))
    _put(block, "text", cleaned["text"].strip())
    _put(block, "images", cleaned["images"])
    _put(block, "videos", videos_of(html))
    return block if len(block) > 1 else None


def _multi_table(tab, data):
    """``multi_table``：一张或多张表，单元格只留纯文本，图标单列。"""
    block = {"kind": "table"}
    _put(block, "tab", _clean(tab))
    _put(block, "tables", tables(data))
    _put(block, "images", _images_in(data))
    return block if block.get("tables") or block.get("images") else None


def _filter_table(tab, data):
    """``filter_table``：带字段说明的表（原神 OST 的曲目表）。"""
    block = {"kind": "table"}
    _put(block, "tab", _clean(tab))
    restored = table(data.get("table") or {})
    _put(block, "tables", [restored] if restored else [])
    options = []
    for item in data.get("options") or []:
        if not isinstance(item, dict):
            continue
        entry = {}
        _put(entry, "key", _clean(item.get("key")))
        values = item.get("value")
        _put(entry, "value", [str(v).strip() for v in values if str(v).strip()]
             if isinstance(values, list) else [_clean(values)])
        if entry:
            options.append(entry)
    _put(block, "options", options)
    _put(block, "images", _images_in(data.get("table") or {}))
    return block if block.get("tables") or block.get("options") else None


def _map_desc(tab, data):
    """``map_desc``：图片陈列（展示图、位置图、谱面图）。"""
    items = []
    for item in (data or {}).get("list") or []:
        if not isinstance(item, dict):
            continue
        image = _clean(item.get("image"))
        if not image:
            continue
        entry = {}
        _put(entry, "tab", _clean(item.get("tab_name")))
        entry["image"] = image
        items.append(entry)
    if not items:
        return None
    block = {"kind": "gallery"}
    _put(block, "tab", _clean(tab))
    block["items"] = items
    return block


def _kv_panel(tab, data):
    """「标签-值」面板：``rich_base_info`` / ``base_info`` / ``npc_base_info`` 等。"""
    attrs = rich_list(data) or base_attrs(data)
    merged = dict(attrs)
    # npc_base_info / 千音雅集把补充信息放在 extra_attr 里，形态同「标签-值」
    merged.update(base_attrs({"attr": (data or {}).get("extra_attr") or []}))
    block = {"kind": "info"}
    _put(block, "tab", _clean(tab))
    _put(block, "attrs", merged)
    return block if merged else None


def _role_panel(tab, data):
    """``role_base_info``：秘境详情面板（名称 + 星级色 + 立绘 + 属性）。"""
    block = _kv_panel(tab, data) or {"kind": "info"}
    _put(block, "name", _clean(data.get("name")))
    if isinstance(data.get("star"), int) and data["star"] > 0:
        block["rarity"] = data["star"]
    _put(block, "image", _clean(data.get("avatar_pc") or data.get("avatar_m")))
    return block if len(block) > 1 else None


def _cave_panel(tab, data):
    """``cave_base_info``：家具基础信息（名称 / 图标 / 品质 / 制作材料）。"""
    block = {"kind": "info"}
    _put(block, "tab", _clean(tab))
    _put(block, "name", _clean(data.get("name")))
    if isinstance(data.get("rate"), int) and data["rate"] > 0:
        block["rarity"] = data["rate"]
    _put(block, "image", _clean(data.get("image")))
    raw = data.get("materials")
    html = "\n".join(raw) if isinstance(raw, list) else str(raw or "")
    _put(block, "entries", _entries(html))
    return block if len(block) > 1 else None


def _card_panel(tab, data):
    """``card_base_info``：七圣召唤卡面（生命 / 充能 / 属性 / 立绘）。"""
    block = _kv_panel(tab, data) or {"kind": "info"}
    _put(block, "name", _clean(data.get("name")))
    _put(block, "image", _clean(data.get("common_img")))
    _put(block, "gold_image", _clean(data.get("gold_img")))
    for key, field in (("life", "life"), ("energy", "energy")):
        if isinstance(data.get(field), int) and data[field]:
            block[key] = data[field]
    return block if len(block) > 1 else None


def _card_skills(tab, data):
    """``card_skill``：卡牌技能，每项带图标、生命 / 充能与效果说明。"""
    items = []
    for item in (data or {}).get("list") or []:
        if not isinstance(item, dict):
            continue
        entry = {}
        name = _clean(item.get("tab_name"))
        # 站点给未填写的技能留一张空卡片，tab_name 全是「默认标题」，不算内容
        if name and name != "默认标题":
            entry["name"] = name
        _put(entry, "type", _clean(item.get("skill_type")))
        _put(entry, "icon", _clean(item.get("icon")))
        for key in ("life", "energy"):
            if isinstance(item.get(key), int) and item[key]:
                entry[key] = item[key]
        _put(entry, "desc", clean_values(item.get("desc")))
        if entry:
            items.append(entry)
    if not items:
        return None
    block = {"kind": "skills"}
    _put(block, "tab", _clean(tab))
    block["items"] = items
    return block


def _monster_panel(tab, data):
    """``monster_base_info``：敌人 / 动物基础信息，含招式图与掉落物。"""
    block = _kv_panel(tab, data) or {"kind": "info"}
    _put(block, "icon", _clean(data.get("image")))
    skills = []
    for item in (data or {}).get("list") or []:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("tab_name"))
        image = _clean(item.get("image"))
        if name and image:
            skills.append({"name": name, "image": image})
    _put(block, "skills", skills)
    _put(block, "drops", materials(data, "feedback"))
    return block if len(block) > 1 else None


def _business_card(tab, data):
    """``business_card``：名片长图与卡面图。"""
    items = []
    for name, field in (("长图", "long_img"), ("卡面", "card_img")):
        image = _clean((data or {}).get(field))
        if image:
            items.append({"tab": name, "image": image})
    if not items:
        return None
    block = {"kind": "gallery"}
    _put(block, "tab", _clean(tab))
    block["items"] = items
    return block


def _timeline(tab, data):
    """``timeline_base_info``：分条事件（组织的重要事件）。"""
    items = []
    for item in (data or {}).get("list") or []:
        if not isinstance(item, dict):
            continue
        entry = {}
        _put(entry, "tab", _clean(item.get("tab_name")))
        _put(entry, "attrs", base_attrs(item))
        _put(entry, "images", _images_in(item.get("attr")))
        if entry:
            items.append(entry)
    if not items:
        return None
    block = {"kind": "timeline"}
    _put(block, "tab", _clean(tab))
    block["items"] = items
    return block


def _levels(tab, data):
    """``equipment_growth_info``：分档数值（幽境危战的挑战说明）。"""
    items = []
    for item in (data or {}).get("list") or []:
        if not isinstance(item, dict):
            continue
        entry = {}
        _put(entry, "tab", _clean(item.get("tab_name")))
        _put(entry, "attrs", base_attrs(item))
        _put(entry, "materials", materials(item))
        notes = {}
        for chunk in _walk_strings(item.get("attr")):
            for number, text in extract_notes(chunk).items():
                notes.setdefault(number, text)
        _put(entry, "notes", notes)
        _put(entry, "images", _images_in(item.get("attr")))
        if entry:
            items.append(entry)
    if not items:
        return None
    block = {"kind": "levels"}
    _put(block, "tab", _clean(tab))
    block["items"] = items
    return block


def _abyss_levels(tab, data):
    """``spiral_abyss_target``：深境螺旋每层的目标与上下半敌人。"""
    items = []
    for item in (data or {}).get("list") or []:
        if not isinstance(item, dict):
            continue
        entry = {}
        _put(entry, "tab", _clean(item.get("level")))
        _put(entry, "target", _clean(item.get("target")))
        _put(entry, "desc", _clean(item.get("desc")))
        for key, field in (("first_half", "first_half"), ("second_half", "second_half")):
            rounds = []
            for wave in ((item.get(field) or {}).get("list") or []):
                if not isinstance(wave, dict):
                    continue
                info = {}
                _put(info, "tab", _clean(wave.get("name")))
                _put(info, "entries", _entries_of(wave.get("entry_pages")))
                if info:
                    rounds.append(info)
            _put(entry, key, rounds)
        if entry:
            items.append(entry)
    if not items:
        return None
    block = {"kind": "levels"}
    _put(block, "tab", _clean(tab))
    block["items"] = items
    return block


def _entries_of(raw_items):
    """``entry_pages`` 这类条目数组 → ``[{name, count, id, icon}]``。"""
    out = []
    for item in raw_items or []:
        if not isinstance(item, dict):
            continue
        entry = {}
        _put(entry, "name", _clean(item.get("nickname")))
        _put(entry, "count", item.get("amount"))
        _put(entry, "id", _clean(item.get("ep_id")))
        _put(entry, "icon", _clean(item.get("img")))
        if entry:
            out.append(entry)
    return out


def _dialogue(tab, data):
    """``interactive_dialogue``：对话树按根节点深度优先摊平成台词序列。"""
    lines = []
    for branch in (data or {}).get("list") or []:
        if not isinstance(branch, dict):
            continue
        contents = branch.get("contents") or {}
        children = branch.get("child_ids") or {}
        if not isinstance(contents, dict):
            contents = {}
        if not isinstance(children, dict):
            children = {}
        seen = set()

        def walk(node_id, depth=0):
            node_id = str(node_id or "")
            if not node_id or node_id in seen or depth > 200:
                return
            seen.add(node_id)
            node = contents.get(node_id) or {}
            if not isinstance(node, dict):
                node = {}
            option = html_to_text(node.get("option") or "").strip()
            text = html_to_text(node.get("dialogue") or "").strip()
            icon = _clean(node.get("icon"))
            if option or text:
                line = {}
                _put(line, "option", option)
                _put(line, "text", text)
                _put(line, "icon", icon)
                lines.append(line)
            for child in children.get(node_id) or []:
                walk(child, depth + 1)

        root = branch.get("root_id")
        if root:
            walk(root)
        else:
            for node_id in contents:
                walk(node_id)
    if not lines:
        return None
    block = {"kind": "dialogue"}
    _put(block, "tab", _clean(tab))
    block["lines"] = lines
    return block


def _voice(tab, data):
    """``role_voice``：按语言的语音台词与音频地址。"""
    languages = {}
    for group in (data or {}).get("list") or []:
        if not isinstance(group, dict):
            continue
        language = _clean(group.get("tab_name"))
        rows = []
        for item in group.get("table") or []:
            if not isinstance(item, dict):
                continue
            entry = {}
            _put(entry, "name", _clean(item.get("name")))
            _put(entry, "text", _clean(item.get("content")))
            _put(entry, "audio", _clean(item.get("audio_url")))
            if entry:
                rows.append(entry)
        if language and rows:
            languages[language] = rows
    if not languages:
        return None
    block = {"kind": "voice"}
    _put(block, "tab", _clean(tab))
    block["languages"] = languages
    return block


def _strategy(tab, data):
    """``strategy``：站内攻略推荐链接。"""
    items = []
    for item in (data or {}).get("list") or []:
        if not isinstance(item, dict):
            continue
        link = _clean(item.get("link"))
        name = _clean(item.get("tab_name"))
        if not link and not name:
            continue
        entry = {}
        _put(entry, "name", name)
        _put(entry, "cover", _clean(item.get("cover")))
        _put(entry, "link", link)
        items.append(entry)
    if not items:
        return None
    block = {"kind": "links"}
    _put(block, "tab", _clean(tab))
    block["items"] = items
    return block


_HANDLERS = {
    "material_base_info": _material_item,
    "collapse_panel": _collapse_text,
    "multi_table": _multi_table,
    "filter_table": _filter_table,
    "map_desc": _map_desc,
    "rich_base_info": _kv_panel,
    "base_info": _kv_panel,
    "npc_base_info": _kv_panel,
    "role_base_info": _role_panel,
    "cave_base_info": _cave_panel,
    "card_base_info": _card_panel,
    "card_skill": _card_skills,
    "monster_base_info": _monster_panel,
    "business_card": _business_card,
    "timeline_base_info": _timeline,
    "equipment_growth_info": _levels,
    "spiral_abyss_target": _abyss_levels,
    "interactive_dialogue": _dialogue,
    "role_voice": _voice,
    "strategy": _strategy,
}

# 已知但正文用不到内容的组件（空卡片分组等），静默跳过
_IGNORED = {"card_group_info"}


def supports(component_id):
    return component_id in _HANDLERS


def block(module_name, component_id, data):
    """一个组件 → 一块内容；不产出内容的返回 None。"""
    handler = _HANDLERS.get(component_id)
    if handler is None:
        return None
    if not isinstance(data, dict):
        return None
    return handler(module_name, data)


def blocks_of(page):
    """整篇词条正文 → 按出现顺序的区块列表。"""
    out = []
    for module in (page or {}).get("modules") or []:
        if not isinstance(module, dict):
            continue
        module_name = _clean(module.get("name"))
        for comp in module.get("components") or []:
            if not isinstance(comp, dict):
                continue
            piece = block(module_name, comp.get("component_id"), comp.get("data"))
            if piece:
                out.append(piece)
    return out
