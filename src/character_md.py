#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""角色词条 → 单人物 Markdown。

与 JSON 共用同一份建模结果（:mod:`character_model`），只负责排版：
基础信息 → 天赋（含倍率表）→ 命之座 → 突破材料 → 推荐装备 → 语音 →
角色故事。图片引用产物目录里的 ``assets/character/``。
"""

import os

_MD_ESCAPE = str.maketrans({"|": "\\|", "\n": "<br>"})


def _esc(text):
    """表格单元格转义：竖线与换行。"""
    return str(text or "").translate(_MD_ESCAPE)


def _table(header, rows):
    if not rows:
        return ""
    out = ["| " + " | ".join(_esc(cell) for cell in header) + " |",
           "| " + " | ".join("---" for _ in header) + " |"]
    for row in rows:
        out.append("| " + " | ".join(_esc(cell) for cell in row) + " |")
    return "\n".join(out)


def _kv_table(pairs):
    rows = [[key, value] for key, value in pairs]
    return _table(["项目", "内容"], rows)


def render(record, image_dir="assets/character"):
    """角色词条 → Markdown 文本。``image_dir`` 是相对产物目录的图片路径。"""
    name = record.get("name") or "未命名"
    lines = [f"# {name}"]

    icon = record.get("icon")
    if icon and not str(icon).startswith("http"):
        lines.append(f"![{name}]({os.path.join('..', image_dir, icon)})")

    meta = []
    if record.get("rarity") is not None:
        meta.append(("稀有度", f"{record['rarity']}星"))
    for key, label in (("element", "元素"), ("weapon_type", "武器类型"),
                       ("region", "地区")):
        if record.get(key):
            meta.append((label, record[key]))
    if record.get("cv"):
        meta.append(("CV", "、".join(f"{lang}：{who}" for lang, who in record["cv"].items())))
    if record.get("summary"):
        meta.append(("简介", record["summary"]))
    if record.get("alias"):
        meta.append(("别名", record["alias"]))
    meta.append(("词条", record.get("url", "")))
    if meta:
        lines += ["", "## 基础信息", "", _kv_table(meta)]

    basic = record.get("basic") or {}
    if basic:
        lines += ["", "## 档案", "", _kv_table(basic.items())]

    for talent in record.get("talents") or []:
        head = " / ".join(part for part in (talent.get("tab"), talent.get("name")) if part)
        lines += ["", f"## 天赋：{head}" if head else "## 天赋"]
        if talent.get("desc"):
            lines += ["", talent["desc"]]
        multipliers = talent.get("multipliers")
        if multipliers:
            lines += ["", _table(multipliers["header"], multipliers["rows"])]

    constellations = record.get("constellations") or []
    if constellations:
        lines += ["", "## 命之座"]
        for index, item in enumerate(constellations, 1):
            lines += ["", f"### {index}. {item.get('name', '')}"]
            if item.get("desc"):
                lines += ["", item["desc"]]

    ascension = record.get("ascension") or []
    if ascension:
        lines += ["", "## 突破材料"]
        for stage in ascension:
            level = stage.get("level") or "未知档位"
            mats = "、".join(
                f"{mat.get('name') or mat.get('id')}×{mat.get('count')}"
                for mat in stage.get("materials") or [])
            attrs = stage.get("attrs") or {}
            attr_text = "；".join(f"{key}：{value}" for key, value in attrs.items())
            parts = [part for part in (mats, attr_text) if part]
            lines.append(f"- **{level}**{'：' + '。'.join(parts) if parts else ''}")

    recommend = record.get("recommend") or []
    for restored in recommend:
        title = restored.get("tab") or "推荐装备"
        lines += ["", f"## {title}", "", _table(restored["header"], restored["rows"])]

    voices = record.get("voices") or {}
    for lang, items in voices.items():
        lines += ["", f"## 语音（{lang}）"]
        for item in items:
            title = item.get("name") or "—"
            content = (item.get("content") or "").replace("\n", " ")
            lines.append(f"- **{title}**：{content}" if content else f"- **{title}**")

    stories = record.get("stories") or {}
    for title, text in stories.items():
        lines += ["", f"## {title}", "", text]

    extras = record.get("extras") or {}
    for title, text in extras.items():
        lines += ["", f"## {title}", "", text]

    return "\n".join(lines).rstrip() + "\n"


def index_header():
    return ["# 旅行者图鉴索引", "",
            "| 角色 | 元素 | 武器类型 | 稀有度 | 地区 |",
            "| --- | --- | --- | --- | --- |"]


def index_row(record):
    rarity = record.get("rarity")
    return ("| {name} | {element} | {weapon} | {rarity} | {region} |").format(
        name=record.get("name", ""),
        element=record.get("element") or "—",
        weapon=record.get("weapon_type") or "—",
        rarity=f"{rarity}星" if rarity is not None else "—",
        region=record.get("region") or "—")
