# 个人开发流程实测（2026-09-14）

结论更新：**文档管理、当前会话原生 MCP、新 CLI 的自动提醒及清零后静默已实测通过；当前桌面会话 PostToolUse 仍未观察到触发。** 下面保留分阶段证据，以末尾最新结果为准。 本次没有实现笔记软件，仅以其需求、探路和里程碑模拟开发中的文档演进。

## 配置与调用方式

工作区已有 `.agents/skills/spec-align/SKILL.md`、`.codex/config.toml` 中 specalign MCP 服务以及 `.codex/hooks.json`。CLI 的配置发现能列出 specalign，但当前模型工具清单没有 Spec Align 工具。

因此本次使用 `mcp_call.py` 读取该工作区真实 MCP 配置，以官方 ClientSession 启动 stdio 子进程；主 agent 通过它逐次调用工具并阅读结果。它不是 Codex 原生工具分发，也不是自动化语义审查器，不包含自动复核逻辑。

调用示例（PowerShell）：

```powershell
'{"tool":"spec_context","arguments":{"item":"LAB-MILESTONE-STORAGE"}}' | python experiments/workflow/mcp_call.py
```

请求与完整返回写入本地 `.specalign/workflow-lab/mcp.jsonl`。该文件不提交，包含真实快照、审查理由、变化证据及错误返回。语义判断由本轮主 agent 作出，探路由只读 subagent 提供，主 agent 归并；并非让脚本自动刷审查记录。

## 实际经过

| 步骤 | 动作 | 观察结果 |
| --- | --- | --- |
| 初始需求 | 离线、单用户单进程；JSON 设计依赖需求，存储里程碑依赖设计 | 两个依赖条目首次需复核；阅读内容后通过 MCP 记录复核 |
| 需求演进 | 改为两个独立进程编辑不同笔记，仍离线 | 文件编辑后未收到自动 hook 提醒，delivery 表仍为空 |
| 证据查询 | 主动调用 MCP explain | 返回原单进程需求、新双进程需求及 diff，旧复核不再匹配 |
| 手工通道检查 | 用已安装 hook 命令注入 PostToolUse 两次 | 首次返回设计 needs_review 与里程碑 upstream_pending；第二次返回空对象。此处仅为手工协议检查 |
| subagent 探路 | 分析 JSON 整体重写风险，建议本地 SQLite | 主 agent 将探路写为 proposed，声明 challenges；新设计声明 supersedes，旧设计仍有效 |
| 采纳新方案 | 通过 spec_decide 先采纳探路，再采纳 SQLite 设计 | 原 JSON 被有效替代；旧里程碑出现 inactive_dependency，不能继续冒充有效依据 |
| 更新计划 | 原里程碑保留 ID，改依赖 SQLite，补并发与锁竞争验收 | 结构恢复有效，设计及里程碑仍需显式复核 |
| 拒绝旧依据 | 故意提交最初 JSON 阶段快照 | MCP 返回 isError，拒绝旧快照；辅助客户端以退出码 3 报告 |
| 收口 | 阅读当前上下文后分别复核新设计与里程碑 | findings 为空，history 保留采纳与问题 open/resolved 历史，无 pending operation |

初始快照：`e3a7577e32c9d4e528161ee6d731dd5195af4a6093a57552b62a0cd3b047ccc4`。

最终快照：`8d8d0587d5ef354244d559017c913de358cb354d65b2dfaad8a3e3d7672e373d`。

最终示例保留在 `spec/workflow-lab/`，scope 与 ID 前缀明确隔离，但由工作区同一个 runtime 管理。旧 JSON 正文没有删除，有效状态由已采纳的替代关系决定。Git 克隆不携带审查账本，届时首次复核提示是正常行为。

## 自动化缺口与下一步

本轮受管文件修改之后没有额外 hook 上下文，delivery 表也没有宿主 session 记录。最终唯一记录为 `manual-workflow-protocol:PostToolUse`，是手工测试写入；不能把它作为自动触发证据。尚未定位到具体是当前会话配置未加载、信任未完成，还是桌面宿主的事件路径问题。

