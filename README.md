# Code Agent Runtime

一个面向代码仓库任务的、可测试的 Python Code Agent Runtime。

它将单 Agent 工具调用、多 Agent 任务 DAG、长期记忆、MCP 工具接入、Git worktree 隔离、只读代码审查与显式合并审批组合为一个可恢复的本地运行时。

## 能力

- 工作区受限的文件读取、搜索、编辑与命令执行
- 工具权限策略、命令超时与结构化工具结果
- 多轮 LLM Tool Calling Agent Loop
- 文件型长期记忆与 MCP 动态工具注册
- LLM 驱动的 JSON Task DAG 规划与依赖调度
- 独立 SubAgent 上下文和 checkpoint/resume
- 写任务的 Git worktree / 分支隔离
- 只读 Review Agent、diff 指纹校验和显式审批合并

## 安装

```bash
python -m pip install -e .
```

配置模型：

```bash
# PowerShell 示例
$env:ANTHROPIC_API_KEY = "..."
$env:MODEL_ID = "..."
```

也支持通过 `ANTHROPIC_BASE_URL` 连接兼容网关。

## 单 Agent

```bash
code-agent "检查并修复测试失败" --workspace /path/to/repository --allow-execute
```

## 多 Agent Git 工作流

目标仓库必须是已有初始提交的 Git 仓库：

```bash
code-agent "修复失败测试，运行验证，并审查修改" \
  --workspace /path/to/repository \
  --workflow \
  --workflow-id fix-issue-42 \
  --allow-execute
```

默认只在隔离 worktree 中修改。只有审查 JSON 返回 `approved`、diff 指纹没有变化、主工作区干净，并且用户显式传入 `--merge-reviewed` 时，才会提交并合并该变更：

```bash
code-agent "..." --workspace /path/to/repository --workflow \
  --workflow-id fix-issue-42 --allow-execute --merge-reviewed
```

## 运行数据目录

默认情况下，虚拟环境、源码和所有 Agent 运行产物都归在本项目目录：`.venv/`、`code_agent/` 与 `runtime-data/`。`runtime-data/` 会按目标仓库隔离保存长期记忆、工作流 checkpoint、终端进度日志和 Git worktree；目标仓库不会再创建 `.code-agent/`，也不会在其同级目录创建 worktree 文件夹。

如需将运行产物放在其他单独目录，传入 `--runtime-dir`：

```powershell
code-agent "修复失败测试" --workspace D:\path\to\repository --workflow `
  --workflow-id fix-issue-42 --allow-execute `
  --runtime-dir D:\code\learn-claude-code\code_agent\runtime-data
```

一次运行的终端进度会同时写入：`runtime-data/<目标仓库名-哈希>/logs/<workflow-id>.log`；同一位置的 `workflows/<workflow-id>.json` 是可恢复的完整检查点。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 限制

### 容器命令执行

传入 `--execution-backend docker --sandbox-image python:3.12-slim` 可把 `run_command` 和 `run_tests` 放到 Docker 中执行。需自行安装并启动 Docker，预先拉取镜像（运行时使用 `--pull=never`）。容器禁止网络、使用只读根文件系统、移除 capabilities、限制 CPU/内存/进程数，并只挂载当前任务工作区；超时会清理容器。镜像需要提供 `sh`，文件权限需允许 UID 65534 访问工作区。Docker 不可用时会报错，不会自动回退本地执行。默认 `local` 仍在宿主机执行。

### MCP 连接

运行 `uv sync --extra mcp` 安装官方 MCP Python SDK 1.x，再通过 `--mcp-config mcp-config.json` 加载服务器：

```json
{
  "servers": {
    "docs": {
      "transport": "stdio",
      "command": "python",
      "args": ["path/to/server.py"],
      "env_from": {"API_KEY": "DOCS_API_KEY"},
      "timeout_seconds": 30,
      "retry_safe_tools": ["lookup"]
    },
    "remote": {
      "transport": "http",
      "url": "https://example.com/mcp",
      "headers_from_env": {"Authorization": "MCP_AUTHORIZATION"}
    }
  }
}
```

凭据从指定环境变量读取；例如 `MCP_AUTHORIZATION` 的值包含 `Bearer ...`。每次操作建立并初始化会话，结束后释放连接；工具发现会处理分页。失败时工具发现可以重新连接一次，工具调用只有同时列入 `retry_safe_tools` 且服务器声明只读或幂等时才允许重试。副作用调用失败不自动重放，结果可能不确定，需检查服务器实际状态。此机制不提供跨进程 exactly-once，也不自动实现 OAuth 登录。stdio MCP 进程在宿主机运行，其权限不受 Docker 命令后端限制。

### 结构化 trace

`runtime-data/<仓库名-哈希>/traces/<workflow-id>.jsonl` 持久化带 UTC 时间和唯一 `run_id` 的事件，包含任务/步骤、规划及执行阶段的模型用量、模型重试、工具及 MCP 耗时、状态和错误类型。工具耗时同时进入 checkpoint。trace 不记录工具参数、输出或凭据；完整工具结果仍保存在 checkpoint。可传入 `--input-cost-per-million 2 --output-cost-per-million 8` 按自定义美元费率估算单次模型请求费用；未配置费率时费用为 null，缓存等差异化计费不在该估算中，结果不能替代服务商账单。

本地执行后端依赖 `shell=True` 和策略限制；需要命令隔离时显式选择 Docker 后端。MCP transport 使用官方 SDK，当前不提供跨进程幂等账本或自动 OAuth 授权。

[`15.py`](15.py) 是原始课程整合 Harness 的保留参考实现；当前可维护运行时位于 [`code_agent/`](code_agent/)。
