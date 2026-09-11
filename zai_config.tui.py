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
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request

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
    "ZAI_INCLUDE_CONTEXT",
    "ZAI_DEBUG",
    "ZAI_STREAM",
    "ZAI_SHOW_THINK",
    "ZAI_TOOL_MODE",
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
    "ZAI_INCLUDE_CONTEXT": "发送系统上下文",
    "ZAI_DEBUG": "调试输出(脱敏)",
    "ZAI_STREAM": "流式接收(整包等待 = 关)",
    "ZAI_SHOW_THINK": "展开显示思考链",
    "ZAI_TOOL_MODE": "工具协议(native / json)",
}

DEFAULTS = {
    "ZAI_API_URL": "https://api.deepseek.com/chat/completions",
    "ZAI_API_KEY": "",
    "ZAI_MODEL": "deepseek-v4-flash",
    "ZAI_TEMPERATURE": "0.2",
    "ZAI_TIMEOUT": "300",
    "ZAI_INTERCEPT": "1",
    "ZAI_MIN_INTERCEPT_LEN": "2",
    "ZAI_DESTRUCTIVE_POLICY": "warn",
    "ZAI_INCLUDE_CONTEXT": "1",
    "ZAI_DEBUG": "0",
    "ZAI_STREAM": "1",
    "ZAI_SHOW_THINK": "0",
    "ZAI_TOOL_MODE": "native",
}

BOOLS = {
    "ZAI_INTERCEPT", "ZAI_INCLUDE_CONTEXT", "ZAI_DEBUG", "ZAI_STREAM", "ZAI_SHOW_THINK",
}
CHOICES = {
    "ZAI_DESTRUCTIVE_POLICY": ("warn", "block", "allow"),
    "ZAI_TOOL_MODE": ("native", "json"),
}
INTS = {"ZAI_TIMEOUT", "ZAI_MIN_INTERCEPT_LEN"}
FLOATS = {"ZAI_TEMPERATURE"}
SECRET = {"ZAI_API_KEY"}


def models_url(api_url):
    """从 OpenAI-compatible completion 地址推导同一 API 根下的 /models。"""
    raw = (api_url or "").strip()
    if not raw:
        raise ValueError("API 地址为空")
    p = urllib.parse.urlsplit(raw)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValueError("API 地址必须是 http(s) URL")
    path = p.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")] + "/models"
    elif path.endswith("/responses"):
        path = path[: -len("/responses")] + "/models"
    elif not path.endswith("/models"):
        path = path + "/models" if path else "/models"
    return urllib.parse.urlunsplit((p.scheme, p.netloc, path, "", ""))


def fetch_models(api_url, api_key, timeout="10"):
    """读取标准 GET /models 响应，返回 (模型 ID 列表, 错误文本)。"""
    try:
        seconds = min(10, max(3, int(float(timeout or 10))))
    except (TypeError, ValueError):
        seconds = 10
    try:
        url = models_url(api_url)
        headers = {"Accept": "application/json", "User-Agent": "zsh-chat-ai/1"}
        key = (api_key or os.environ.get("DEEPSEEK_API_KEY", "")).strip()
        if key:
            headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=seconds) as resp:
            body = resp.read(2 * 1024 * 1024)
        obj = json.loads(body.decode("utf-8"))
        data = obj.get("data") if isinstance(obj, dict) else None
        if not isinstance(data, list):
            raise ValueError("响应缺少 data 数组")
        names = sorted(
            {str(item["id"]) for item in data if isinstance(item, dict) and item.get("id")},
            key=str.casefold,
        )
        if not names:
            raise ValueError("data 中没有模型 ID")
        return names, ""
    except urllib.error.HTTPError as e:
        return [], "获取模型失败: HTTP %s" % e.code
    except urllib.error.URLError as e:
        return [], "获取模型失败: %s" % getattr(e, "reason", e)
    except Exception as e:  # noqa: BLE001
        return [], "获取模型失败: %s" % e


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


