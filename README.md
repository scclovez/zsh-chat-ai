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
| 显式入口（推荐） | `ai 帮我看看磁盘空间` | 任何请求都用 `ai` 开头，最稳 |
| 直接说（无前缀） | 直接输入 `看看磁盘空间够不够` 回车 | 自动拦截"不是命令"的句子走 AI |
| 打开设置界面 | `ai -config` | 可视化修改 API 地址 / Key / 模型 / 各种开关 |

**执行时的确认**：AI 返回命令后会问：

```
执行? [y]全部 / [n]取消 / 编号(如 1 或 1-2)选择:
```

- `y`：全部执行；`n` 或直接回车：取消；`1 2` 或 `1-3`：挑几条执行。
- 含高风险命令时会标 ⚠，需要再输入 `f` 才执行。
- 中途某条命令出错时，会停下来问你是否继续。

> 小提示：如果句子的第一个词正好是个已存在的命令（如 `python 帮我统计…`），不会被自动拦截，请加上 `ai` 前缀。

## 常用设置（可选，不设置也能用）

想调整时有两种办法：① 运行 `ai -config` 可视化修改（保存即生效）；② 在 `~/.zshrc` 里 `export` 后重开终端。

| 设置 | 默认 | 作用 |
|---|---|---|
| `ZAI_MODEL` | `deepseek-v4-flash` | 模型，可换 `deepseek-v4-pro` |
| `ZAI_INTERCEPT` | `1` | `0` = 关闭"直接输入中文"的自动拦截 |
| `ZAI_AUTO_CONFIRM` | `0` | `1` = 不再逐个问 y/N，直接执行（危险命令仍要确认） |
| `ZAI_DRY_RUN` | `0` | `1` = 只展示命令、绝不执行（试效果用） |
| `ZAI_CMD` | `ai` | 显式入口的命令名（改名字防冲突） |

## 常见问题

- **转圈后报错 / 没反应**：多半是网络或 key 问题，检查 `curl -i https://api.deepseek.com/models` 能否连通。
- **报 `401/403`**：API key 不对，检查 `~/.zshrc` 里的 `DEEPSEEK_API_KEY`。
- **中文句子在终端里显示红色**：正常，那是语法高亮对"未知命令"的着色，回车后就会走 AI。
- **想换别的 AI 服务**：`ai -config` 里填任意 OpenAI 兼容的 API 地址和 Key 即可。
- **AI 返回的东西不合预期**：重新描述需求试试，或换更强的模型（`ai -config` 里改）。

## 安全说明

- 所有命令执行前都会展示给你确认，**你确认了才会运行**。
- API key 只用于请求头，调试日志会自动打码（`sk-...`）。
- 想彻底不用自动拦截：`export ZAI_INTERCEPT=0`（显式 `ai` 仍可用）。
