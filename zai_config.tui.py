#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zsh-chat-ai 配置 TUI (curses)
用法(由插件调用):
    ai -config
或手动:
    python3 zai_config.tui.py ~/.config/zsh-chat-ai/config [init.json]

说明:
  - argv[1] = 配置文件路径(保存目标)
  - argv[2](可选) = 初始值 JSON 文件; 缺省则用内置默认
  - 用 curses 读写终端(stdin/stdout 保留为真终端, 按键才有效),
    不要通过管道喂 stdin。保存时把 ZAI_* 写成 KEY=VALUE 行。
返回码: 0=已保存, 1=放弃, 2=出错
"""
import curses
import json
import os
import sys

# 字段顺序即显示/保存顺序
ORDER = [
    "ZAI_API_URL",
    "ZAI_API_KEY",
    "ZAI_MODEL",
    "ZAI_TEMPERATURE",
    "ZAI_TIMEOUT",
    "ZAI_INTERCEPT",
    "ZAI_MIN_INTERCEPT_LEN",
    "ZAI_DESTRUCTIVE_POLICY",
    "ZAI_AUTO_CONFIRM",
    "ZAI_STOP_ON_ERROR",
    "ZAI_INCLUDE_CONTEXT",
    "ZAI_HISTORY",
    "ZAI_DEBUG",
    "ZAI_STREAM",
]

LABELS = {
    "ZAI_API_URL": "API 地址(OpenAI 兼容端点)",
    "ZAI_API_KEY": "API Key(留空回退 DEEPSEEK_API_KEY)",
    "ZAI_MODEL": "模型",
    "ZAI_TEMPERATURE": "Temperature",
    "ZAI_TIMEOUT": "请求超时(秒)",
    "ZAI_INTERCEPT": "拦截未知命令(纯自然语言)",
    "ZAI_MIN_INTERCEPT_LEN": "拦截最短首词长度",
    "ZAI_DESTRUCTIVE_POLICY": "危险命令策略",
    "ZAI_AUTO_CONFIRM": "自动确认执行",
    "ZAI_STOP_ON_ERROR": "出错时暂停询问",
    "ZAI_INCLUDE_CONTEXT": "发送系统上下文",
    "ZAI_HISTORY": "执行命令写入历史",
    "ZAI_DEBUG": "调试输出(脱敏)",
    "ZAI_STREAM": "流式显示思考内容",
}

DEFAULTS = {
    "ZAI_API_URL": "https://api.deepseek.com/chat/completions",
    "ZAI_API_KEY": "",
    "ZAI_MODEL": "deepseek-v4-flash",
    "ZAI_TEMPERATURE": "0.2",
    "ZAI_TIMEOUT": "60",
    "ZAI_INTERCEPT": "1",
    "ZAI_MIN_INTERCEPT_LEN": "2",
    "ZAI_DESTRUCTIVE_POLICY": "warn",
    "ZAI_AUTO_CONFIRM": "0",
    "ZAI_STOP_ON_ERROR": "1",
    "ZAI_INCLUDE_CONTEXT": "1",
    "ZAI_HISTORY": "0",
    "ZAI_DEBUG": "0",
    "ZAI_STREAM": "1",
}

BOOLS = {
    "ZAI_INTERCEPT", "ZAI_AUTO_CONFIRM", "ZAI_STOP_ON_ERROR",
    "ZAI_INCLUDE_CONTEXT", "ZAI_HISTORY", "ZAI_DEBUG", "ZAI_STREAM",
}
CHOICES = {"ZAI_DESTRUCTIVE_POLICY": ("warn", "block", "allow")}
INTS = {"ZAI_TIMEOUT", "ZAI_MIN_INTERCEPT_LEN"}
FLOATS = {"ZAI_TEMPERATURE"}
SECRET = {"ZAI_API_KEY"}


def mask(v):
    if not v:
        return ""
    if len(v) <= 6:
        return "*" * len(v)
    return "*" * (len(v) - 4) + v[-4:]


def read_extra(path, order):
    """保留文件中不属于 TUI 管理的键(如 ZAI_LANG), 避免保存时被丢弃。"""
    extra = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.rstrip("\n").rstrip("\r")
                st = s.strip()
                if not st or st.startswith("#"):
                    continue
                if "=" not in st:
                    continue
                key = st.split("=", 1)[0].strip()
                if key and key not in order and all(c.isalnum() or c == "_" for c in key):
                    extra.append(s)
    except OSError:
        pass
    return extra


def write_config(path, vals, order):
    try:
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        lines = []
        for k in order:
            v = vals.get(k, DEFAULTS.get(k, ""))
            if k in SECRET and v == "":
                continue  # 空 key: 不写, 表示回退 DEEPSEEK_API_KEY
            lines.append("%s=%s" % (k, v))
        lines += read_extra(path, order)  # 非 TUI 键原样保留
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
        return True
    except Exception as e:  # noqa: BLE001
        try:
            sys.stderr.write("config 写入失败: %s\n" % e)
        except Exception:  # noqa: BLE001
            pass
        return False


def main(stdscr):
    init = {}
    if len(sys.argv) > 2:
        try:
            with open(sys.argv[2], encoding="utf-8") as f:
                init = json.load(f)
        except Exception:  # noqa: BLE001
            init = {}
    elif not sys.stdin.isatty():
        # 兼容旧式: 从管道 stdin 读初始 JSON
        try:
            init = json.load(sys.stdin)
        except Exception:  # noqa: BLE001
            init = {}
    has_fallback = str(init.get("HAS_FALLBACK", "0")) in ("1", "1.0", "true", "True")

    vals = {}
    for k in ORDER:
        raw = init.get(k)
        vals[k] = DEFAULTS.get(k, "") if raw is None else str(raw)
    if "ZAI_DESTRUCTIVE_POLICY" in vals and vals["ZAI_DESTRUCTIVE_POLICY"] not in CHOICES["ZAI_DESTRUCTIVE_POLICY"]:
        vals["ZAI_DESTRUCTIVE_POLICY"] = "warn"

    order = ORDER
    n = len(order)
    cur = 0
    editing = False
    buf = ""
    save = False
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    stdscr.keypad(True)

    def display_value(k, raw):
        if k in SECRET:
            return mask(raw) if raw else ("<空: 用 DEEPSEEK_API_KEY>" if has_fallback else "<空>")
        if k in BOOLS:
            return "开" if raw == "1" else "关"
        if k == "ZAI_MODEL":
            return raw or "<默认 deepseek-v4-flash>"
        return raw

    while True:
        h, w = stdscr.getmaxyx()
        if h < n + 6 or w < 30:
            stdscr.erase()
            msg = "终端太小：需要至少 %dx%d 才能显示配置" % (30, n + 6)
            try:
                stdscr.addstr(0, 0, msg[:w - 1])
                stdscr.addstr(1, 0, "按 q 退出")
            except curses.error:
                pass
            stdscr.refresh()
            c = stdscr.getch()
            if c in (ord("q"), ord("Q"), 27):
                return 1
            continue

        stdscr.erase()
        title = "zsh-chat-ai 配置   操作: ↑/↓ 或 j/k 移动 · Enter 编辑/切换 · Esc 取消编辑 · s 保存 · q 退出"
        try:
            stdscr.addnstr(0, 0, title, w)
            y = 2
            for i, k in enumerate(order):
                label = LABELS.get(k, k)
                disp = display_value(k, vals[k])
                mark = "> " if (i == cur and not editing) else "  "
                attr = curses.A_REVERSE if (i == cur and not editing) else curses.A_NORMAL
                text = "%s%-36s  %s" % (mark, label[:36], disp)
                stdscr.addnstr(y, 0, text, w, attr)
                y += 1
            cfg = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else ""
            stdscr.addnstr(h - 2, 0, "[s] 保存并退出      [q] 退出不保存      config: " + cfg, w)
            if editing:
                k = order[cur]
                prefix = "编辑 %s: " % LABELS.get(k, k)
                shown = prefix + buf + "_"
                stdscr.addnstr(h - 1, 0, shown, w, curses.A_REVERSE)
                cells = 0
                for ch in shown:
                    cells += 2 if ord(ch) > 127 else 1
                stdscr.move(h - 1, min(w - 1, cells))
                try:
                    curses.curs_set(1)
                except curses.error:
                    pass
            else:
                try:
                    curses.curs_set(0)
                except curses.error:
                    pass
        except curses.error:
            pass
        stdscr.refresh()

        c = stdscr.getch()

        if editing:
            if c in (10, 13, curses.KEY_ENTER):
                k = order[cur]
                if k in INTS:
                    try:
                        vals[k] = str(int(buf))
                    except ValueError:
                        pass
                elif k in FLOATS:
                    try:
                        vals[k] = format(float(buf), ".6g")
                    except ValueError:
                        pass
                else:
                    vals[k] = buf
                editing = False
            elif c == 27:
                editing = False
            elif c in (8, 127, curses.KEY_BACKSPACE):
                buf = buf[:-1]
            elif 32 <= c <= 126:
                buf += chr(c)
        else:
            if c == curses.KEY_RESIZE:
                continue
            if c in (curses.KEY_UP, ord("k"), ord("K")):
                cur = (cur - 1) % n
            elif c in (curses.KEY_DOWN, ord("j"), ord("J")):
                cur = (cur + 1) % n
            elif c in (10, 13, curses.KEY_ENTER, ord(" ")):
                k = order[cur]
                if k in BOOLS:
                    vals[k] = "0" if vals[k] == "1" else "1"
                elif k in CHOICES:
                    opts = CHOICES[k]
                    try:
                        idx = opts.index(vals[k])
                    except ValueError:
                        idx = 0
                    vals[k] = opts[(idx + 1) % len(opts)]
                else:  # 文本 / 数字 / 密钥 → 进入编辑
                    editing = True
                    buf = vals[k]
            elif c in (ord("s"), ord("S")):
                save = True
                break
            elif c in (ord("q"), ord("Q"), 27):
                break

    if save:
        ok = write_config(sys.argv[1], vals, order)
        return 0 if ok else 2
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("用法: python3 zai_config.tui.py <配置文件路径> < initial.json\n")
        sys.exit(2)
    try:
        code = curses.wrapper(main)
    except curses.error:
        code = 2
    except KeyboardInterrupt:
        code = 1
    sys.exit(code)
