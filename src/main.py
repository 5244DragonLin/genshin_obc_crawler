#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令行入口。

用法：
  python src/main.py                                # 按 config.yaml / 默认值导出全部分类
  python src/main.py --out "E:/BaiduSyncdisk/其他/原神观测枢图鉴"
  python src/main.py --only 角色 武器               # 只导指定分类
  python src/main.py --no-images                    # 不下载封面
  python src/main.py --limit 5                      # 每个分类只导 5 条，试跑用
  python src/main.py --dry-run                      # 只统计条数，不写文件
  python src/main.py --refresh                      # 忽略缓存重新请求
"""

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from config import load_config                           # noqa: E402
from exporter import CATALOGS, Exporter, normalize_catalogs   # noqa: E402
from obc_api import Client                               # noqa: E402
from progress import Console                             # noqa: E402

VERSION = "0.1.0"


def build_client(cfg, console=None):
    cache_dir = None
    if cfg.get("cache", {}).get("enabled", True):
        cache_dir = cfg["cache"].get("dir") or ".cache"
        if not os.path.isabs(cache_dir):
            cache_dir = os.path.join(SCRIPT_DIR, "..", cache_dir)
        cache_dir = os.path.abspath(cache_dir)
    request = cfg.get("request", {})
    return Client(timeout=request.get("timeout", 30),
                  retries=request.get("retries", 2),
                  delay=request.get("delay", 0.1),
                  cache_dir=cache_dir,
                  cache_ttl_hours=cfg.get("cache", {}).get("ttl_hours", 24),
                  verbose=cfg.get("logging", {}).get("verbose", False),
                  log=console,
                  proxy=request.get("proxy") or "")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="导出米游社观测枢（原神 WIKI）的角色 / 武器 / 圣遗物图鉴",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="分类别名：角色、武器、圣遗物")
    parser.add_argument("--out", "-o", help="输出目录，默认取 config.yaml 的 output_dir")
    parser.add_argument("--config", "-c", default="config.yaml", help="配置文件路径")
    parser.add_argument("--only", nargs="*", help="只导出指定分类（空格或逗号分隔）")
    parser.add_argument("--images", dest="images", action="store_true", default=None,
                        help="下载词条封面（默认开启）")
    parser.add_argument("--no-images", dest="images", action="store_false",
                        help="不下载封面，只在 JSON 里保留远程地址")
    parser.add_argument("--limit", type=int, help="每个分类最多导出几条（试跑用）")
    parser.add_argument("--refresh", action="store_true",
                        help="忽略 HTTP 缓存重新请求")
    parser.add_argument("--progress", dest="progress", action="store_true", default=None,
                        help="显示进度条（默认开启，仅终端下生效）")
    parser.add_argument("--no-progress", dest="progress", action="store_false",
                        help="不画进度条，只打日志")
    parser.add_argument("--dry-run", action="store_true", help="只统计条数，不写文件")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    out_root = os.path.abspath(args.out or cfg.get("output_dir") or "output")
    images = cfg.get("download_images", True) if args.images is None else args.images
    limit = args.limit if args.limit is not None else (cfg.get("limit") or 0)
    show_bar = (cfg.get("logging", {}).get("progress", True)
                if args.progress is None else args.progress)
    console = Console(show_bar=show_bar)
    refresh = bool(args.refresh)

    try:
        catalogs = normalize_catalogs(args.only)
    except ValueError as e:
        console(f"[配置] {e}")
        names = "、".join(c["name"] for c in CATALOGS)
        console(f"可用分类：{names}")
        return 1
    if not catalogs:
        console("没有匹配到分类。")
        return 1

    console("=" * 68)
    console(f"原神观测枢图鉴导出 {VERSION}｜{len(catalogs)} 个分类")
    console(f"本次抓取：{'、'.join(c['name'] for c in catalogs)}")
    console(f"输出目录：{out_root}")
    console("增量方式：全量正文 + 指纹对账（未变化的条目不重写）")
    console("=" * 68)

    client = build_client(cfg, console)

    if args.dry_run:
        total = 0
        bar = console.bar(len(catalogs), label="盘点")
        for index, catalog in enumerate(catalogs, 1):
            cards = client.channel_cards(catalog["channel"], refresh=refresh)
            count = min(len(cards), limit) if limit else len(cards)
            total += count
            console(f"[dry-run] {catalog['name']}"
                    f"（channel={catalog['channel']}）：{count} 条")
            bar.update(index, suffix=f"合计 {total} 条")
        bar.close(suffix=f"合计 {total} 条")
        console(f"[dry-run] 合计 {total} 条")
        return 0

    exporter = Exporter(client, out_root, images=images, limit=limit,
                        refresh=refresh, console=console)
    stats = exporter.run(catalogs)

    console("\n" + "=" * 68)
    total = sum(s["count"] for s in stats)
    errors = sum(len(s["errors"]) for s in stats)
    totals = exporter.changes.totals()
    console(f"导出完成：{total} 条，失败 {errors} 条")
    console(f"本次变化：新增 {totals['added']}、更新 {totals['updated']}、"
            f"移除 {totals['removed']}、未变 {totals['unchanged']}、失败 {totals['failed']}")
    for stat in stats:
        console(f"  {stat['name']}：{stat['count']} 条 → {stat['file']}")
    console(f"产物目录：{out_root}")
    console(f"变更明细：{os.path.join(out_root, 'changes.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
