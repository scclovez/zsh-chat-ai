#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zsh-chat-ai 文件编辑助手 (agent 用)
用法(由插件调用, 一般不在终端手敲):
    python3 zai_tools.py edit --preview <文件> <edits.json>
    python3 zai_tools.py edit --apply   <文件> <edits.json>
    python3 zai_tools.py create --preview <文件>          # 内容从 stdin
    python3 zai_tools.py create --apply   <文件>
    python3 zai_tools.py clean <目录>

edits.json 结构: {"edits":[{"old":"唯一原文片段","new":"替换为"}, ...]}
规则:
  - 每个 old 必须在当前(依次应用后的)文本中恰好出现一次, 否则报错(带上下文);
  - old 全文匹配(含缩进/换行), 用于锚定与行级替换; new 可为 "" 表示删除;
  - --preview 只打印 unified diff 不落盘; --apply 落盘(先写 .tmp 再原子替换)。
返回码: 0=成功; 2=参数/文件错误; 3=内容不匹配(不落盘)。
"""
import difflib
import json
import os
import sys

MAX_DIFF = 4000  # 展示的 diff 行数上限(防止刷屏)


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def write_text(path, text):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + ".zaitmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def find_snippet(text, old, label):
    if old == "":
        sys.stderr.write("错误: old 片段为空(第 %s 处)\n" % label)
        return -1
    idx = text.find(old)
    if idx < 0:
        sys.stderr.write(
            "错误: 第 %s 处 old 片段在文件中找不到(片段前 60 字符):\n%r\n" % (label, old[:60]))
        return -2
    if text.find(old, idx + 1) >= 0:
        sys.stderr.write(
            "错误: 第 %s 处 old 片段在文件中出现多次, 需更长的锚点:\n%r\n" % (label, old[:80]))
        return -3
    return idx


def apply_edits(original, edits):
    text = original
    for i, e in enumerate(edits, 1):
        old = e.get("old", "")
        new = e.get("new", "")
        idx = find_snippet(text, old, "%d/%d" % (i, len(edits)))
        if idx < 0:
            return None
        text = text[:idx] + new + text[idx + len(old):]
    return text


def make_diff(path, before, after):
    a = before.splitlines(keepends=True)
    b = after.splitlines(keepends=True)
    lines = list(difflib.unified_diff(a, b, fromfile=path, tofile=path, n=3))
    if not lines:
        return ""
    lines = lines[:MAX_DIFF]
    if len(lines) >= MAX_DIFF:
        lines.append("... (diff 过长, 已截断)\n")
    return "".join(lines)


def load_edits(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("edits.json 读取失败: %s\n" % e)
        sys.exit(2)
    eds = obj.get("edits") if isinstance(obj, dict) else obj
    if not isinstance(eds, list) or not all(
            isinstance(x, dict) and "old" in x and isinstance(x.get("new", ""), str) for x in eds):
        sys.stderr.write("edits.json 结构应为 {\"edits\":[{\"old\":..,\"new\":..},...]}\n")
        sys.exit(2)
    return eds


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("用法见文件头注释\n")
        sys.exit(2)
    mode = sys.argv[1]  # edit | create | clean
    if mode == "clean":
        # 清理自己的临时文件
        import glob
        for pat in ("*.zaitmp",):
            for p in glob.glob(os.path.join(sys.argv[2] if len(sys.argv) > 2 else ".", pat)):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return
    if len(sys.argv) < 3:
        sys.stderr.write("缺少参数\n")
        sys.exit(2)
    action = sys.argv[2]  # --preview | --apply
    if mode == "edit":
        if len(sys.argv) < 5:
            sys.stderr.write("edit 需要 <文件> <edits.json>\n")
            sys.exit(2)
        path = sys.argv[3]
        if not os.path.isfile(path):
            sys.stderr.write("文件不存在: %s\n" % path)
            sys.exit(2)
        original = read_text(path)
        after = apply_edits(original, load_edits(sys.argv[4]))
        if after is None:
            sys.exit(3)
        diff = make_diff(path, original, after)
        if action == "--preview":
            sys.stdout.write(diff)
        else:
            write_text(path, after)
            sys.stdout.write(diff)
            sys.stdout.write("OK: 已写入 %s\n" % path)
        return
    if mode == "create":
        path = sys.argv[3]
        content = sys.stdin.read()
        if action == "--apply":
            write_text(path, content)
            sys.stdout.write("OK: 已创建 %s (%d 字节)\n" % (path, len(content.encode("utf-8"))))
        else:
            new = ("+++ %s\n@@ -0,0 +1,%d @@\n" % (path, content.count("\n") + 1)) + \
                "".join("+" + l for l in content.splitlines(keepends=True))
            sys.stdout.write(new[:MAX_DIFF])
        return
    sys.stderr.write("未知命令: %s\n" % mode)
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
    except KeyboardInterrupt:
        sys.exit(130)
