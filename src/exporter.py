#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取编排、封面下载与落盘。

每个图鉴对应观测枢的一个频道（channel_id），列表接口一次取全，词条正文
逐条从 hoyowiki 新平台接口获取。分类定义见 :mod:`catalogs`：

- 前六类图鉴（角色 / 武器 / 圣遗物 / 敌人 / 食物 / 书籍）走专用建模器；
- 快捷导航里其余频道走 :mod:`generic_model` 的通用建模；
- 千星奇域 / 卡牌图鉴 / 影音回廊是聚合频道，一个频道收多个子频道的卡片，
  记录里的 ``channel`` 标明来路。

标题带「预告」的未上线词条（如「米提亚【预告】」，正文全是「待更新」占位）
直接跳过不导出；影音类频道的「角色预告 PV」是正经片名，按分类定义里的
``previews: False`` 关掉这条规则。产物结构：

- ``角色图鉴.json`` + ``旅行者/<角色>.md``（每人一篇，附 ``index.md``）
- ``<分类名>.json`` 每类一个
- ``assets/<分类>/`` 封面与组件图片
- ``manifest.json`` / ``changes.json`` / ``.state.json``
"""

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import character_md
import character_model
import generic_model
# 分类定义搬到了 catalogs.py，这里保留导出路径兼容旧代码
from catalogs import CATALOGS, normalize_catalogs       # noqa: F401
from obc_api import PREVIEW_MARK, Client, deep_parse, get_opener
from state import Changes, fingerprint, load_old_records, write_manifest

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_MD_DIR = "旅行者"          # 角色 Markdown 目录
_ART_DIR = "立绘"           # 角色立绘子目录（相对 assets/character）

# 按标题标记跳过的未上线词条（如「米提亚【预告】」，正文全是「待更新」占位）
_SKIP_PREVIEWS = True


def is_preview(card, catalog=None):
    """未上线词条：标题带「预告」标记（米提亚【预告】、瓦列里【预告】）。

    影音类频道（``previews: False``）标题里的「角色预告 PV」是正经片名，
    不能当占位跳过。
    """
    if catalog is not None and not catalog.get("previews", True):
        return False
    return _SKIP_PREVIEWS and PREVIEW_MARK in Client.card_name(card)


def _safe_name(name):
    """文件名安全化：去掉路径分隔符与 Windows 保留字符。"""
    return re.sub(r'[\\/:*?"<>|]', "_", str(name or "")).strip() or "未命名"


def _url_ext(url):
    """图片地址的后缀名，认不出时按 .png 处理。"""
    ext = os.path.splitext(urllib.parse.urlparse(str(url or "")).path)[1].lower()
    return ext if ext in (".png", ".jpg", ".jpeg", ".webp") else ".png"


def _subchannel(card, subchannels):
    """聚合频道里卡片属于哪个子频道：``ext`` 的 ``c_<id>`` 键即子频道 id。

    这是快路径；少数卡片 ``ext`` 为空（站点没写筛选标签），由
    :meth:`Exporter._subchannel_index` 按子频道列表补齐。
    """
    if not subchannels:
        return None
    ext = deep_parse((card or {}).get("ext"))
    if not isinstance(ext, dict):
        return None
    for key in ext:
        match = re.fullmatch(r"c_(\d+)", str(key))
        if not match:
            continue
        name = subchannels.get(int(match.group(1)))
        if name:
            return name
    return None


def _image_paths(record):
    """记录里的本地图片路径，用来判断产物是否需要重写。"""
    return (record.get("cover"),)


def _name_counts(records):
    """统计同一分类内各名字出现次数，用来判断是否需要追加后缀。"""
    counts = {}
    for record in records:
        name = record.get("name") or ""
        counts[name] = counts.get(name, 0) + 1
    return counts


def _looks_ok(path):
    """本地文件是否还可用：不存在或小到不可能是一张图都视为不可用。

    站点最小的封面约 3.6KB，1KB 的下限只拦截断文件与 0 字节文件，
    避免一次写坏之后再也走不到重新下载的分支。
    """
    try:
        return os.path.getsize(path) > 1024
    except OSError:
        return False


def _download(url, path, opener=None):
    """下载封面到本地；成功返回 True。

    临时文件名带上线程标识：同名词条（如旅行者各元素版本）会落到同一个
    封面路径，并发写时若共用 ``.tmp`` 会互相截断，加线程号后各写各的。
    """
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", UA)
        req.add_header("Referer", "https://baike.mihoyo.com/")
        with (opener or get_opener()).open(req, timeout=30) as resp:
            data = resp.read()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}-{threading.get_ident()}.tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


class Exporter:
    def __init__(self, client, out_root, images=True, limit=0, refresh=False,
                 console=None, voice_languages=None, concurrency=16):
        self.client = client
        self.out_root = out_root
        self.images = bool(images)
        self.limit = int(limit or 0)
        self.refresh = bool(refresh)
        self.console = console or print
        self.opener = client.opener
        self.voice_languages = voice_languages or character_model.VOICE_LANGUAGES
        self.concurrency = max(1, int(concurrency or 1))
        self.changes = Changes()
        self._cover_urls = {}               # catalog_key -> {id: 远程头像地址}
        self._art_urls = {}                 # catalog_key -> {id: 远程立绘地址}
        self._cover_lock = threading.Lock()  # 图片台账在多线程里登记，加锁保护
        self._sub_index = {}                # 聚合频道：词条 id -> 子频道名
        self._load_state()

    # ------------------------------------------------------------------
    def _load_state(self):
        path = os.path.join(self.out_root, ".state.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data.get("cover_urls"), dict):
                self._cover_urls = data["cover_urls"]
            if isinstance(data.get("art_urls"), dict):
                self._art_urls = data["art_urls"]
        except Exception:
            pass

    def _save_state(self):
        path = os.path.join(self.out_root, ".state.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"cover_urls": self._cover_urls, "art_urls": self._art_urls},
                      f, ensure_ascii=False)
        os.replace(tmp, path)

    # ------------------------------------------------------------------
    def _fetch_image(self, key, entry_id, url, relative, ledger):
        """按「地址没变且本地文件完好」判定可复用，否则下载；成功返回 True。"""
        absolute = os.path.join(self.out_root, relative)
        with self._cover_lock:
            known = ledger.setdefault(key, {})
            reusable = known.get(entry_id) == url and _looks_ok(absolute)
        if reusable:
            return True
        if not _download(url, absolute, self.opener):
            return False
        with self._cover_lock:
            known[entry_id] = url
        return True

    def _cover(self, catalog, record, name_counts):
        """下载图片，返回 ``(封面路径, 失败提示)``。

        角色只下词条内的立绘，不再保留列表页的 196×196 头像；没有立绘的词条
        封面留空。武器与圣遗物仍取列表页的图标。

        文件名与 Markdown 用同一套规则（同名记录追加元素后缀），旅行者各元素
        版本因此各占一个文件，不再互相覆盖。

        本方法会在多个线程里同时执行：台账读写加锁，提示文案返回给主线程
        去打，避免和进度条抢同一行。
        """
        if not self.images:
            return None, None
        key = catalog["key"]
        entry_id = record.get("id")
        stem = self._file_stem(record, name_counts)

        if key == "character":
            if not record.get("portrait"):
                return None, None
            relative = os.path.join("assets", key, _ART_DIR,
                                    f"{stem}{_url_ext(record['portrait'])}")
            if self._fetch_image(key, entry_id, record["portrait"], relative,
                                 self._art_urls):
                return relative, None
            return None, f"    立绘下载失败：{record.get('name')}"

        # 通用分类里，秘境 / 家具 / 名片这类把主图放在 image
        source = record.get("icon") or record.get("image")
        if not source:
            return None, None
        relative = os.path.join("assets", key, f"{stem}.png")
        if self._fetch_image(key, entry_id, source, relative,
                             self._cover_urls):
            return relative, None
        return None, f"    封面下载失败：{record.get('name')}"

    # ------------------------------------------------------------------
    def _subchannel_index(self, catalog):
        """聚合频道的「词条 id → 子频道名」索引。

        卡片 ``ext`` 里的 ``c_<子频道id>`` 只覆盖挂了筛选标签的卡片：千星奇域
        有 12 条、影音回廊有 5 条站点没写标签（如「旅行者语音展示」「WIKI
        编辑教程」），``ext`` 是空的。这里逐个子频道取一遍列表补齐，
        每个子频道一次请求，代价远小于逐条词条。
        """
        subchannels = catalog.get("subchannels")
        if not subchannels:
            return {}
        index = {}
        for channel_id, name in sorted(subchannels.items()):
            try:
                cards = self.client.channel_cards(channel_id, refresh=self.refresh)
            except Exception:
                continue
            for card in cards:
                index[self.client.card_id(card)] = name
        return index

    # ------------------------------------------------------------------
    def _build(self, catalog, card):
        """单条词条建模，取正文但不碰封面。

        封面留到全部记录就绪后再并发下载：文件名要不要加元素后缀，取决于
        同一分类内还有没有同名记录，而这个信息只有全部建模完才知道。
        """
        entry_id = self.client.card_id(card)
        try:
            page = self.client.entry_page(entry_id, refresh=self.refresh)
            if catalog.get("generic"):
                record = generic_model.build(card, page, catalog)
                # 聚合频道：卡片 ext 里的 c_<子频道id> 指明来路，记进 channel
                sub = (_subchannel(card, catalog.get("subchannels"))
                       or self._sub_index.get(entry_id))
                if sub:
                    record["channel"] = sub
            elif catalog["key"] == "character":
                # 只有角色模型接受 voice_languages，其余模型是 build(card, page)
                record = catalog["model"].build(card, page,
                                                voice_languages=self.voice_languages)
            else:
                record = catalog["model"].build(card, page)
            record["cover"] = None
            return record, None
        except Exception as e:
            return None, {"id": entry_id, "name": self.client.card_name(card),
                          "error": str(e)[:200]}

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
        # 聚合频道先把子频道归属索引建好，建模线程里直接查
        self._sub_index = self._subchannel_index(catalog)

        # 未上线词条（标题带「预告」）不导出：正文全是「待更新」占位，
        # 之前抓进去的旧记录因此对不上，会按「移除」清掉 JSON 与 Markdown
        skipped = [Client.card_name(card) for card in cards
                   if is_preview(card, catalog)]
        if skipped:
            self.console(f"  跳过未上线词条 {len(skipped)} 条：{'、'.join(skipped)}")
        cards = [card for card in cards if not is_preview(card, catalog)]

        records, errors = [], []
        added = updated = removed = unchanged = 0
        old_fingerprints = {rid: fingerprint(rec) for rid, rec in old_by_id.items()}

        cards = cards[:self.limit] if self.limit else cards
        seen = set()
        bar = self.console.bar(len(cards), label=name)
        # 并发只覆盖「等网络」这一段；统计、进度条、落盘都在主线程做，
        # 结果按 ``pool.map`` 的输入顺序回收，产物顺序与串行时一致。
        done = 0
        fresh = []                              # 本轮建模成功、待下封面的记录
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            for record, error in pool.map(
                    lambda card: self._build(catalog, card), cards):
                done += 1
                if error is not None:
                    entry_id = error["id"]
                    errors.append(error)
                    if entry_id in old_by_id:       # 单条失败保留旧记录
                        records.append(old_by_id[entry_id])
                        seen.add(entry_id)
                else:
                    entry_id = str(record.get("id"))
                    records.append(record)
                    fresh.append(record)
                    seen.add(entry_id)
                    new_fp = fingerprint(record)
                    if entry_id in old_fingerprints:
                        if new_fp == old_fingerprints[entry_id]:
                            unchanged += 1
                        else:
                            updated += 1
                    else:
                        added += 1
                bar.update(done)
        bar.close(suffix=f"失败 {len(errors)} 条")

        # 封面单独一轮：此时全部记录已就绪，重名判断才准确，每条记录各有
        # 一个确定的文件路径，不会因为并发完成先后而互相覆盖。
        if fresh:
            name_counts = _name_counts(records)
            warnings = []
            with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
                for record, (cover, warning) in zip(
                        fresh, pool.map(
                            lambda rec: self._cover(catalog, rec, name_counts),
                            fresh)):
                    record["cover"] = cover
                    if warning:
                        warnings.append(warning)
            for warning in warnings:
                self.console(warning)
            # 内容没变但封面路径变了（如加后缀区分同名记录）也算一轮更新，
            # 否则会跳过重写，JSON 里的路径与磁盘上的文件对不上。
            repathed = 0
            for record in fresh:
                entry_id = str(record.get("id"))
                old = old_by_id.get(entry_id)
                if old is None:
                    continue
                if fingerprint(record) == old_fingerprints.get(entry_id) \
                        and _image_paths(record) != _image_paths(old):
                    repathed += 1
            if repathed:
                unchanged -= repathed
                updated += repathed

        removed_ids = [rid for rid in old_by_id if rid not in seen]
        removed = len(removed_ids)
        # 移除条目的封面文件一并清理（Markdown 已有对应清理），避免磁盘留孤儿图
        for rid in removed_ids:
            cover = (old_by_id.get(rid) or {}).get("cover")
            if not cover:
                continue
            try:
                os.remove(os.path.join(self.out_root, cover))
            except OSError:
                pass
        if not errors and records:
            # 全部条目未变且没有增删时，不重写产物
            same_set = (set(seen) == set(old_fingerprints))
            all_same = same_set and all(
                fingerprint(rec) == old_fingerprints.get(str(rec.get("id")))
                and _image_paths(rec) == _image_paths(old_by_id.get(str(rec.get("id"))) or {})
                for rec in records)
            if all_same:
                if catalog.get("md"):
                    # 产物文件可能被手动删过：检查一遍，缺了就地补齐
                    self._write_markdown(records, removed_ids, old_records)
                self.console(f"  {name} 完成：{len(records)} 条，未变 {unchanged} 条，产物不重写"
                             + (f"（跳过未上线 {len(skipped)} 条）" if skipped else ""))
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
                     f"（新增 {added} / 更新 {updated} / 移除 {removed} / 未变 {unchanged}）"
                     + (f"，跳过未上线 {len(skipped)} 条" if skipped else ""))
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
    def _file_stem(record, name_counts):
        """文件名主干：同名记录追加元素或 id，避免落到同一个文件。

        Markdown 与封面共用这一套规则，两边的文件名保持一致。
        """
        name = _safe_name(record.get("name") or record.get("id"))
        if name_counts.get(record.get("name") or "", 1) > 1:
            suffix = record.get("element") or record.get("id")
            if suffix:
                name = f"{name}-{_safe_name(suffix)}"
        return name

    @classmethod
    def _md_filename(cls, record, name_counts):
        return f"{cls._file_stem(record, name_counts)}.md"


def _md_fingerprint(record):
    """Markdown 重写判定：与 JSON 指纹同源，忽略 cover 差异。"""
    return fingerprint(record)