官方 [Hooks 文档](https://developers.openai.com/codex/hooks) 要求项目层可信，且非托管 hook 的具体定义经过 review/trust；可在 CLI `/hooks` 检查。工具没有设置或绕过信任。

下一次宿主验收：

1. 在此工作区打开 Codex 的 MCP/配置界面，确认 specalign 服务；若当前会话仍不暴露工具，重新加载配置或重开会话后核对，不把“配置存在”当作成功。
2. 在支持 `/hooks` 的 Codex CLI 中检查项目与两个 Spec Align hook 的信任状态，按宿主流程审阅。桌面和 CLI 结果分别记录，不能相互代替。
3. 模型先通过原生 spec_context 读取 LAB-MILESTONE-STORAGE；确认工具确实出现在模型可调用清单。
4. 用户提出一次模拟需求变更（例如双进程变三进程）。agent 只编辑 LAB-REQ-OFFLINE，随后进行一次无关读取，暂不主动调用 Spec Align。
5. 验收是否自动出现 needs_review/upstream_pending，并有非 manual 的 delivery 记录；之后按 skill 复核、确认提醒解除。没有触发就沿配置加载 → 信任 → 命令执行 → additionalContext 送达逐层定位。

当前 verdict：手动/MCP 辅助工作流通过；无人记忆依赖的自动巡查验收未通过，不能对外称为全自动可用。

## 后续宿主诊断：已定位信任阻塞

同日继续测试，使用本机 Codex CLI 0.152.0 生成的 app-server JSON schema，按其协议启动全新 stdio app-server。只执行 initialize、hooks/list 和 mcpServerStatus/list，无模型请求，不设置 hook 信任，也不改认证。

实际返回：

- 两个 hook 均来自当前项目 `.codex/hooks.json`，enabled=true，解析错误数为 0；两者 trustStatus 均为 **untrusted**。
- 新 app-server 的 MCP 工具清单包含 spec_check、spec_context、spec_decide、spec_explain、spec_history、spec_impact、spec_review 全部七项。
- 这证明新 CLI 宿主能加载 MCP 并发现工具，超出了独立 MCP 客户端握手验证；但没有证明当前桌面会话的工具清单更新，也没有证明模型已使用 MCP。
- 官方规则下 untrusted hook 会被跳过，因此该信任状态是已确认的阻塞项。需用户在 `/hooks` 正常审阅两项定义后再进行自动提醒测试；不绕过信任来伪装正式接入成功。

可重复执行：`python experiments/workflow/host_diagnostic.py`。每个 RPC 最多等待 25 秒，结束时清理本次子进程；报告仅输出 Spec Align hook 元数据和工具名，不输出其他 MCP 配置或凭据。本地证据保存在 `.specalign/diagnostics/host-status.json`。

## 信任后的真实送达验收

用户正常信任两项 hook 后，hooks/list 均返回 trusted，hash 未变；当前桌面模型工具清单也出现七项原生 MCP，已直接调用 spec_check、spec_explain、spec_context、spec_review 成功，不再依赖辅助客户端。

将模拟需求由两个改成三个进程，先执行文件编辑及无关读取，不调用检查。当前桌面会话没有自动提醒，也没有新增 delivery 行；其 PostToolUse 仍未验证成功。

随后启动使用正常配置、已信任项目 hooks 的只读 `codex exec --ephemeral`，未忽略用户配置、未绕过信任、未改认证。探针只要求执行 `Write-Output READY` 并报告任何自动提醒，不提供问题 ID 或快照，不允许读取文档或主动调用 Spec Align。

- 首次尝试没有可核验的工具执行，仅自动 Stop 有账本记录，不计为 PostToolUse 成功。
- 第二次 CLI 会话 `01a09c0f-6ad7-7ef2-9cf5-856bda2c2f22` 实际执行命令，输出 READY、退出 0；随后模型准确引用 needs_review（LAB-DESIGN-SQLITE、LAB-EXP-MULTIPROCESS）、upstream_pending（LAB-MILESTONE-STORAGE）以及快照 `f95e0a40376f4e9bd250ac607383c6ed8fa79f26f8a9b971caca0cf0afa135f9`。账本同时存在该 session 的 PostToolUse 与 Stop 自动记录。这是模型实际收到提醒的证据。
- 主 agent 通过当前会话原生 MCP 阅读依据。探路及 SQLite 设计仍兼容三进程目标；里程碑直接复用了需求数量，因此补上对 LAB-REQ-OFFLINE 的直接依赖，并更新三进程验收。这说明漏声明依赖仍需 agent 语义判断。
- 主 agent 提交三条有理由的原生 MCP 复核，findings 清零。最终快照 `278b0b4160ec950c7194c98d456a72233529e76383df32f57488b8018b9bd37e`。
- 清零对照 CLI 会话 `01a09c10-b778-7561-91fa-a315678f8db2` 同样实际输出 READY、退出 0，两个 hook 均有自动调用记录，模型报告没有 Spec Align 提醒。

原始日志留在 `.specalign/diagnostics/trusted-cli-retry.jsonl` 与 `trusted-cli-clean.jsonl`，信任证据在 host-status.json。日志未提交。旧认证错误和 untrusted 记录仅描述历史阶段，不再作为当前阻塞原因。

验收范围：CLI 自动触发及模型送达通过、当前桌面原生 MCP 通过、主 agent 有依据复核通过。没有声称单个无人干预 CLI agent 自主修复整个链路，也没有声称桌面 PostToolUse、subagent 编辑覆盖或 Stop 阻塞模式已完成真实验收。

