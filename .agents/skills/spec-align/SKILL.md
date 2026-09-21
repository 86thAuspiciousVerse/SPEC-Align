---
name: spec-align
description: Maintain explicit Markdown requirements and design dependencies with the Spec Align CLI. Use when creating or changing managed spec documents, incorporating exploration findings, or responding to Spec Align review reminders.
---

# Spec Align 文档维护

用自然语言作判断，用 runtime 记录身份、依赖和版本依据。runtime 不理解语义，也不会补全漏掉的依赖。

## 确定项目与工具

使用目标项目的绝对路径作为 `--root`，它不一定是当前 shell 目录或 skill 所在仓库。CLI 必须已安装；若不可用，报告未完成检查，不伪造输出，也不更改全局配置。

读取目标根目录 `specalign.yaml` 的 roots/exclude，默认只管理 `spec/**/*.md`。仅在当前任务要求建立受管文档时运行 `specalign --root <root> init`。不要批量迁移全部 Markdown。普通文档与历史材料可以保持未纳管。

## 写重要结论

为影响实现、跨文档复用或需要追溯的重要结论设置稳定 ID；移动文件或改标题不要换 ID。条目用独立行的 HTML 注释包围；代码围栏中的示例不算声明：

```markdown
<!-- spec
id: DESIGN-LOCAL-STORAGE
status: active
depends_on:
  - REQ-OFFLINE
references: []
-->

采用本地存储完成离线操作。

<!-- /spec -->
```

协议接受 `id/status/depends_on/references/supersedes/challenges/kind/scope`。kind/scope 为非空字符串，缺省 scope 为 project。ID 使用 ASCII 字母开头，后续可用字母、数字、下划线和连字符。状态为 `proposed/active/retired`。

- 判断依赖：如果 A 改变，B 可能需要重新检查，就由 B 声明 `depends_on: [A]`。修改方案时重新检查依赖，也可删除不再成立的依赖。
- `references` 表示背景或出处，只检查目标存在，不传播复核。目标同样需要显式条目 ID；普通网页/文档路径写普通 Markdown 链接，不塞进 ID 列表。
- 有效条目只依赖有效条目。新建议先标 `proposed`；仅在已有用户授权范围内采纳为 `active`。不要求简单项目每项工程决策都另行审批。
- `supersedes` 指向拟替代条目，只有采纳才生效；目标须同 scope，不能出现多个已采纳直接继任者。`challenges` 记录对现行决定的挑战，不自动覆盖它。
- 采纳使用 `accept ID --snapshot TOKEN --actor NAME --reason TEXT`；退役使用同参数的 `retire`。新方案生效后检查仍引用旧项的下游。retired 表示曾采纳后退役，不能把未采纳候选以此标记并保留 supersedes。

探路结论归并时区分证据、建议与现行决定。若建议触及已确认的产品约束，先明确取舍，不能因报告较新就覆盖旧需求。subagent 的报告由当前任务负责者收口，不把建议自动变成已采纳决定。

## 检查与复核

完成一批编辑或收到提醒后执行：

```text
specalign --root <root> check
specalign --root <root> explain <item-id>
specalign --root <root> context <item-id>
specalign --root <root> impact <item-id>
```

`check` 返回当前快照与问题。`explain` 返回本条目和直接依赖的当前正文、选取的复核记录，以及相对该记录的差异；它优先选择适用于当前版本的记录，否则选择最近一条。没有记录时 `review:null`，需要初次检查。

先处理解析失败、重复 ID、断链、无效依赖和循环。`valid:true` 仅表示没有结构错误；`needs_review` 仍可能存在。

对于 `needs_review`，阅读当前条目、依赖和变化证据，判断仍兼容还是需要修改。先改内容，再重新获取快照。确认当前版本后提交：

```text
specalign --root <root> review <item-id> --snapshot <实际快照> --reason "具体检查了什么，以及为什么兼容"
```

