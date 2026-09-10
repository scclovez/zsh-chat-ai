#!/usr/bin/env zsh
# =============================================================================
# zsh-chat-ai 安装/卸载脚本 (幂等, 不破坏 .zshrc 其它内容; 移动目录后可修复路径)
#
#   zsh install.zsh                # 默认: source 模式 —— 在 ~/.zshrc 末尾追加托管块
#   zsh install.zsh --mode plugin  # 插件模式 —— 软链到 oh-my-zsh 并加入 plugins=()
#   zsh install.zsh --uninstall    # 卸载(两种模式都移除)
#   zsh install.zsh --dry-run      # 只打印将要做什么
# =============================================================================

# --- 解析参数 ---
MODE=source
ACTION=install
DO=0
for a in "$@"; do
  case $a in
    --mode) ;;
    source|plugin) MODE=$a ;;
    --uninstall) ACTION=uninstall ;;
    --dry-run) DO=1 ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0 ;;
    *) print -u2 -r -- "未知参数: $a (支持 --mode source|plugin / --uninstall / --dry-run)"
       exit 2 ;;
  esac
done

# --- 路径 ---
ZDOT=${ZDOTDIR:-$HOME}
ZRC=$ZDOT/.zshrc
PLUGIN_DIR=${0:A:h}                       # 本脚本所在目录的绝对路径
PLUGIN_FILE=$PLUGIN_DIR/zsh-chat-ai.plugin.zsh
OMZ_CUSTOM=${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}
LINK_DIR=$OMZ_CUSTOM/plugins/zsh-chat-ai
BEGIN_MARK='# ===== zsh-chat-ai (managed by install.zsh) ====='
END_MARK='# ===== end zsh-chat-ai ====='

[[ -f $PLUGIN_FILE ]] || { print -u2 -r -- "找不到 $PLUGIN_FILE"; exit 1; }

# 幂等: 判断完整托管块是否已存在于 .zshrc
has_block() { [[ -f $ZRC ]] && grep -Fq "$BEGIN_MARK" "$ZRC" && grep -Fq "$END_MARK" "$ZRC"; }
# 幂等: plugin 模式软链是否已存在且指向本目录
has_link()   { [[ -L $LINK_DIR ]] && [[ $(readlink "$LINK_DIR") == "$PLUGIN_DIR" ]]; }

say() { print -r -- "install.zsh: $*"; }
warn(){ print -u2 -r -- "install.zsh: 警告: $*"; }

dry_or_do() {  # 传入要执行的命令; --dry-run 时只回显
  if (( DO )); then
    print -r -- "   [dry-run] $*"
  else
    eval "$*"
  fi
}

block_text() {
  print -r -- "$BEGIN_MARK"
  print -r -- "ZAI_PLUGIN_DIR=\"$PLUGIN_DIR\""
  print -r -- '[[ -f "$ZAI_PLUGIN_DIR/zsh-chat-ai.plugin.zsh" ]] && source "$ZAI_PLUGIN_DIR/zsh-chat-ai.plugin.zsh"'
  print -r -- "$END_MARK"
}

# 用当前目录重写托管块。仓库移动后，旧的绝对路径会在此被修正。
rewrite_source_block() {
  local tmp line
  local -i in_block=0 seen=0
  tmp=$(mktemp "${ZRC}.zai.XXXXXX") || { warn "无法创建临时文件以更新 $ZRC"; return 1; }
  while IFS= read -r line || [[ -n $line ]]; do
    if [[ $line == "$BEGIN_MARK" ]]; then
      (( seen += 1 ))
      block_text >> "$tmp"
      in_block=1
      continue
    fi
    if (( in_block )); then
      [[ $line == "$END_MARK" ]] && in_block=0
      continue
    fi
    print -r -- "$line" >> "$tmp"
  done < "$ZRC"
  if (( seen != 1 || in_block )); then
    rm -f "$tmp"
    warn "托管块格式异常，未修改 $ZRC。"
    return 1
  fi
  mv "$tmp" "$ZRC"
}

ensure_trailing_newline() {
  # 保证文件末尾有换行, 避免追加内容粘到上一行
  [[ -s $ZRC ]] || { print -r -- "" > "$ZRC"; return; }
  [[ -n $(tail -c1 "$ZRC") ]] && print -r -- "" >> "$ZRC"
}

install_source_mode() {
  if has_block; then
    say "更新 $ZRC 中的托管块，确保指向当前目录: $PLUGIN_DIR"
    if (( DO )); then
      print -r -- "   [dry-run] 将把已有托管块改为:"
      print -r -- "$(block_text)" | sed 's/^/      /'
    else
      rewrite_source_block || return 1
    fi
    return 0
  fi
  say "在 $ZRC 末尾追加托管块 (source 模式)。"
  if (( ! DO )); then
    [[ -f $ZRC ]] || { warn "$ZRC 不存在, 将创建。"; : > "$ZRC"; }
    ensure_trailing_newline
    block_text >> "$ZRC"
  else
    print -r -- "   [dry-run] 将追加:"
    print -r -- "$(block_text)" | sed 's/^/      /'
  fi
  return 0
}

