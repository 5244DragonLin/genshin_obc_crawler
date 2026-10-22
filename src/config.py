#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置加载：内置默认值 → config.yaml → 命令行参数。

只依赖标准库；装了 PyYAML 就用它解析，没装也能用内置的极简解析器跑通
本项目配置文件用到的语法子集（嵌套字典、字符串、数字、布尔、行内列表、注释）。
"""

import os
import re

DEFAULT_CONFIG = {
    "output_dir": "output",
    "download_images": True,
    "limit": 0,
    "request": {
        "timeout": 30,
        "retries": 2,
        "delay": 0.1,
        "proxy": "",
    },
    "cache": {
        "enabled": True,
        "dir": ".cache",
        "ttl_hours": 24,
    },
    "logging": {
        "verbose": False,
        "progress": True,
    },
}


def _strip_comment(line):
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out)


def _scalar(value):
    value = value.strip()
    if not value:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    low = value.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~", "none"):
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in re.split(r"\s*,\s*", inner) if part.strip()]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def parse_yaml(text):
    """解析配置用到的 YAML 子集。"""
    lines = [_strip_comment(raw).rstrip() for raw in str(text).splitlines()]

    def block(start, indent):
        data, i = {}, start
        while i < len(lines):
            raw = lines[i]
            if not raw.strip():
                i += 1
                continue
            cur = len(raw) - len(raw.lstrip(" "))
            if cur < indent:
                break
            content = raw.strip()
            if ":" not in content:
                i += 1
                continue
            key, _, value = content.partition(":")
            key = key.strip().strip("\"'")
            value = value.strip()
            if value:
                data[key] = _scalar(value)
                i += 1
                continue
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and (len(lines[j]) - len(lines[j].lstrip(" "))) > cur:
                child, i = block(j, len(lines[j]) - len(lines[j].lstrip(" ")))
                data[key] = child
            else:
                data[key] = {}
                i += 1
        return data, i

    return block(0, 0)[0]


def _merge(base, extra):
    out = dict(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        elif value not in (None, ""):
            out[key] = value
    return out


def load_config(path="config.yaml"):
    """读配置文件；不存在就用默认值。"""
    merged = _merge(DEFAULT_CONFIG, {})
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        try:
            import yaml            # 装了 PyYAML 优先用
            data = yaml.safe_load(raw) or {}
        except Exception:
            data = parse_yaml(raw)
        merged = _merge(merged, data)
    return merged
