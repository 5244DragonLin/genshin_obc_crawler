#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""增量对账：内容指纹、旧产物索引、变更清单。

产物按「内容指纹」对账：

- 指纹 = 建模结果 JSON 的哈希（键序归一，忽略本地封面路径 ``cover``，
  它随下载状态变化，不代表内容更新）；
- 没变的条目原样沿用旧记录，没变的分类不重写产物文件；
- 抓取失败的条目保留旧记录，不因一次网络抖动把词条从产物里删掉；
- 每轮新增 / 更新 / 移除 / 失败 / 未变写入 ``changes.json``。
"""

import hashlib
import json
import os
import time

# 参与指纹时忽略的键：本地封面路径随下载状态变化，不是内容本身
_VOLATILE_KEYS = ("cover",)


def fingerprint(record):
    """建模结果 → 内容指纹（sha256 十六进制）。"""
    cleaned = {key: value for key, value in (record or {}).items()
               if key not in _VOLATILE_KEYS}
    text = json.dumps(cleaned, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_old_records(out_root, catalog):
    """读旧产物 JSON，返回 ``{id: 旧记录}``；没有或损坏返回空表。"""
    path = os.path.join(out_root, f"{catalog['name']}.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    records = data.get("items") if isinstance(data, dict) else None
    if not isinstance(records, list):
        return {}
    return {str(item.get("id")): item for item in records
            if isinstance(item, dict) and item.get("id") is not None}


class Changes:
    """单轮变更记录，最后整体写入 ``changes.json``。"""

    def __init__(self):
        self.catalogs = []
        self.checked_at = time.strftime("%Y-%m-%d %H:%M:%S")

    def add(self, catalog_key, catalog_name, added, updated, removed, failed,
            unchanged, skipped=0):
        self.catalogs.append({
            "key": catalog_key, "name": catalog_name,
            "added": added, "updated": updated, "removed": removed,
            "failed": failed, "unchanged": unchanged, "skipped": skipped,
        })

    def totals(self):
        keys = ("added", "updated", "removed", "failed", "unchanged", "skipped")
        return {key: sum(c.get(key, 0) for c in self.catalogs) for key in keys}

    def dump(self, out_root):
        data = {"checked_at": self.checked_at,
                "totals": self.totals(),
                "catalogs": self.catalogs}
        path = os.path.join(out_root, "changes.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return path


def write_manifest(out_root, stats, generated_at=None):
    """写 ``manifest.json``：各分类条数、失败明细与检查时间。"""
    data = {
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "generated_at": generated_at,
        "catalogs": [{"key": s["key"], "name": s["name"], "count": s["count"],
                      "file": s["file"], "failed": s["errors"]} for s in stats],
    }
    path = os.path.join(out_root, "manifest.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return path