uninstall_source_mode() {
  if ! has_block; then
    say "source 模式的托管块不存在, 无需移除。"
    return 0
  fi
  say "移除 $ZRC 中的 zsh-chat-ai 托管块。"
  dry_or_do "awk -v b='zsh-chat-ai (managed by install.zsh)' -v e='end zsh-chat-ai' 'index(\$0,b){skip=1} !skip{print} index(\$0,e){skip=0}' \"$ZRC\" > \"$ZRC.tmp\" && mv \"$ZRC.tmp\" \"$ZRC\""
  return 0
}

install_plugin_mode() {
  if has_link; then
    say "软链 $LINK_DIR -> $PLUGIN_DIR 已存在。"
  elif [[ -L $LINK_DIR ]]; then
    say "更新旧软链 $LINK_DIR -> $PLUGIN_DIR"
    dry_or_do "ln -sfn \"$PLUGIN_DIR\" \"$LINK_DIR\""
  else
    if [[ -e $LINK_DIR || -L $LINK_DIR ]]; then
      warn "$LINK_DIR 已存在但不是指向本目录, 不覆盖。可先 --uninstall 或手动删除。"
      return 1
    fi
    say "创建软链 $LINK_DIR -> $PLUGIN_DIR"
    dry_or_do "mkdir -p \"$OMZ_CUSTOM/plugins\" && ln -sfn \"$PLUGIN_DIR\" \"$LINK_DIR\""
  fi
  # 往 plugins=(...) 加入 zsh-chat-ai (保持 zsh-syntax-highlighting 在最后)
  if [[ -f $ZRC ]] && grep -qE 'plugins=\([^)]*\)' "$ZRC"; then
    if grep -qE 'plugins=\([^)]*zsh-chat-ai[^)]*\)' "$ZRC"; then
      say "plugins=(...) 已包含 zsh-chat-ai。"
    else
      say "把 zsh-chat-ai 加入 plugins=(...) (syntax-highlighting 保持最后)。"
      dry_or_do "python3 - \"$ZRC\" <<'PY'
import re,sys
p=sys.argv[1]
s=open(p,encoding='utf-8').read()
def repl(m):
    inner=m.group(0)
    toks=re.findall(r'[^ \\t()]+', inner.replace('plugins=','').strip('()'))
    if 'zsh-chat-ai' in toks:
        return inner
    drop={'zsh-chat-ai','zsh-syntax-highlighting'}
    toks=[t for t in toks if t not in drop]
    toks.append('zsh-chat-ai')
    toks.append('zsh-syntax-highlighting')
    return 'plugins=(' + ' '.join(toks) + ')'
s2,n=re.subn(r'plugins=\\([^)]*\\)', repl, s, count=1)
open(p,'w',encoding='utf-8').write(s2 if n else s)
print(('updated' if n else 'not-found')+': plugins line')
PY"
    fi
  else
    warn "在 $ZRC 中找不到 plugins=(...), 跳过 plugin 列表修改; 请手动把 zsh-chat-ai 加入 plugins 数组。"
  fi
  return 0
}

uninstall_plugin_mode() {
  if [[ -L $LINK_DIR || -e $LINK_DIR ]]; then
    say "删除软链/目录 $LINK_DIR"
    dry_or_do "rm -rf \"$LINK_DIR\""
  else
    say "无 $LINK_DIR, 跳过。"
  fi
  # 从 plugins=(...) 移除 zsh-chat-ai
  if [[ -f $ZRC ]] && grep -qE 'plugins=\([^)]*zsh-chat-ai[^)]*\)' "$ZRC"; then
    say "从 plugins=(...) 移除 zsh-chat-ai。"
    dry_or_do "python3 - \"$ZRC\" <<'PY'
import re,sys
p=sys.argv[1]
s=open(p,encoding='utf-8').read()
def repl(m):
    toks=re.findall(r'[^ \\t()]+', m.group(0).replace('plugins=','').strip('()'))
    toks=[t for t in toks if t!='zsh-chat-ai']
    # 保持原顺序(不再强推 syntax-highlighting 到末, 仅移除)
    return 'plugins=(' + ' '.join(toks) + ')'
s2=re.sub(r'plugins=\\([^)]*\\)', repl, s, count=1)
open(p,'w',encoding='utf-8').write(s2)
print('removed zsh-chat-ai from plugins')
PY"
  fi
  return 0
}

# --- 主流程 ---
if (( DO )); then say "----- dry-run 模式, 不会真正改动 -----"; fi

if [[ $ACTION == uninstall ]]; then
  uninstall_source_mode
  uninstall_plugin_mode
else
  case $MODE in
    source) install_source_mode ;;
    plugin) install_plugin_mode ;;
  esac
fi

say "完成。重开一个终端 (或执行: exec zsh) 生效。"
say "入口命令: ai <自然语言>    例如: ai 把时区改成上海"
(( DO )) && exit 0
exit 0