不给尚未检查的内容登记复核；不通过直接改数据库或更新 hash 清除提醒。如果命令拒绝旧快照，重新获取差异并判断，不能只替换参数盲目重试。`upstream_pending` 优先处理链上的上游复核；不要求每个间接下游无条件重写。

检查类命令退出码 0 表示无达到门槛的问题，2 表示有问题（默认含 warning），3 表示执行/配置失败。`check --agent` 给短摘要，`check --fail-on error` 只以结构错误作为门槛。`review` 后仍可能因其他事项返回 2；这不等于本条复核没有写入，应读报告确认。`history ID` 可追溯复核与问题记录，backup/restore 用于保留账本，不直接删除数据库。

最后再检查一次，明确剩余事项与未纳管范围。检查通过不等于全部自然语言一致。`.specalign/` 含不可自动重建的复核账本，不能当缓存删除。

## 提醒边界

skill 自身不自动运行 hook。未配置或未验证宿主 hook 时，仍需要显式调用检查，不声称已自动巡查。`PostToolUse` 返回提醒 JSON，`Stop` 默认作警告，配置 stop_on_errors 后结构错误最多请求继续一次。安装集成使用显式 `install --codex`，不修改信任、认证或全局配置。MCP 可用时 spec_init/spec_check/spec_explain/spec_context/spec_impact/spec_history/spec_review/spec_decide/spec_review_batch/spec_migration_plan 对应同一核心；用工具返回的真实 snapshot，不发明 token。

MCP 可以在启动时绑定项目，也可以无参数启动为未绑定服务。未绑定服务启动时不扫描任何目录；先通过 shell 的 `pwd`/`Get-Location` 或当前任务已确认的工作区信息取得绝对路径，再把它作为每次项目工具调用的 `root`，需要建立项目时先调用 `spec_init(root=...)`。绑定或未绑定模式的成功结果都会带 `project_root`，必须核对它与当前目标项目一致；字段缺失或不一致时，不得调用 `spec_review`、`spec_decide` 或批量复核，改用 CLI 的显式 `--root <root>`。不要混用不同根目录的 snapshot。不要把相对路径、`$PWD` 或 `${workspaceFolder}` 当作 MCP root；MCP 不会替你展开这些变量。

## 0.3 紧凑工作流

MCP spec_check 默认 summary，不再返回全部 items 正文；单项采纳/复核返回精简回执。未绑定服务的每次调用都要带 `root`，绑定服务可省略。需要正文使用 explain/context 或 check(detail="full")。CLI check 为兼容旧脚本仍默认 full，可用 --detail summary 或 --agent。scope 只过滤显示，不取消项目级结构错误，注意 project_error_count/project_unresolved_count。

当前任务可调用 spec_context(items=[ID1, ID2], related=true)，不能同时提供 item 与 items。正文共享 max_chars 预算，max_items 限制条目数；检查截断和 omitted_items，未读到的依据不得复核。related 只增加目标一跳关系，不意味着完整全项目关系。

一次读完同一快照的一组依据后，可调用 spec_review_batch(snapshot=实际快照, reviews=[{"item":"ID1","reason":"具体理由"}, ...])。每项独立理由，最多200项；任一条目无效或快照改变则整批拒绝，不盲目换 token 重试。返回 batch_id，history 可查逐项审计。批量复核不等于批量采纳。

check(since_snapshot=已保存快照) 明确比较基线，返回 changed_ids/deleted_ids/change_affected_ids；没有基线时不要把待处理问题当作本次变更。scope 不是隔离项目，跨范围依赖仍需要检查。

替代之后用 spec_migration_plan(scope=可选范围) 查看仍依赖旧条目的迁移候选。candidate 只是声明的有效继任者，requires_judgment 永远为 true；检查 would_create_cycle 并阅读新旧契约后再决定换边、删边或重写。工具不自动修改文件，不保证候选语义兼容。

不要每次小编辑都主动全量 check。以任务开始、重大设计变化和阶段收口为检查时机，hook 提供额外提醒。复用了上游的具体参数或验收要求时，直接声明该依据，避免仅靠间接传播漏掉需更新的复述。

