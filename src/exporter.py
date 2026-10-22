#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分类定义、抓取编排、封面下载与落盘。

三类图鉴各自对应观测枢的一个频道（channel_id），列表接口一次取全，
词条正文逐条从 hoyowiki 新平台接口获取。产物结构：

- ``角色图鉴.json`` + ``旅行者/<角色>.md``（每人一篇，附 ``index.md``）
- ``武器图鉴.json`` / ``圣遗物图鉴.json``
- ``assets/<分类>/`` 封面与组件图片
- ``manifest.json`` / ``changes.json`` / ``.state.json``
"""

import json
import os
import re
import time
import urllib.request

import artifact_model
import character_md
import character_model
import weapon_model
from obc_api import Client, get_opener
from state import Changes, fingerprint, load_old_records, write_manifest

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 观测枢频道 id（api-static 列表接口的 channel_id）
CATALOGS = [
    {"key": "character", "name": "角色图鉴", "channel": 25,
     "model": character_model, "md": True},
    {"key": "weapon", "name": "武器图鉴", "channel": 5,
     "model": weapon_model, "md": False},
    {"key": "artifact", "name": "圣遗物图鉴", "channel": 218,
     "model": artifact_model, "md": False},
]

# ``--only`` / 配置里的分类别名
_ALIASES = {
    "character": "character", "角色": "character", "角色图鉴": "character",
    "weapon": "weapon", "武器": "weapon", "武器图鉴": "weapon",
    "artifact": "artifact", "圣遗物": "artifact", "圣遗物图鉴": "artifact",
}

_MD_DIR = "旅行者"          # 角色 Markdown 目录


def normalize_catalogs(only):
    """``--only`` 别名列表 → CATALOGS 子集；空列表 = 全部。"""
    if not only:
        return list(CATALOGS)
    wanted = []
    for token in only:
        for part in re.split(r"[,，\s]+", str(token)):
            if not part:
                continue
            key = _ALIASES.get(part.lower().strip())
            if key is None:
                raise ValueError(f"未知分类：{part}")
            if key not in wanted:
                wanted.append(key)
    # 输出顺序固定为内置顺序，不跟随命令行顺序
    return [c for c in CATALOGS if c["key"] in wanted]


def _safe_name(name):
    """文件名安全化：去掉路径分隔符与 Windows 保留字符。"""
    return re.sub(r'[\\/:*?"<>|]', "_", str(name or "")).strip() or "未命名"


def _download(url, path, opener=None):
    """下载封面到本地；成功返回 True。"""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", UA)
        req.add_header("Referer", "https://baike.mihoyo.com/")
        with (opener or get_opener()).open(req, timeout=30) as resp:
            data = resp.read()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


class Exporter:
    def __init__(self, client, out_root, images=True, limit=0, refresh=False,
                 console=None, voice_languages=None):
        self.client = client
        self.out_root = out_root
        self.images = bool(images)
        self.limit = int(limit or 0)
        self.refresh = bool(refresh)
        self.console = console or print
        self.opener = client.opener
        self.voice_languages = voice_languages or character_model.VOICE_LANGUAGES
        self.changes = Changes()
        self._cover_urls = {}               # catalog_key -> {id: 远程封面地址}
        self._load_state()

    # ------------------------------------------------------------------
    def _load_state(self):
        path = os.path.join(self.out_root, ".state.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data.get("cover_urls"), dict):
                self._cover_urls = data["cover_urls"]
        except Exception:
            pass

    def _save_state(self):
        path = os.path.join(self.out_root, ".state.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"cover_urls": self._cover_urls}, f, ensure_ascii=False)
        os.replace(tmp, path)

    # ------------------------------------------------------------------
    def _cover(self, catalog, record):
        """下载词条封面，返回相对产物目录的路径；失败返回 None。

        远程地址没变时直接沿用本地文件，不重复下载。
        """
        url = record.get("icon")
        if not self.images or not url:
            return None
        known = self._cover_urls.setdefault(catalog["key"], {})
        name = _safe_name(record.get("name") or record.get("id"))
        relative = os.path.join("assets", catalog["key"], f"{name}.png")
        absolute = os.path.join(self.out_root, relative)
        if known.get(record.get("id")) == url and os.path.isfile(absolute):
            return relative
        if _download(url, absolute, self.opener):
            known[record.get("id")] = url
            return relative
        self.console(f"    封面下载失败：{record.get('name')}")
        return None

    # ------------------------------------------------------------------
    def run(self, catalogs):
        os.makedirs(self.out_root, exist_ok=True)
        stats = []
        for catalog in catalogs:
            stats.append(self._run_catalog(catalog))
        self._save_state()
        generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        stats = [dict(stat, generated_at=generated_at) for stat in stats]
        write_manifest(self.out_root, stats, generated_at)
        self.changes.dump(self.out_root)
        return stats

    def _run_catalog(self, catalog):
        name = catalog["name"]
        self.console(f"[{name}] 开始抓取")
        cards = self.client.channel_cards(catalog["channel"], refresh=self.refresh)
        old_records = load_old_records(self.out_root, catalog)
        old_by_id = dict(old_records)

        records, errors = [], []
        added = updated = removed = unchanged = 0
        old_fingerprints = {rid: fingerprint(rec) for rid, rec in old_by_id.items()}

        cards = cards[:self.limit] if self.limit else cards
        seen = set()
        bar = self.console.bar(len(cards), label=name)
        for index, card in enumerate(cards, 1):
            entry_id = self.client.card_id(card)
            title = self.client.card_name(card)
            try:
                page = self.client.entry_page(entry_id, refresh=self.refresh)
                record = catalog["model"].build(
                    card, page,
                    voice_languages=(self.voice_languages
                                     if catalog["key"] == "character" else None))
                record["cover"] = self._cover(catalog, record)
                records.append(record)
                seen.add(entry_id)
                new_fp = fingerprint(record)
                if entry_id in old_fingerprints:
                    if new_fp == old_fingerprints[entry_id]:
                        unchanged += 1
                    else:
                        updated += 1
                else:
                    added += 1
            except Exception as e:                  # 单条失败保留旧记录
                errors.append({"id": entry_id, "name": title, "error": str(e)[:200]})
                if entry_id in old_by_id:
                    records.append(old_by_id[entry_id])
                    seen.add(entry_id)
            bar.update(index)
        bar.close(suffix=f"失败 {len(errors)} 条")

        removed_ids = [rid for rid in old_by_id if rid not in seen]
        removed = len(removed_ids)
        if not errors and records:
            # 全部条目未变且没有增删时，不重写产物
            same_set = (set(seen) == set(old_fingerprints))
            all_same = same_set and all(
                fingerprint(rec) == old_fingerprints.get(str(rec.get("id")))
                for rec in records)
            if all_same:
                if catalog.get("md"):
                    # 产物文件可能被手动删过：检查一遍，缺了就地补齐
                    self._write_markdown(records, removed_ids, old_records)
                self.console(f"  {name} 完成：{len(records)} 条，未变 {unchanged} 条，产物不重写")
                self.changes.add(catalog["key"], name, added, updated, removed,
                                 len(errors), unchanged)
                return {"key": catalog["key"], "name": name, "count": len(records),
                        "file": f"{name}.json（未变）", "errors": errors}

        records.sort(key=lambda rec: (-(rec.get("rarity") or 0) if isinstance(rec.get("rarity"), int) else 0,
                                      rec.get("name") or ""))
        self._write_json(catalog, records)
        if catalog.get("md"):
            self._write_markdown(records, removed_ids, old_records)
        self.console(f"  {name} 完成：{len(records)} 条，失败 {len(errors)} 条"
                     f"（新增 {added} / 更新 {updated} / 移除 {removed} / 未变 {unchanged}）")
        self.changes.add(catalog["key"], name, added, updated, removed,
                         len(errors), unchanged)
        return {"key": catalog["key"], "name": name, "count": len(records),
                "file": f"{name}.json", "errors": errors}

    # ------------------------------------------------------------------
    def _write_json(self, catalog, records):
        path = os.path.join(self.out_root, f"{catalog['name']}.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"catalog": catalog["name"],
                       "count": len(records),
                       "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "items": records}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    def _write_markdown(self, records, removed_ids, old_records):
        md_root = os.path.join(self.out_root, _MD_DIR)
        os.makedirs(md_root, exist_ok=True)
        # 同名角色（旅行者按元素一题多版）文件名追加元素或 id 防覆盖
        name_counts = {}
        for record in records:
            key = record.get("name") or ""
            name_counts[key] = name_counts.get(key, 0) + 1
        written = 0
        for record in records:
            entry_id = str(record.get("id"))
            old = old_records.get(entry_id)
            filename = self._md_filename(record, name_counts)
            path = os.path.join(md_root, filename)
            if old is not None and _md_fingerprint(record) == _md_fingerprint(old) \
                    and os.path.isfile(path):
                continue
            with open(path, "w", encoding="utf-8") as f:
                f.write(character_md.render(record))
            written += 1
        for rid in removed_ids:
            old = old_records.get(rid)
            if not old:
                continue
            filename = self._md_filename(old, name_counts)
            path = os.path.join(md_root, filename)
            if os.path.isfile(path):
                os.remove(path)
        # 索引按稀有度倒序、同名按名称
        ordered = sorted(records, key=lambda rec: (
            -(rec.get("rarity") if isinstance(rec.get("rarity"), int) else 0),
            rec.get("name") or ""))
        lines = character_md.index_header()
        lines += [character_md.index_row(rec) for rec in ordered]
        with open(os.path.join(md_root, "index.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        self.console(f"  角色 Markdown 完成：{len(records)} 篇 → {_MD_DIR}/"
                     f"（本次重写 {written} 篇）")

    @staticmethod
    def _md_filename(record, name_counts):
        name = _safe_name(record.get("name") or record.get("id"))
        if name_counts.get(record.get("name") or "", 1) > 1:
            suffix = record.get("element") or record.get("id")
            if suffix:
                name = f"{name}-{_safe_name(suffix)}"
        return f"{name}.md"


def _md_fingerprint(record):
    """Markdown 重写判定：与 JSON 指纹同源，忽略 cover 差异。"""
    return fingerprint(record)
