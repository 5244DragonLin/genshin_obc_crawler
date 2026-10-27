#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""米游社观测枢（原神 WIKI）公开接口客户端。

数据源分两个域名：

- 分类列表走 ``api-static.mihoyo.com`` 的 ``home/content/list``，一次返回
  整个频道的全部卡片（角色 / 武器 / 圣遗物等，无需翻页）；
- 词条正文走 ``act-api-takumi-static.mihoyo.com`` 的 ``hoyowiki`` 新平台
  接口 ``entry_page``，新旧词条都能取到（老的 ``v1/content/info`` 只剩
  未迁移的旧词条，新词条会报 -2010「内容不存在」，本项目不使用）。

全程 GET、无需登录。响应里大量字段是「Python 字面量字符串」（服务端
把 dict/list 直接 str() 后塞进 JSON），由 :func:`deep_parse` 统一还原。
"""

import ast
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

# 列表接口（CDN 域名，各频道卡片都在这里）
LIST_BASE = "https://api-static.mihoyo.com"
LIST_PATH = "/common/blackboard/ys_obc/v1/home/content/list"
APP_SN = "ys_obc"
# 词条正文接口（观测枢新平台，覆盖新旧全部词条）
DETAIL_BASE = "https://act-api-takumi-static.mihoyo.com"
DETAIL_PATH = "/hoyowiki/genshin/wapi/entry_page"
ENTRY_URL = "https://baike.mihoyo.com/ys/obc/content/{}/detail"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 未上线词条的标题标记，如「米提亚【预告】」；正文全是「待更新」占位
PREVIEW_MARK = "预告"

# 数据源全是国内 CDN：默认绕过系统 / 环境变量代理直连，需要代理时在
# config.yaml 的 request.proxy 里显式指定。opener 全局共享。
_direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_opener_cache = {"key": None, "opener": _direct_opener}


def get_opener(proxy=""):
    """按代理配置返回 opener；同一配置复用同一个实例。"""
    key = proxy or ""
    if _opener_cache["key"] != key:
        if proxy:
            _opener_cache["opener"] = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        else:
            _opener_cache["opener"] = _direct_opener
        _opener_cache["key"] = key
    return _opener_cache["opener"]


class EntryNotFound(Exception):
    """词条在接口侧不存在（retcode -2010 等）。"""


def deep_parse(value):
    """递归还原「字符串化的字面量」字段。

    服务端会把 dict / list 直接 ``str()`` 后当字符串塞进 JSON（单引号、
    True/False 都不是合法 JSON），先按 Python 字面量解析，不行再试 JSON，
    还不行就原样返回。递归到没有任何可解析的字符串为止。
    """
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in ("{", "[") and text[-1:] in ("}", "]"):
            try:
                value = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                try:
                    value = json.loads(text)
                except (ValueError, TypeError):
                    return value
    if isinstance(value, list):
        return [deep_parse(item) for item in value]
    if isinstance(value, dict):
        return {key: deep_parse(item) for key, item in value.items()}
    return value


def _looks_structured(text):
    text = text.strip()
    return len(text) >= 2 and text[0] in ("{", "[") and text[-1] in ("}", "]")


class Client:
    def __init__(self, timeout=30, retries=2, delay=0.1, cache_dir=None,
                 cache_ttl_hours=24, verbose=False, log=None, proxy=""):
        self.timeout = timeout
        self.retries = retries
        self.delay = delay
        self.cache_dir = cache_dir
        self.cache_ttl = cache_ttl_hours * 3600
        self.verbose = verbose
        self.log = log or print
        self.opener = get_opener(proxy)

    # ------------------------------------------------------------------
    # 网络
    # ------------------------------------------------------------------
    def _log(self, msg):
        if self.verbose:
            self.log(msg)

    def _get(self, url):
        """GET 一个接口，返回业务 data；网络异常退避重试，业务错误抛异常。"""
        req = urllib.request.Request(url)
        req.add_header("User-Agent", UA)
        req.add_header("Referer", "https://baike.mihoyo.com/")

        raw = None
        last_err = None
        for attempt in range(self.retries + 1):
            try:
                with self.opener.open(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                break
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", errors="replace")
                break
            except Exception as e:                      # URLError / TLS 抖动 / 超时
                last_err = e
                if attempt < self.retries:
                    time.sleep(0.4 * (2 ** attempt))
                    continue
                raise RuntimeError(f"网络错误：{e}（{url}）") from e
        try:
            obj = json.loads(raw)
        except (TypeError, ValueError):
            raise RuntimeError(f"响应不是 JSON：{(raw or '')[:200]}（{url}）")
        code = obj.get("retcode")
        if code != 0:
            message = obj.get("message") or ""
            if code in (-2010, -500001) or "内容不存在" in message:
                raise EntryNotFound(f"[{code}] {message}（{url}）")
            raise RuntimeError(f"[{code}] {message}（{url}）")
        return obj.get("data")

    # ------------------------------------------------------------------
    # 本地缓存
    # ------------------------------------------------------------------
    def _cache_path(self, *parts):
        if not self.cache_dir:
            return None
        return os.path.join(self.cache_dir, *parts)

    def _read_cache(self, path):
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except Exception:
            return None
        if self.cache_ttl and time.time() - rec.get("ts", 0) > self.cache_ttl:
            return None
        return rec.get("data")

    def _write_cache(self, path, data):
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"ts": time.time(), "data": data}, f, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 业务接口
    # ------------------------------------------------------------------
    def channel_cards(self, channel_id, refresh=False):
        """频道下的全部卡片。

        列表接口一次给全量，不用翻页；``children`` / ``ext`` 等
        字符串化字段在这里就地还原。
        """
        channel_id = str(channel_id)
        path = self._cache_path("list", f"{channel_id}.json")
        if not refresh:
            cached = self._read_cache(path)
            if cached is not None:
                return cached

        url = f"{LIST_BASE}{LIST_PATH}?app_sn={APP_SN}&channel_id={channel_id}"
        node = (self._get(url) or {}).get("list") or []
        cards = self._collect_leaf_cards(node)
        self._write_cache(path, cards)
        return cards

    def _collect_leaf_cards(self, nodes):
        """频道树可能是嵌套结构（父频道挂子频道），递归收集叶子上的卡片。"""
        cards = []
        for node in nodes or []:
            own = node.get("list") or []
            if own:
                cards.extend(own)
            else:
                cards.extend(self._collect_leaf_cards(deep_parse(node.get("children"))))
        return cards

    def entry_page(self, entry_id, refresh=False):
        """词条正文（hoyowiki 新平台，字符串字段已递归还原）。"""
        entry_id = str(entry_id)
        path = self._cache_path("entry", f"{entry_id}.json")
        if not refresh:
            cached = self._read_cache(path)
            if cached:
                return cached
        url = f"{DETAIL_BASE}{DETAIL_PATH}?entry_page_id={urllib.parse.quote(entry_id)}"
        data = self._get(url) or {}
        page = deep_parse(data.get("page") or {})
        if isinstance(page, dict) and page:
            self._write_cache(path, page)
        return page

    # ------------------------------------------------------------------
    # 卡片取值
    # ------------------------------------------------------------------
    @staticmethod
    def card_id(card):
        return str((card or {}).get("content_id") or "").strip()

    @staticmethod
    def card_name(card):
        return str((card or {}).get("title") or "").strip()

    @staticmethod
    def card_icon(card):
        return str((card or {}).get("icon") or "").strip()

    @staticmethod
    def card_summary(card):
        return str((card or {}).get("summary") or "").strip()

    @staticmethod
    def card_alias(card):
        return str((card or {}).get("alias_name") or "").strip()

    @staticmethod
    def card_is_preview(card):
        """未上线词条（标题带「预告」标记，如「米提亚【预告】」）。"""
        return PREVIEW_MARK in str((card or {}).get("title") or "")

    @staticmethod
    def card_filters(card):
        """卡片上的筛选标签，如 ``地区/纳塔``、``元素/冰``、``武器/单手剑``。

        存在 ``ext`` 的 ``c_<频道id>.filter.text`` 里，本身又是一个字符串化列表。
        """
        card = card or {}
        ext = deep_parse(card.get("ext"))
        tags = []
        if isinstance(ext, dict):
            for section in ext.values():
                filter_ = (section or {}).get("filter") or {}
                text = filter_.get("text")
                if isinstance(text, str) and _looks_structured(text):
                    try:
                        text = json.loads(text)
                    except (ValueError, TypeError):
                        text = deep_parse(text)
                if isinstance(text, list):
                    tags.extend(str(item).strip() for item in text if str(item).strip())
        return tags

    @staticmethod
    def card_filter(card, prefix):
        """取某个前缀的标签值，如 ``元素/冰`` → ``冰``；没有返回 None。"""
        for tag in Client.card_filters(card):
            if tag.startswith(prefix + "/"):
                return tag[len(prefix) + 1:].strip() or None
        return None

    @staticmethod
    def card_filter_all(card, prefix):
        """取某个前缀的全部标签值，按出现顺序去重。

        一个词条可能挂多个同类标签：敌人常有两种元素（``元素/冰``、
        ``元素/风``），食物可能同时是「攻击类」与「暴击类」。
        """
        values = []
        for tag in Client.card_filters(card):
            if tag.startswith(prefix + "/"):
                value = tag[len(prefix) + 1:].strip()
                if value and value not in values:
                    values.append(value)
        return values
