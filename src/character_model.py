#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""角色词条 → 语义化 JSON。

词条组件（component_id）与取值：

- ``role_base_info`` —— 名称、星级、头像、「标签-值」基础信息（生日 / 所属 /
  定位 / 武器类型 / 命之座 / 称号）
- ``role_talent`` —— 天赋：每项含名称、说明、倍率表
- ``role_ascension`` —— 突破材料：按「N级属性/突破所需材料」分档
- ``multi_table``（模块「命之座」）—— 六命：单元格内嵌图标 + 名称 + 说明
- ``role_voice`` —— 语音台词：按语言分组，默认只保留汉语
  （``voice_languages`` 参数可改，``"all"`` 保留全部语言）
- ``role_relation`` / ``recommend`` —— 角色关系网 / 推荐装备（方表，保留行列）
- 折叠面板 —— 角色故事 1-5、角色CV、特殊料理、回答等，按模块名收集

元素 / 地区 / 武器类型取分类卡片上的筛选标签，站点没写就不输出该键。
"""

import re

from model_utils import (base_attrs, collapse_panels, components, find_components,
                         first_component, materials, table, tables)
from richtext import clean_html, clean_values, extract_images, html_to_text

VOICE_LANGUAGES = ("汉语",)     # 默认保留的语音语言，配置 voice_languages 可覆盖

_CV_LABELS = ("中", "日", "英", "韩")


def _parse_cv(text):
    """CV 面板 → {语言: 名字}。

    站点里有三种写法：``中：谢莹``、``中 谢莹``（表格单元格各占一行）、
    ``中`` 单独一行紧跟 ``谢莹``，这里统一按标签-值配对。
    """
    out = {}
    lines = [line.strip() for line in (text or "").split("\n") if line.strip()]
    pending = None
    for line in lines:
        head, sep, value = line.replace("：", ":", 1).partition(":")
        head, value = head.strip(), value.strip()
        if not sep:
            # 无冒号：可能是「中 谢莹」同格，或标签单独占行
            parts = line.split(None, 1)
            if parts and parts[0] in _CV_LABELS and parts[0] not in out:
                if len(parts) == 2:
                    out[parts[0]] = parts[1].strip()
                    pending = None
                else:
                    pending = parts[0]
                continue
            if pending and pending not in out and line:
                out[pending] = line
                pending = None
            continue
        if head in _CV_LABELS and head not in out:
            if value:
                out[head] = value
                pending = None
            else:
                pending = head
    return out


def _constellation_from_cell(cell):
    """单个命座富文本段 → {name, desc, icon?}；空段返回 None。"""
    cleaned = clean_html(cell)
    lines = [line for line in cleaned["text"].split("\n") if line.strip()]
    if not lines:
        return None
    item = {"name": lines[0].strip(), "desc": "\n".join(lines[1:]).strip()}
    if cleaned["images"]:
        item["icon"] = cleaned["images"][0]
    return item


def _constellations(page):
    """命之座：multi_table 里有两种排版。

    - 方表：表头「名称 / 介绍」，每行一格名称一格介绍（老模板）；
    - 单格：整张表一个单元格，六命以 ``<hr>`` 分隔（新模板）。
    """
    out = []
    for module_name, comp in components(page):
        if comp.get("component_id") != "multi_table" or module_name != "命之座":
            continue
        for raw in ((comp.get("data") or {}).get("tables") or []):
            header = [html_to_text(h).strip() for h in raw.get("header") or []]
            rows = raw.get("row") or []
            if "介绍" in header and len(header) >= 2:
                name_idx = header.index("名称") if "名称" in header else 0
                desc_idx = header.index("介绍")
                for row in rows:
                    if not isinstance(row, list) or len(row) <= max(name_idx, desc_idx):
                        continue
                    name = html_to_text(row[name_idx]).replace("\n", " ").strip()
                    desc = html_to_text(row[desc_idx]).strip()
                    if not name and not desc:
                        continue
                    item = {"name": name, "desc": desc}
                    images = extract_images(row[name_idx])
                    if images:
                        item["icon"] = images[0]
                    out.append(item)
            else:
                cells = [cell for row in rows for cell in row]
                chunks = []
                for cell in cells:
                    parts = re.split(r"<hr[^>]*>", str(cell or ""))
                    chunks.extend(parts if len(parts) > 1 else [cell])
                for chunk in chunks:
                    item = _constellation_from_cell(chunk)
                    if item:
                        out.append(item)
    # 同名命座去重（站点偶见同一模块重复挂载）
    deduped, seen = [], set()
    for item in out:
        if item["name"] in seen:
            continue
        seen.add(item["name"])
        deduped.append(item)
    return deduped


def _talents(page):
    out = []
    for data in find_components(page, "role_talent"):
        for item in data.get("list") or []:
            if not isinstance(item, dict):
                continue
            talent = {"tab": str(item.get("tab_name") or "").strip() or None,
                      "name": str(item.get("title") or "").strip() or None}
            desc = html_to_text(item.get("desc") or "").strip()
            if desc:
                talent["desc"] = desc
            icon = str(item.get("icon") or "").strip()
            if icon:
                talent["icon"] = icon
            restored = table(item.get("attr") or {})
            if restored:
                talent["multipliers"] = restored
            out.append(talent)
    return out


def _ascension(page):
    out = []
    for data in find_components(page, "role_ascension"):
        for item in data.get("list") or []:
            if not isinstance(item, dict):
                continue
            level = str(item.get("tab_name") or "").strip()
            entry = {"level": level or None, "materials": materials(item)}
            attrs = base_attrs(item)
            if attrs:
                entry["attrs"] = attrs
            out.append(entry)
    return out


def _voices(page, languages=VOICE_LANGUAGES):
    """语音台词 → ``{语言: [{name, content, audio?}]}``，按 ``languages`` 过滤。

    ``languages`` 为 ``"all"`` 或含 ``"all"`` 时保留全部语言，否则只留列表里的。
    """
    keep_all = (languages == "all"
                or (isinstance(languages, (list, tuple))
                    and any(str(v).lower() == "all" for v in languages)))
    out = {}
    for data in find_components(page, "role_voice"):
        for group in data.get("list") or []:
            lang = str((group or {}).get("tab_name") or "").strip()
            if not lang:
                continue
            if not keep_all and languages and lang not in languages:
                continue
            lines = []
            for voice in group.get("table") or []:
                name = str((voice or {}).get("name") or "").strip()
                content = str((voice or {}).get("content") or "").strip()
                if not name and not content:
                    continue
                item = {"name": name or None, "content": content or None}
                audio = str((voice or {}).get("audio_url") or "").strip()
                if audio:
                    item["audio"] = audio
                lines.append(item)
            if lines:
                out[lang] = lines
    return out


def _recommend(page):
    out = []
    for data in find_components(page, "recommend"):
        out.extend(tables(data))
    return out


def _relations(page):
    for module_name, comp in components(page):
        if comp.get("component_id") == "role_relation":
            restored = tables(comp.get("data") or {})
            if restored:
                return restored
    return None


def build(card, page, voice_languages=VOICE_LANGUAGES):
    """组装单个角色词条。``card`` 是分类卡片，``page`` 是词条正文。

    ``voice_languages`` 指定保留哪些语言的语音，``"all"`` = 全部语言。
    """
    from obc_api import ENTRY_URL, Client

    base = first_component(page, "role_base_info") or {}
    attrs = base_attrs(base)

    record = {
        "id": Client.card_id(card),
        "name": str(base.get("name") or Client.card_name(card)).strip(),
        "url": ENTRY_URL.format(Client.card_id(card)),
    }
    if record["name"] != Client.card_name(card):
        record["card_name"] = Client.card_name(card)
    summary = Client.card_summary(card)
    if summary:
        record["summary"] = summary
    alias = Client.card_alias(card)
    if alias:
        record["alias"] = alias

    for key, prefix in (("region", "地区"), ("element", "元素"),
                        ("weapon_type", "武器")):
        value = Client.card_filter(card, prefix)
        if value:
            record[key] = value
    if isinstance(base.get("star"), int):
        record["rarity"] = base["star"]
    icon = Client.card_icon(card) or str(base.get("avatar_pc") or "").strip()
    if icon:
        record["icon"] = icon

    if attrs:
        record["basic"] = attrs

    cv = next((panel for panel in collapse_panels(page, "角色CV")), None)
    if cv:
        parsed = _parse_cv(cv["text"])
        if parsed:
            record["cv"] = parsed

    record["talents"] = _talents(page)
    constellations = _constellations(page)
    if constellations:
        record["constellations"] = constellations
    record["ascension"] = _ascension(page)
    recommend = _recommend(page)
    if recommend:
        record["recommend"] = recommend
    relations = _relations(page)
    if relations:
        record["relations"] = relations

    voices = _voices(page, voice_languages)
    if voices:
        record["voices"] = voices

    stories, extras = {}, {}
    for panel in collapse_panels(page):
        name = panel["name"]
        if name.startswith("角色故事"):
            stories[name] = panel["text"]
        elif name in ("角色详细", "更多描述", "特殊料理", "回答", "生日邮件"):
            extras[name] = panel["text"]
    if stories:
        record["stories"] = stories
    if extras:
        record["extras"] = extras

    displays = []
    for data in find_components(page, "map_desc"):
        for item in data.get("list") or []:
            name = str((item or {}).get("tab_name") or "").strip()
            image = str((item or {}).get("image") or "").strip()
            if name and image:
                displays.append({"name": name, "image": image})
    if displays:
        record["displays"] = displays

    return record
