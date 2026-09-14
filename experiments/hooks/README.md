# Codex hook 最小验证记录

日期：2026-09-14。本目录是探针，不是正式安装配置。

> 下文是最初隔离探针的历史记录。后续已安装项目集成，并通过 app-server 只读诊断确认两项 hook 均为 untrusted、MCP 七项工具可发现；当前依据见 [工作流实测](../workflow/README.md)。不再将下文“没有安装实际 hooks”视为当前状态。

## 已观察到

- 本机 `codex --version`：`codex-cli 0.152.0`。
- `codex features list`：`hooks stable true`。
- CLI 帮助提供 `--ignore-user-config`、`--ephemeral` 和单次 hook trust 参数。
- 官方 https://developers.openai.com/codex/hooks 的原文返回说明 `PostToolUse` 支持 JSON `hookSpecificOutput.additionalContext`，plain stdout 不作为该事件的上下文。

## 一次实际探针结果

使用命令行临时 hook 定义，在子目录 workspace 中启动独立只读 CLI。不更改全局或项目 hook 配置。`--ignore-user-config` 不代表隔离所有插件或系统配置；本次仍观察到插件加载警告。

模型请求超时，并在回退请求中收到 401（Missing bearer or basic authentication）。未进入所需工具调用，未获得 hook 触发或模型收到 token 的证据。按用户要求停止前置排障，没有改认证或持续重试。

最初探针的 Windows 子进程超时清理存在不足，独立审查后改为直接重定向日志、等待 70 秒并清理本次进程树。修订版仅作静态检查，未再次发起模型调用。

## 结论

- 本地 runtime 的 hook JSON 输出与去重行为有自动测试。
- CLI 和桌面端真实 hook 送达均仍未验证。
- 没有安装实际 hooks；不能声称已经自动巡查当前会话。
- 下次有可用独立 CLI 认证时再运行一次 `python experiments/hooks/run_probe.py`。该命令会使用模型服务，并对本次调用跳过 hook 信任确认；运行前应检查活动 hook 来源。正式接入应采用正常宿主信任流程。

