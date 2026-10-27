#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""建模公共取值：组件定位、表格还原、材料条目。

观测枢词条正文是一组 ``modules → components``，每个组件有稳定的
``component_id``（如 ``role_base_info`` / ``equipment_growth_info``），
组件 ``data`` 里是模板化的 dict（``{"key": ..., "value": [...]}`` 的
「标签-值」对、``{"header": [...], "row": [...]}`` 的表格）。这里集中
处理这些通用形态，各类图鉴建模器只关心自己的组件。
"""

from richtext import clean_html, clean_values, html_to_text


def components(page):
    """按出现顺序展开 ``(模块名, 组件)``。"""
    for module in (page or {}).get("modules") or []:
        for comp in module.get("components") or []:
            yield str(module.get("name") or ""), comp


def find_components(page, component_id):
    """取全部指定 component_id 的组件 data（同名组件可能出现多次）。"""
    out = []
    for _, comp in components(page):
        if comp.get("component_id") == component_id:
            data = comp.get("data")
            if isinstance(data, dict):
                out.append(data)
    return out


def first_component(page, component_id):
    """取第一个指定 component_id 的组件 data，没有返回 None。"""
    found = find_components(page, component_id)
    return found[0] if found else None


def base_attrs(data):
    """``role_base_info.attr`` 这类「标签-值」列表 → ``{标签: 文本}``。

    同名标签取第一次出现的值；value 数组多段拼接为一段文本。
    """
    out = {}
    for item in (data or {}).get("attr") or []:
        key = str(item.get("key") or "").strip().rstrip("：:").strip()
        if not key:
            continue
        text = clean_values(item.get("value"))
        if text and key not in out:
            out[key] = text
    return out


def rich_list(data):
    """``rich_base_info.list`` 这类「标签-值」列表 → ``{标签: 文本}``。"""
    out = {}
    for item in (data or {}).get("list") or []:
        key = str(item.get("key") or "").strip().rstrip("：:").strip()
        if not key:
            continue
        text = clean_values(item.get("value"))
        if text and key not in out:
            out[key] = text
    return out


def _cell_text(cell):
    """表格单元格 → 纯文本（内部换行保留为空格分隔）。"""
    return html_to_text(cell).replace("\n", " ").strip()


def table(data):
    """还原 ``{"header": [...], "row": [[...]]}`` 表格。

    返回 ``{"header": [...], "rows": [[...]]}``，全部单元格转为纯文本；
    ``header`` 缺失时按列数生成 ``列1/列2…`` 占位。
    """
    if not isinstance(data, dict):
        return None
    header = [(_cell_text(h) or f"列{i + 1}") for i, h in enumerate(data.get("header") or [])]
    rows = []
    for raw in data.get("row") or []:
        if not isinstance(raw, list):
            continue
        cells = [_cell_text(cell) for cell in raw]
        if header and len(cells) < len(header):
            cells += [""] * (len(header) - len(cells))
        elif header and len(cells) > len(header):
            cells = cells[:len(header)]
        rows.append(cells)
    if not header and rows:
        header = [f"列{i + 1}" for i in range(len(rows[0]))]
    if not rows:
        return None
    return {"header": header, "rows": rows}


def tables(data):
    """``multi_table.tables`` / ``recommend.tables`` → 逐张还原。"""
    out = []
    for raw in (data or {}).get("tables") or []:
        restored = table(raw)
        if not restored:
            continue
        restored = dict(restored)
        tab = str((raw or {}).get("tab_name") or "").strip()
        if tab:
            restored["tab"] = tab
        out.append(restored)
    return out


def materials(data, field="materials"):
    """材料列表 ``[{ep_id, amount, nickname, img, link}]`` → 规整条目。

    ``ep_id`` 就是该材料词条的 content_id，可直接用于跳转与关联。
    ``field`` 指定取哪个字段：角色突破、武器成长、食物配方都是
    ``materials``，敌人的掉落物用 ``feedback``（同一种条目形态）。
    """
    out = []
    for item in (data or {}).get(field) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("nickname") or "").strip()
        entry_id = str(item.get("ep_id") or "").strip()
        if not name and not entry_id:
            continue
        entry = {"name": name or None, "count": item.get("amount")}
        if entry_id:
            entry["id"] = entry_id
        img = str(item.get("img") or "").strip()
        if img:
            entry["icon"] = img
        out.append(entry)
    return out


def collapse_panels(page, name=None):
    """折叠面板组件（角色故事、CV、特殊料理等）。

    返回 ``[(模块名, 文本, entries)]``；同名模块可出现多次（角色故事1-5）。
    """
    out = []
    for module_name, comp in components(page):
        if comp.get("component_id") != "collapse_panel":
            continue
        if name is not None and module_name != name:
            continue
        data = comp.get("data") or {}
        cleaned = clean_html(data.get("rich_text") or "")
        text = cleaned["text"].strip()
        if text or cleaned["entries"]:
            out.append({"name": module_name, "text": text, "entries": cleaned["entries"]})
    return out
