# zsh-chat-ai

在 **kitty / zsh**（oh-my-zsh、powerlevel10k）终端里，用**中文说一句话**，让 AI 帮你完成系统配置和日常 shell 工作——不需要记快捷键、不需要背命令。

```
❯ ai 把时区改成上海
zai: 把系统时区设置为上海(Asia/Shanghai)，需要 sudo。
  [1] sudo timedatectl set-timezone Asia/Shanghai
zai: 执行? [y]全部 / [n]取消 / 编号(如 1 或 1-2)选择: y
zai> sudo timedatectl set-timezone Asia/Shanghai
```

## 它能做什么

- **说中文就行**：比如「看看磁盘空间」「把当前 git 分支推送到远程」「装个 htop」。
- **先展示、再执行**：AI 会先列出要运行的命令和说明，你确认后才逐条在**当前终端**里执行，所以 `cd`、`export`、`sudo` 等效果都是真的。
- **你说了算**：AI 只是帮你起草和执行，**最终决定权在你**。涉及删除、格式化等危险操作时会标 ⚠，还需要你再输入一次 `f` 才会执行。

## 安装

```sh
cd ~/Desktop/zsh-chat-ai
zsh install.zsh            # 写入 ~/.zshrc（幂等，可重复执行）
exec zsh                   # 或重开一个终端
```

前提：已安装 `curl`、`jq`，并且 `~/.zshrc` 里已导出 DeepSeek 的 API key（`DEEPSEEK_API_KEY`）。

其它命令：`zsh install.zsh --mode plugin`（装成 oh-my-zsh 插件）、`zsh install.zsh --uninstall`（卸载）。

## 使用方法

三种方式任选：

| 方式 | 操作 | 说明 |
|---|---|---|
| 显式入口（推荐） | `ai 帮我看看磁盘空间` | 自动分流：闲聊回文本，要动手则给命令（确认后执行） |
| 直接说（无前缀） | 直接输入 `看看磁盘空间够不够` 回车 | 自动拦截"不是命令"的句子走 AI |
| Agent 会话 | `ai chat` | 多轮会话：可闲聊，也能读文件/搜代码/执行命令/改代码（改动先看 diff） |
| 强制命令模式 | `ai run 帮我装个 htop` | 跳过闲聊判断，直接走命令流程 |
| 打开设置界面 | `ai -config` | 可视化修改 API 地址 / Key / 模型 / 各种开关 |

**执行时的确认**：AI 返回命令后会问：

```
执行? [y]全部 / [n]取消 / 编号(如 1 或 1-2)选择:
```

- `y`：全部执行；`n` 或直接回车：取消；`1 2` 或 `1-3`：挑几条执行。
- 含高风险命令时会标 ⚠，需要再输入 `f` 才执行。
- 中途某条命令出错时，会停下来问你是否继续。

> 小提示：如果句子的第一个词正好是个已存在的命令（如 `python 帮我统计…`），不会被自动拦截，请加上 `ai` 前缀。

## Agent 会话（`ai chat`）

在终端里和 AI 边聊边干活：会话**按目录自动续接**（换目录 = 换上下文），历史存在 `~/.config/zsh-chat-ai/sessions.d/`，`ZAI_SESSION=0` 可关闭记忆。

```
❯ ai chat
== zai agent 会话 ==
锚点目录: /home/me/proj   会话文件: ~/.config/zsh-chat-ai/sessions.d/sess-xxx.jsonl
zai❯ 帮我把 README 里 x 改成 y，然后跑一下测试
zai: 我先看一下相关代码。
   …（agent 多步执行：读文件→改文件前展示 diff 给你确认→执行命令）
```

- **能做什么**：闲聊、问答，也可以读文件 / 搜代码 / 执行命令 / 改代码 / 新建文件，多步直到完成或你叫停；
- **确认策略**：`read`/`grep`/`ls` 等只读操作自动执行；`shell` 沿用命令确认与危险命令门禁；**`edit`/`create` 改文件前先展示 diff，你按 y/N 决定**；
- **权限**：默认可修改你自己目录（`$HOME`）内的文件；`$HOME` 之外（系统级，如 `/etc`）**每次会弹"请求权限"**，同意才放行；
- 会话内斜杠命令：`/new` 清空重来 · `/hist` 看历史 · `/dir` 看锚点 · `/help` · `/quit` 退出；
- 单次使用：`ai chat 帮我看下这个报错`（不进会话界面）。

## 常用设置（可选，不设置也能用）

想调整时有两种办法：① 运行 `ai -config` 可视化修改（保存即生效）；② 在 `~/.zshrc` 里 `export` 后重开终端。

| 设置 | 默认 | 作用 |
|---|---|---|
| `ZAI_MODEL` | `deepseek-v4-flash` | 模型，可换 `deepseek-v4-pro` |
| `ZAI_INTERCEPT` | `1` | `0` = 关闭"直接输入中文"的自动拦截 |
| `ZAI_AUTO_CONFIRM` | `0` | `1` = 不再逐个问 y/N，直接执行（危险命令仍要确认） |
| `ZAI_DRY_RUN` | `0` | `1` = 只展示命令、绝不执行（试效果用） |
| `ZAI_STREAM` | `1` | 等待时实时把模型的思考内容显示在终端，出结果后自动清掉；`0` = 关闭流式 |
| `ZAI_SESSION` | `1` | `0` = 关闭"按目录续接会话"的记忆 |
| `ZAI_CMD` | `ai` | 显式入口的命令名（改名字防冲突） |

## 常见问题

- **转圈后报错 / 没反应**：多半是网络或 key 问题，检查 `curl -i https://api.deepseek.com/models` 能否连通。
- **报 `401/403`**：API key 不对，检查 `~/.zshrc` 里的 `DEEPSEEK_API_KEY`。
- **中文句子在终端里显示红色**：正常，那是语法高亮对"未知命令"的着色，回车后就会走 AI。
- **想换别的 AI 服务**：`ai -config` 里填任意 OpenAI 兼容的 API 地址和 Key 即可。
- **AI 返回的东西不合预期**：重新描述需求试试，或换更强的模型（`ai -config` 里改）。
- **看不到"思考内容"？** 需要支持推理/思考的模型（不返回 thinking 的模型等待时只显示"思考中…"）；想关掉实时思考显示可 `export ZAI_STREAM=0`。

## 安全说明

- 所有命令执行前都会展示给你确认，**你确认了才会运行**。
- API key 只用于请求头，调试日志会自动打码（`sk-...`）。
- 想彻底不用自动拦截：`export ZAI_INTERCEPT=0`（显式 `ai` 仍可用）。
