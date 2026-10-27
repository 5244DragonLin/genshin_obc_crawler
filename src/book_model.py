#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""书籍词条 → 语义化 JSON。

一个词条 = 一套书。正文里全部是 ``material_base_info``（卷信息）与
``collapse_panel``（该卷全文）两种组件，两者分开存放、排列顺序互不相干：
卷信息可能按「卷一、卷四、卷二、卷三」排，全文面板又是另一种顺序。

因此建模时先配对再排序：

- 配对：按卷名全等对齐 → 按正文首行的小节名对齐 → 按卷序整本对齐 →
数量相等时退回按出现顺序；
- 排序：按卷序（序 0、上本 1、中本 2、下本 3、第 N 卷 10+N）重排。

卷名写法不统一（「卷一 / 第一卷 / 卷三 / 其之一 / 上本 / 自定义标题」），
统一的解析见 :func:`volume_no`。
"""

import re

from model_utils import base_attrs, find_components
from richtext import html_to_text

_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# 卷序的特殊写法：序 / 前言排最前，上中下本按顺序落在卷一之前
_SECTION_ENDS = (("前言", 0), ("序", 0),
                 ("上本", 1), ("中本", 2), ("下本", 3),
                 ("上卷", 1), ("中卷", 2), ("下卷", 3))

_VOLUME_PATTERNS = (
    re.compile(r"第([零〇一二两三四五六七八九十]+)卷"),
    re.compile(r"卷([零〇一二两三四五六七八九十]+)"),
    re.compile(r"其之?([零〇一二两三四五六七八九十]+)"),
    re.compile(r"[·・.\-]\s*([零〇一二两三四五六七八九十]+)\s*$"),
    re.compile(r"([零〇一二两三四五六七八九十]+)\s*$"),
)


def _cn_number(text):
    """中文数字 → int，覆盖「三 / 十 / 十二 / 二十 / 二十一」。"""
    text = str(text or "")
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if "十" in text:
        head, _, tail = text.partition("十")
        tens = _CN_DIGITS.get(head, 1) if head else 1
        ones = _CN_DIGITS.get(tail, 0) if tail else 0
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    if len(text) == 1:
        return _CN_DIGITS.get(text)
    digits = [_CN_DIGITS.get(char) for char in text]
    if any(digit is None for digit in digits):
        return None
    return int("".join(str(digit) for digit in digits))


def volume_no(text):
    """卷名 → 卷序，认不出返回 None。

    数字卷统一记 ``10 + N``，使「序 / 前言」（0）和「上中下本」（1/2/3）
    稳定排在卷一之前。
    """
    text = str(text or "").strip()
    if not text:
        return None
    for word, value in _SECTION_ENDS:
        if text.endswith(word):
            return value
    for pattern in _VOLUME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        number = _cn_number(match.group(1))
        if number is not None:
            return 10 + number
    return None


def _name_key(text):
    """卷名比对用：去掉空白、书名号与分隔符再比。"""
    return re.sub(r"[\s·・.\-、（）()《》]+", "", str(text or ""))


def _tail_key(name):
    """书名末尾的小节名：``绝云记闻·石兽`` → ``石兽``；没有分隔符返回 None。

    「绝云记闻」这类合集每篇的小节名只在书名末尾，正文面板却统一叫
    「书籍内容」，只能靠正文首行的「——石兽——」对上。
    """
    parts = re.split(r"[·・.\-]\s*", str(name or ""))
    if len(parts) < 2:
        return None
    return _name_key(parts[-1]) or None


def _content_head(text):
    """正文首行去掉装饰性破折号：``——石兽——`` → ``石兽``。"""
    line = str(text or "").split("\n", 1)[0]
    return line.strip().strip("—－- ").strip()


def _panel_name_key(panel):
    return _name_key(panel.get("volume"))


def _panel_head_key(panel):
    return _name_key(panel.get("head"))


def _panel_volume_key(panel):
    return volume_no(panel.get("volume"))


# 配对策略，依次尝试；某一档能把两边整本对齐才算数
_STRATEGIES = (
    (_name_key, _panel_name_key),        # 卷名一致
    (_tail_key, _panel_head_key),        # 书名小节名 = 正文首行
    (volume_no, _panel_volume_key),      # 卷一 / 第一卷 / 其之一 / 上本
)


def _collect(page):
    """把正文拆成「卷信息块」与「全文面板」两组，各自保持出现顺序。"""
    infos, panels = [], []
    for data in find_components(page, "material_base_info"):
        info = {"name": str(data.get("name") or "").strip()}
        if isinstance(data.get("star"), int):
            info["rarity"] = data["star"]
        attrs = base_attrs(data)
        for key, target in (("描述", "desc"), ("作者", "author")):
            value = attrs.pop(key, "")
            if value:
                info[target] = value
        if attrs:
            info["attrs"] = attrs
        if info["name"]:
            infos.append(info)
    # 折叠面板另有少量杂质：模块名与正文都为空的不算
    for module in (page or {}).get("modules") or []:
        for comp in module.get("components") or []:
            if comp.get("component_id") != "collapse_panel":
                continue
            text = html_to_text((comp.get("data") or {}).get("rich_text") or "").strip()
            if not text:
                continue
            panels.append({"volume": str(module.get("name") or "").strip(),
                           "head": _content_head(text), "content": text})
    return infos, panels


def _match(infos, panels, info_key, panel_key):
    """按 ``info_key`` / ``panel_key`` 全等配对，返回 ``({信息块下标: 面板}, 未配对的面板)``。"""
    leftover = list(panels)
    keys = {id(panel): panel_key(panel) for panel in panels}
    pairs = {}
    for index, info in enumerate(infos):
        target = info_key(info.get("name"))
        if target is None:
            continue
        for pos in range(len(leftover)):
            if keys[id(leftover[pos])] == target:
                pairs[index] = leftover.pop(pos)
                break
    return pairs, leftover


def _pair(infos, panels):
    """卷信息块与全文面板配对，返回 ``[(信息块, 面板或 None)]``。

    站点在「序 + 卷一…卷六」这类整体错位编号的书里，两边的出现顺序恰好是
    对的；在「卷一、卷四、卷二、卷三」这类只打乱顺序的书里，卷序能整本对
    齐。所以先试卷名、再试正文首行、最后试卷序，都排不满时才退回出现顺序。
    """
    for info_key, panel_key in _STRATEGIES:
        pairs, leftover = _match(infos, panels, info_key, panel_key)
        complete = not leftover and len(pairs) == len(infos) == len(panels)
        if complete:
            return [(info, pairs.get(index)) for index, info in enumerate(infos)]

    if len(infos) == len(panels):
        return list(zip(infos, panels))

    # 数量不等：先吃掉按卷名能配上的，剩下的全文按顺序补给还没配上的卷
    pairs, leftover = _match(infos, panels, _name_key, _panel_name_key)
    for index in range(len(infos)):
        if index in pairs or not leftover:
            continue
        pairs[index] = leftover.pop(0)
    return [(info, pairs.get(index)) for index, info in enumerate(infos)]


def _sort_key(volume):
    """卷序认不出来的（自定义卷名）排在最后，彼此保持出现顺序。"""
    number = volume_no(volume.get("name") or volume.get("title"))
    return 10 ** 6 if number is None else number


def _volumes(page):
    infos, panels = _collect(page)
    pairs = _pair(infos, panels)

    volumes, used = [], set()
    for info, panel in pairs:
        volume = {}
        if panel and panel.get("volume"):
            volume["title"] = panel["volume"]
        if info.get("name"):
            volume["name"] = info["name"]
        if isinstance(info.get("rarity"), int):
            volume["rarity"] = info["rarity"]
        if info.get("desc"):
            volume["desc"] = info["desc"]
        if info.get("author"):
            volume["author"] = info["author"]
        if info.get("attrs"):
            volume["attrs"] = info["attrs"]
        if panel and panel.get("content"):
            volume["content"] = panel["content"]
        if panel:
            used.add(id(panel))
        if volume:
            volumes.append(volume)

    # 没配上卷信息的全文单独成卷，内容不丢
    for panel in panels:
        if id(panel) in used:
            continue
        volume = {}
        if panel.get("volume"):
            volume["title"] = panel["volume"]
        if panel.get("content"):
            volume["content"] = panel["content"]
        if volume:
            volumes.append(volume)

    volumes.sort(key=_sort_key)
    return volumes


def build(card, page):
    from obc_api import ENTRY_URL, Client

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

    types = Client.card_filter_all(card, "书籍类型")
    if types:
        record["types"] = types
    sources = Client.card_filter_all(card, "获取方式")
    if sources:
        record["sources"] = sources

    icon = Client.card_icon(card)
    if icon:
        record["icon"] = icon

    volumes = _volumes(page)
    if volumes:
        record["volumes"] = volumes

    return {key: value for key, value in record.items() if value not in (None, [], {})}
