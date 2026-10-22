#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终端进度输出：日志与进度条共用一条通道。

进度条只占一行；写日志时先擦掉进度条、打完日志再重绘，长跑时既能
看到进度，也不会把日志行冲散。输出不是终端（重定向到文件、管道、
CI 日志）时自动降级成每 10% 打一行，不带回车符。
"""

import os
import shutil
import sys
import time
import unicodedata

REDRAW_INTERVAL = 0.1        # 终端上两次重绘的最小间隔（秒）
PLAIN_STEPS = 10             # 非终端时按 10% 打一行

_RESET = "\033[0m"
_STYLES = {"bar": "\033[36m", "pct": "\033[1m", "dim": "\033[2m"}

# 实心/空心字符按控制台编码挑：Windows 的 cp936 有 █ 没有 ░
_BAR_SETS = (("█", "░"), ("█", "-"), ("=", "-"))


def _isatty(stream):
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _encodable(stream, text):
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
        return True
    except (LookupError, UnicodeEncodeError):
        return False


def _enable_windows_ansi():
    """Windows 控制台默认不认 ANSI，试着打开 VT 处理。"""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & 0x0004:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def _ansi_ok(stream):
    if not _isatty(stream) or os.environ.get("NO_COLOR"):
        return False
    if os.name != "nt":
        return True
    if os.environ.get("WT_SESSION") or os.environ.get("TERM"):
        return True
    return _enable_windows_ansi()


def _width(text):
    """可见宽度：全角字符按两列算，否则进度条会顶到下一行。"""
    total = 0
    for ch in text:
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def _clip(text, room):
    """按可见宽度截断。"""
    if room <= 0:
        return ""
    if _width(text) <= room:
        return text
    out, used = [], 0
    for ch in text:
        step = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if used + step > room:
            break
        out.append(ch)
        used += step
    return "".join(out)


def _join(sep, parts):
    return "".join(sep + part for part in parts)


def _clock(seconds):
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class Console:
    """日志与进度条的唯一出口，可直接当 ``print`` 用。"""

    def __init__(self, stream=None, show_bar=True, color=None):
        self.stream = stream if stream is not None else sys.stdout
        self.tty = _isatty(self.stream)
        self.show_bar = bool(show_bar)
        self.color = _ansi_ok(self.stream) if color is None else bool(color)
        self.unicode = _encodable(self.stream, "█░·")
        self.fill, self.empty = next(
            (pair for pair in _BAR_SETS
             if _encodable(self.stream, pair[0]) and _encodable(self.stream, pair[1])),
            _BAR_SETS[-1])
        self.sep = " · " if _encodable(self.stream, "·") else " | "
        self._bar = None
        self._drawn = 0

    # ------------------------------------------------------------------
    @property
    def width(self):
        try:
            return shutil.get_terminal_size((80, 24)).columns
        except Exception:
            return 80

    def __call__(self, message=""):
        """打一行日志：先擦进度条，打完再画回去。"""
        self._clear()
        self._write(f"{message}\n")
        if self._bar is not None:
            self._bar._render(force=True)

    def bar(self, total, label="", suffix=""):
        """新建进度条；同一时间只有一条，旧的直接收尾。"""
        if self._bar is not None:
            self._bar.close()
        self._bar = Bar(self, total, label, suffix)
        return self._bar

    # ------------------------------------------------------------------
    def _write(self, text):
        self.stream.write(text)
        self.stream.flush()

    def _clear(self):
        if self.tty and self._drawn:
            self.stream.write("\r" + " " * self._drawn + "\r")
            self.stream.flush()
            self._drawn = 0

    def _style(self, text, style):
        if not self.color or not style or not text:
            return text
        return _STYLES[style] + text + _RESET

    def _draw(self, segments, newline=False):
        room = max(12, self.width - 1)
        out, used = [], 0
        for text, style in segments:
            if used >= room:
                break
            piece = _clip(text, room - used)
            used += _width(piece)
            out.append(self._style(piece, style))
            if _width(piece) < _width(text):
                break
        pad = max(0, self._drawn - used) if not newline else 0
        self.stream.write("\r" + "".join(out) + " " * pad)
        if newline:
            self.stream.write("\n")
        self.stream.flush()
        self._drawn = 0 if newline else used


class Bar:
    """单行进度条。由 ``Console.bar()`` 创建，结束时调用 ``close()``。"""

    def __init__(self, console, total, label="", suffix=""):
        self.console = console
        self.total = max(int(total or 0), 0)
        self.label = label or ""
        self.suffix = suffix or ""
        self.count = 0
        self.started = time.monotonic()
        self._last_draw = 0.0
        self._last_step = -1
        self._closed = False
        self._render(force=True)

    # ------------------------------------------------------------------
    def advance(self, step=1, suffix=None):
        self.update(self.count + step, suffix)

    def update(self, count, suffix=None):
        if self._closed:
            return
        if suffix is not None:
            self.suffix = suffix
        self.count = max(0, int(count))
        if self.total:
            self.count = min(self.count, self.total)
        self._render()

    def close(self, suffix=None):
        if self._closed:
            return
        if suffix is not None:
            self.suffix = suffix
        self._closed = True
        self._render(force=True, finish=True)
        if self.console._bar is self:
            self.console._bar = None
            self.console._drawn = 0

    # ------------------------------------------------------------------
    def _decile(self):
        if not self.total:
            return PLAIN_STEPS if self.count else 0
        return int(self.count * PLAIN_STEPS / self.total)

    def _render(self, force=False, finish=False):
        console = self.console
        if not console.show_bar:
            return
        if not console.tty:
            # 条数太少时按 10% 打点只剩噪音，交给收尾的「完成」日志
            if self.total < 20:
                return
            step = self._decile()
            if not finish and (step == 0 or step == self._last_step):
                return
            if finish and self._last_step >= step:
                return
            self._last_step = step
            console._write(self._plain_line() + "\n")
            return
        now = time.monotonic()
        if not force and now - self._last_draw < REDRAW_INTERVAL:
            return
        self._last_draw = now
        console._draw(self._segments(), newline=finish)

    def _counts(self):
        if not self.total:
            return f"{self.count} 条"
        return f"{self.count}/{self.total}"

    def _percent(self):
        if not self.total:
            return 100.0 if self.count else 0.0
        return min(100.0, self.count * 100.0 / self.total)

    def _plain_line(self):
        """非终端下的一行摘要，不带回车符，可直接进日志文件。"""
        line = f"  {self.label} " if self.label else "  "
        line += f"{self._percent():.0f}%（{self._counts()}）"
        if self.suffix:
            line += f" {self.console.sep.strip()} {self.suffix}"
        return line

    def _segments(self):
        console = self.console
        percent = self._percent()
        head = f"  {self.label} " if self.label else "  "
        pct_text = f" {percent:3.0f}%"
        tail = [self._counts()]
        elapsed = time.monotonic() - self.started
        if self.count >= 5 and elapsed >= 1.0:
            speed = self.count / elapsed
            tail.append(f"{speed:.1f} 条/秒")
            if self.total > self.count:
                tail.append(f"剩余 {_clock((self.total - self.count) / speed)}")
        if self.suffix:
            tail.append(self.suffix)

        room = max(6, console.width - 1 - _width(head) - _width(pct_text))
        # 空间不够时从尾部往回丢：先丢封面数、再丢剩余时间，最后连计数也不显示
        while tail and _width(_join(console.sep, tail)) > room - 8:
            tail.pop()
        tail_text = _join(console.sep, tail)
        bar_width = max(8, min(26, room - _width(tail_text)))
        filled = int(bar_width * percent / 100.0 + 0.5)
        bar = console.fill * filled + console.empty * (bar_width - filled)
        return [(head, None), (bar, "bar"), (pct_text, "pct"), (tail_text, "dim")]
