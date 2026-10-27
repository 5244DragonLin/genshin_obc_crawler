#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""富文本处理测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from richtext import (clean_html, clean_values, extract_entries, extract_images,
                      extract_notes, html_to_text)


class TestHtmlToText(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(html_to_text("<p>普通攻击</p><p>进行至多五段的连续攻击。</p>"),
                         "普通攻击\n进行至多五段的连续攻击。")

    def test_strips_style_and_color(self):
        html = '<p><span style="color: rgb(212, 177, 6)">重击</span></p><p>消耗体力。</p>'
        self.assertEqual(html_to_text(html), "重击\n消耗体力。")

    def test_br_makes_line_break(self):
        self.assertEqual(html_to_text("技能名<br>效果说明"), "技能名\n效果说明")

    def test_entities(self):
        self.assertEqual(html_to_text("<p>攻击力&gt;50%&amp;暴击</p>"), "攻击力>50%&暴击")

    def test_empty(self):
        self.assertEqual(html_to_text(""), "")
        self.assertEqual(html_to_text(None), "")
        self.assertEqual(html_to_text("<p></p><p> </p>"), "")


class TestExtractEntries(unittest.TestCase):
    HTML = ('<p><span class="custom-entry-wrapper" data-entry-id="857" '
            'data-entry-name="哀叙冰玉碎屑" data-entry-img="http://img/857.png" '
            'data-entry-link="/ys/obc/content/857/detail"><a>哀叙冰玉碎屑</a></span>'
            '×1，以及<span class="custom-entry-wrapper" data-entry-id="858" '
            'data-entry-name="哀叙冰玉断片">断片</span>×9。</p>')

    def test_entries(self):
        entries = extract_entries(self.HTML)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["id"], "857")
        self.assertEqual(entries[0]["name"], "哀叙冰玉碎屑")
        self.assertEqual(entries[0]["img"], "http://img/857.png")
        self.assertEqual(entries[1]["id"], "858")

    def test_dedup(self):
        html = ('<p><span data-entry-id="1" data-entry-name="甲">甲</span></p>'
                '<p><span data-entry-id="1" data-entry-name="甲">甲</span></p>')
        self.assertEqual(len(extract_entries(html)), 1)

    def test_text_without_entries(self):
        self.assertEqual(extract_entries("<p>普通文本</p>"), [])

    def test_amount_becomes_count(self):
        # 材料条目带数量（data-entry-amount）时补一个 count
        html = ('<p><span class="custom-entry-wrapper" data-entry-id="756" '
                'data-entry-name="琉璃百合" data-entry-amount="2"><a>琉璃百合</a></span>'
                '，<span class="custom-entry-wrapper" data-entry-id="777" '
                'data-entry-name="糖"><a>糖</a></span></p>')
        entries = extract_entries(html)
        self.assertEqual(entries[0]["count"], 2)
        self.assertNotIn("count", entries[1])


class TestExtractNotes(unittest.TestCase):
    def test_footnote(self):
        # 正文只留 [1] 标记，注释正文在 span 的 data-name 里（值为转义过的 HTML）
        html = ('<p>世界8(93级)：112.36w<span data-type="1" '
                'data-name="&lt;p&gt;数据为实测，单位以&lt;strong&gt;w&lt;/strong&gt;计。&lt;/p&gt;" '
                'class="wiki-note-text"><sup class="wiki-sup">[1]</sup></span></p>')
        self.assertEqual(html_to_text(html), "世界8(93级)：112.36w[1]")
        notes = extract_notes(html)
        self.assertEqual(notes["1"], "数据为实测，单位以w计。")

    def test_no_notes(self):
        self.assertEqual(extract_notes("<p>普通文本</p>"), {})
        self.assertEqual(extract_notes(None), {})


class TestExtractImages(unittest.TestCase):
    def test_image_view_and_img(self):
        html = ('<span class="custom-image-view" data-image-url="http://a.png">'
                '</span><img src="http://b.png"/><img src="http://a.png"/>')
        self.assertEqual(extract_images(html), ["http://a.png", "http://b.png"])


class TestCleanHtml(unittest.TestCase):
    def test_bundle(self):
        cleaned = clean_html('<p><span data-entry-id="9" data-entry-name="丙">丙</span>'
                             '<img src="http://i.png"/></p>')
        self.assertEqual(cleaned["text"], "丙")
        self.assertEqual(cleaned["entries"][0]["name"], "丙")
        self.assertEqual(cleaned["images"], ["http://i.png"])


class TestCleanValues(unittest.TestCase):
    def test_value_list(self):
        value = {"key": "获取途径：", "value": ["<p>限定祈愿</p>", "<p>活动获取</p>"]}
        self.assertEqual(clean_values(value), "限定祈愿 活动获取")

    def test_plain_string(self):
        self.assertEqual(clean_values(["<p>直接文本</p>"]), "直接文本")
        self.assertEqual(clean_values(None), "")


if __name__ == "__main__":
    unittest.main()