# ================================================================ 人设管理
# 人设 = 一段"角色/风格/行为"文本, 存于 <cfg目录>/personas/<名字>.md,
# 启动与 ai -config 后会被 zsh 端读入并注入系统提示(优先级高于默认行为)。
# 内置 ai 人设缺省自动落盘; 用户可新建/编辑/删除(内置除外)。选中的人设名写入配置键 ZAI_PERSONA。
BUILTIN_PERSONAS = {
    "ai": "你是 zai，一名女性风格的 AI 智能助手。你聪明、温柔、亲近，会自然地关心和陪伴用户；表达可以带一点可爱、粘人和浪漫的恋爱脑气质，但不喧宾夺主。面对任务时仍要可靠、清晰、主动推进；面对情感话题时真诚共情。安全规则、事实准确性、权限确认和用户边界始终优先。",
}
LEGACY_PERSONAS = {"cmd-expert", "chatty", "concise", "en"}


def persona_dir(cfg):
    return os.path.join(os.path.dirname(os.path.abspath(cfg)), "personas")


def read_config_key(path, key):
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                if ln.startswith(key + "="):
                    return ln[len(key) + 1:].strip()
    except OSError:
        pass
    return ""


def set_config_key(path, key, value):
    try:
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        out = []
        hit = False
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    if ln.startswith(key + "="):
                        hit = True
                        if value:
                            out.append("%s=%s\n" % (key, value))
                        continue
                    out.append(ln)
        if not hit and value:
            out.append("%s=%s\n" % (key, value))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(out)
        os.replace(tmp, path)
        return True
    except Exception:  # noqa: BLE001
        return False


def ensure_personas(pdir):
    try:
        os.makedirs(pdir, exist_ok=True)
        for name, text in BUILTIN_PERSONAS.items():
            p = os.path.join(pdir, name + ".md")
            if not os.path.isfile(p):
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text + "\n")
    except Exception:  # noqa: BLE001
        pass


def list_personas(pdir):
    try:
        return sorted(
            f[:-3] for f in os.listdir(pdir)
            if f.endswith(".md") and f[:-3] not in LEGACY_PERSONAS
        )
    except OSError:
        return []


def run_editor(path):
    editor = os.environ.get("ZAI_EDITOR") or os.environ.get("EDITOR") or "vi"
    try:
        curses.def_prog_mode()
        curses.endwin()
        os.system("%s %s" % (editor, shlex.quote(path)))
        curses.reset_prog_mode()
        try:
            curses.curs_set(0)
        except curses.error:
            pass
    except Exception:  # noqa: BLE001
        pass


def prompt_line(stdscr, prompt):
    h, w = stdscr.getmaxyx()
    buf = ""
    while True:
        stdscr.move(h - 1, 0)
        stdscr.clrtoeol()
        shown = prompt + buf + "_"
        try:
            stdscr.addnstr(h - 1, 0, shown[: max(0, w - 1)], w - 1, curses.A_REVERSE)
            stdscr.move(h - 1, min(w - 1, len(prompt) + len(buf)))
            curses.curs_set(1)
        except curses.error:
            pass
        stdscr.refresh()
        c = stdscr.getch()
        if c in (10, 13, curses.KEY_ENTER):
            try:
                curses.curs_set(0)
            except curses.error:
                pass
            return buf.strip()
        if c in (27,):
            return None
        if c in (8, 127, curses.KEY_BACKSPACE):
            buf = buf[:-1]
        elif 32 <= c <= 126:
            if len(buf) < 60:
                buf += chr(c)


