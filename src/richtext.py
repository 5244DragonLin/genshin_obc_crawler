#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""观测枢富文本处理：HTML → 纯文本 / 结构化片段。

词条正文里的 ``<p>``、``<br>``、表格单元格自带内联样式与彩色 span，直接
留着的没法检索；材料、推荐武器这类可点击词条包在
``<span class="custom-entry-wrapper" data-entry-id=...>`` 里，图标包在
``<span class="custom-image-view" data-image-url=...>`` 里。本模块负责：

- :func:`html_to_text` —— 按块级标签分行，剥掉全部标签与实体转义；
- :func:`extract_entries` —— 抽出文本里引用的其他词条（名称 + 词条 id）；
- :func:`extract_images` —— 抽出内嵌图片地址；
- :func:`clean_html` —— 以上三者的打包结果，供建模器一次取全。

基于标准库 ``html.parser``，不引入额外依赖。
"""

import html as html_module
import re
from html.parser import HTMLParser

# 产生换行的块级标签（td / th 也按块处理，让表格单元格各占一行，
# 便于「中：谢莹」这类逐格内容按行配对）
_BLOCK_TAGS = {"p", "br", "hr", "li", "tr", "td", "th", "div", "h1", "h2",
               "h3", "h4", "h5", "h6", "table", "ul", "ol", "blockquote"}
_VOID_TAGS = {"br", "hr", "img"}

_ENTRY_ATTRS = ("data-entry-id", "data-entry-name", "data-entry-img", "data-entry-link")
_IMAGE_ATTRS = ("data-image-url", "src", "data-src")

_WS_RE = re.compile(r"[ \t\u00a0]+")
_LINE_RE = re.compile(r"\n\s*")


class _WikiParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines = []              # 最终文本行
        self._buf = []               # 当前行片段
        self.entries = []            # 引用的词条
        self.images = []             # 内嵌图片
        self._entry_stack = []       # 处理中的 custom-entry-wrapper

    # -- 工具 ----------------------------------------------------------
    def _flush_line(self):
        line = _WS_RE.sub(" ", "".join(self._buf)).strip()
        self._buf = []
        if line:
            self.lines.append(line)

    def _break(self):
        self._flush_line()

    def _grab(self, attrs, names):
        values = dict(attrs or {})
        return {name: values.get(name) for name in names if values.get(name)}

    # -- 解析 ----------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        if tag in _VOID_TAGS:
            self._break()
        elif tag in _BLOCK_TAGS:
            self._break()
        if tag == "span":
            entry = self._grab(attrs, _ENTRY_ATTRS)
            if entry:
                self._entry_stack.append(entry)
            image = self._grab(attrs, ("data-image-url",))
            if image:
                self.images.append(image["data-image-url"])
        elif tag == "img":
            image = self._grab(attrs, ("data-image-url", "src", "data-src"))
            url = image.get("data-image-url") or image.get("src") or image.get("data-src")
            if url:
                self.images.append(url)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag == "span":
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS or tag in _VOID_TAGS:
            self._break()
        if tag == "span" and self._entry_stack:
            self.entries.append(self._entry_stack.pop())

    def handle_data(self, data):
        if data:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush_line()


def parse_fragment(html):
    """解析一段富文本，返回 ``(lines, entries, images)``。"""
    parser = _WikiParser()
    try:
        parser.feed(str(html or ""))
        parser.close()
    except Exception:
        text = html_module.unescape(re.sub(r"<[^>]+>", " ", str(html or "")))
        return [line.strip() for line in text.splitlines() if line.strip()], [], []
    return parser.lines, parser.entries, parser.images


def html_to_text(html):
    """富文本 → 纯文本。块级标签转行，剥样式与实体，压掉空行。"""
    lines, _, _ = parse_fragment(html)
    return "\n".join(_LINE_RE.sub("\n", "\n".join(lines)).split("\n")) if lines else ""


def extract_entries(html):
    """文本引用的其他词条：``[{id, name, img, link}]``，按出现顺序去重。"""
    _, entries, _ = parse_fragment(html)
    out, seen = [], set()
    for entry in entries:
        key = str(entry.get("data-entry-id") or "")
        name = str(entry.get("data-entry-name") or "").strip()
        if not key and not name:
            continue
        marker = (key, name)
        if marker in seen:
            continue
        seen.add(marker)
        out.append({"id": key or None, "name": name,
                    "img": entry.get("data-entry-img"),
                    "link": entry.get("data-entry-link")})
    return out


def extract_images(html):
    """内嵌图片地址，按出现顺序去重。"""
    _, _, images = parse_fragment(html)
    out, seen = [], set()
    for url in images:
        url = str(url).strip()
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def clean_html(html):
    """一次取全：返回 ``{text, entries, images}``。"""
    lines, entries, images = parse_fragment(html)
    return {
        "text": "\n".join(_LINE_RE.sub("\n", "\n".join(lines)).split("\n")) if lines else "",
        "entries": extract_entries(html),
        "images": extract_images(html),
    }


def clean_values(value):
    """观测枢字段的标准形态 ``{"key": ..., "value": [html, ...]}`` → 纯文本。

    value 数组里每段是一块 HTML，块间按空格拼接成一行；整体非列表或为空
    时返回空串。
    """
    if isinstance(value, dict):
        value = value.get("value")
    if not isinstance(value, list):
        return html_to_text(value) if value else ""
    parts = [html_to_text(item) for item in value]
    return " ".join(part for part in parts if part)