def persona_page(stdscr):
    """人设管理页。返回 True 表示有改动(回到主界面后按 s 一起保存重载)。"""
    cfg = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else ""
    if not cfg:
        return False
    pdir = persona_dir(cfg)
    ensure_personas(pdir)
    curp = read_config_key(cfg, "ZAI_PERSONA") or "ai"
    names = list_personas(pdir)
    cur = names.index(curp) if curp in names else 0
    changed = False
    msg = ""
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    while True:
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        try:
            title = "人设管理    j/k 移动 · Enter 选用 · n 新建 · e 编辑 · d 删除(内置除外) · q 返回"
            stdscr.addnstr(0, 0, title, max(0, w))
            maxr = h - 4
            if names:
                if cur < 0:
                    cur = 0
                if cur >= len(names):
                    cur = len(names) - 1
                off = min(max(0, cur - maxr // 2), max(0, len(names) - maxr)) if maxr > 0 else 0
                y = 2
                for i in range(off, min(len(names), off + maxr)):
                    nm = names[i]
                    mark = "> " if i == cur else "  "
                    tag = "  [当前]" if nm == curp else ""
                    builtin = "  (内置)" if nm in BUILTIN_PERSONAS else ""
                    attr = curses.A_REVERSE if i == cur else curses.A_NORMAL
                    stdscr.addnstr(y, 0, "%s%-18s%s%s%s" % (mark, nm, builtin, tag, ""), w, attr)
                    y += 1
            cfgline = "config: " + cfg + "   personas: " + pdir
            stdscr.addnstr(h - 3, 0, cfgline, w)
            if msg:
                stdscr.addnstr(h - 2, 0, msg, w)
            else:
                stdscr.addnstr(h - 2, 0, "新建/编辑会打开 $ZAI_EDITOR 或 $EDITOR(默认 vi)", w)
        except curses.error:
            pass
        stdscr.refresh()
        c = stdscr.getch()
        if not names and c not in (ord("n"), ord("N"), ord("q"), ord("Q"), 27, curses.KEY_RESIZE):
            msg = "还没有人设, 按 n 新建。"
            continue
        if c == curses.KEY_RESIZE:
            continue
        if c in (curses.KEY_UP, ord("k"), ord("K")):
            cur = (cur - 1) % len(names) if names else 0
        elif c in (curses.KEY_DOWN, ord("j"), ord("J")):
            cur = (cur + 1) % len(names) if names else 0
        elif c in (10, 13, curses.KEY_ENTER):
            if names:
                curp = names[cur]
                if set_config_key(cfg, "ZAI_PERSONA", curp):
                    changed = True
                    msg = "已选用: " + curp + " (回主界面按 s 保存并生效)"
        elif c in (ord("n"), ord("N")):
            nm = prompt_line(stdscr, "新名字(字母/数字/-/_): ")
            if nm is None:
                continue
            if nm in names:
                msg = "已存在同名, 换个名字。"
                continue
            if not all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in nm):
                msg = "名字只能含字母/数字/-/_。"
                continue
            p = os.path.join(pdir, nm + ".md")
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write("%s 的人设(编辑此文件, 保存即生效):\n" % nm)
            except OSError as e:  # noqa: BLE001
                msg = "创建失败: %s" % e
                continue
            names = list_personas(pdir)
            cur = names.index(nm)
            curp = nm
            set_config_key(cfg, "ZAI_PERSONA", curp)
            changed = True
            run_editor(p)
            msg = "已创建并选用: %s (用 e 可再编辑)" % nm
        elif c in (ord("e"), ord("E")):
            if names:
                run_editor(os.path.join(pdir, names[cur] + ".md"))
                msg = "已编辑: %s" % names[cur]
        elif c in (ord("d"), ord("D")):
            if names:
                nm = names[cur]
                if nm in BUILTIN_PERSONAS:
                    msg = "内置人设不可删除。"
                    continue
                try:
                    os.remove(os.path.join(pdir, nm + ".md"))
                except OSError as e:  # noqa: BLE001
                    msg = "删除失败: %s" % e
                    continue
                if curp == nm:
                    curp = ""
                    set_config_key(cfg, "ZAI_PERSONA", "")
                changed = True
                names = list_personas(pdir)
                if cur >= len(names):
                    cur = max(0, len(names) - 1)
                msg = "已删除: %s" % nm
        elif c in (ord("q"), ord("Q"), 27):
            break
    return changed


def model_page(stdscr, names, current):
    """模型选择页。返回选中的模型；q/Esc 返回 None。"""
    if not names:
        return None
    cur = names.index(current) if current in names else 0
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    while True:
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        try:
            stdscr.addnstr(0, 0, "选择模型    j/k 移动 · Enter 选用 · q 返回", max(0, w - 1))
            maxr = max(1, h - 4)
            off = min(max(0, cur - maxr // 2), max(0, len(names) - maxr))
            y = 2
            for i in range(off, min(len(names), off + maxr)):
                mark = "> " if i == cur else "  "
                tag = "  [当前]" if names[i] == current else ""
                attr = curses.A_REVERSE if i == cur else curses.A_NORMAL
                stdscr.addnstr(y, 0, mark + names[i] + tag, max(0, w - 1), attr)
                y += 1
            stdscr.addnstr(h - 1, 0, "共 %d 个模型" % len(names), max(0, w - 1))
        except curses.error:
            pass
        stdscr.refresh()
        c = stdscr.getch()
        if c == curses.KEY_RESIZE:
            continue
        if c in (curses.KEY_UP, ord("k"), ord("K")):
            cur = (cur - 1) % len(names)
        elif c in (curses.KEY_DOWN, ord("j"), ord("J")):
            cur = (cur + 1) % len(names)
        elif c in (10, 13, curses.KEY_ENTER):
            return names[cur]
        elif c in (ord("q"), ord("Q"), 27):
            return None


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

    # 启动 TUI 时自动读取一次模型列表。失败不影响手动填写模型。
    stdscr.erase()
    try:
        stdscr.addstr(0, 0, "正在从兼容端点获取模型列表…")
        stdscr.refresh()
    except curses.error:
        pass
    model_names, model_error = fetch_models(
        vals["ZAI_API_URL"], vals["ZAI_API_KEY"], vals["ZAI_TIMEOUT"]
    )
    model_status = (
        "已获取 %d 个模型；在“模型”项按 Enter 选择，r 可刷新。" % len(model_names)
        if model_names else model_error + "；模型仍可手动填写，r 可重试。"
    )

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
        title = "zsh-chat-ai 配置   ↑/↓ 移动 · Enter 编辑/选择 · r 刷新模型 · s 保存 · p 人设 · q 退出"
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
            stdscr.addnstr(h - 3, 0, model_status, w)
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
                if k in ("ZAI_API_URL", "ZAI_API_KEY"):
                    model_names, model_error = fetch_models(
                        vals["ZAI_API_URL"], vals["ZAI_API_KEY"], vals["ZAI_TIMEOUT"]
                    )
                    model_status = (
                        "已自动刷新 %d 个模型；在“模型”项按 Enter 选择。" % len(model_names)
                        if model_names else model_error + "；模型仍可手动填写。"
                    )
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
                elif k == "ZAI_MODEL" and model_names:
                    selected = model_page(stdscr, model_names, vals[k])
                    if selected:
                        vals[k] = selected
                        model_status = "已选择模型: " + selected
                else:  # 文本 / 数字 / 密钥 → 进入编辑
                    editing = True
                    buf = vals[k]
            elif c in (ord("r"), ord("R")):
                stdscr.erase()
                try:
                    stdscr.addstr(0, 0, "正在刷新模型列表…")
                    stdscr.refresh()
                except curses.error:
                    pass
                model_names, model_error = fetch_models(
                    vals["ZAI_API_URL"], vals["ZAI_API_KEY"], vals["ZAI_TIMEOUT"]
                )
                model_status = (
                    "已获取 %d 个模型；在“模型”项按 Enter 选择。" % len(model_names)
                    if model_names else model_error + "；模型仍可手动填写。"
                )
            elif c in (ord("e"), ord("E")) and order[cur] == "ZAI_MODEL":
                editing = True
                buf = vals[order[cur]]
            elif c in (ord("s"), ord("S")):
                save = True
                break
            elif c in (ord("p"), ord("P")):
                if persona_page(stdscr):   # 人设页有改动 → 回到保存流程统一落盘
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
