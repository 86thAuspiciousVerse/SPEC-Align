# Spec Align 文档协议与运行合同（0.2）

本文是已实现协议的当前定义。产品意图见根目录设计记录，实施验收见 `IMPLEMENTATION-PLAN.md`。协议不包含自然语言语义推断。

## 文档与条目

UTF-8 Markdown；单文件最大 2 MB。仅独立 HTML 注释块生效，代码围栏中的示例不生效；起止标记不可嵌套。标记未闭合、未知字段、重复 YAML 键、错误字段类型都报解析错误。

```markdown
<!-- spec
id: DESIGN-STORAGE
status: active
kind: design
scope: desktop
depends_on: [REQ-OFFLINE]
references: []
-->

正文为当前设计。

<!-- /spec -->
```

| 字段 | 规则 |
| --- | --- |
| id | 必需。ASCII 字母开头，后续字母、数字、下划线、连字符；全项目唯一 |
| status | 必需。proposed / active / retired |
| depends_on | 可选 ID 列表，成立依据；改变时复核 |
| references | 可选 ID 列表，背景出处；只验证存在性 |
| supersedes | 可选 ID 列表，拟替代或已替代的决定 |
| challenges | 可选 ID 列表，显式挑战；不自动选择解决方案 |
| kind | 可选非空字符串，仅作分类 |
| scope | 可选非空字符串，缺省 project；替代双方必须同范围 |

所有关系目标必须存在，列表不能重复。网页链接和普通文件路径写在正文，不填入 ID 列表。

条目正文、声明状态和结构字段参与版本 hash；位置不参与。整个扫描快照包含文件指纹、位置和配置，所以移动文档不使已有复核失效，但会使正在提交的旧扫描 token 失效。CRLF/LF 在正文解析时规范化。

## 生命周期

`proposed` 不覆盖任何现行决定。`accept ID --snapshot TOKEN --actor NAME --reason TEXT` 将候选条目变为 active；`retire` 仅将 active 变为 retired。命令原子替换目标文件的元数据块，记录操作意图及结果，不批量改写历史文档。操作者是自报身份，runtime 不验证其授权；agent 必须遵守已有用户授权。

已采纳（active 或 retired）条目的 supersedes 生效，被替代项返回 `effective_status: superseded`，原始 status 保留。retired 表示曾经采纳后退役，不能把被拒绝的候选标为 retired 并携带 supersedes；未采纳方案保留 proposed 或移至不受管的历史材料。

继任者退役不会使旧决定复活。多名已采纳继任者直接替代同一项为错误；应沿链继续替代。自替代、跨 scope 替代、supersedes 环为错误。active 条目依赖 superseded/retired/proposed 目标为错误，需要显式更新依据。正常替代可能让现有下游出现这一错误，这是需要收口的变更影响。

challenges 指向仍 active 的目标时产生 warning；它不改变目标效力。任何 active/retired 状态仍可手工编辑，但只有通过命令作出的采纳/退役才有操作审计记录。

## 复核与影响

active 且有 depends_on 的条目需要匹配自身版本与直接依赖版本集合的复核记录。初次声明依赖不等于完成复核。review 必须提供检查返回的全项目 snapshot 与非空理由；当前扫描结构无效或快照变化时拒绝。再次读取内容用于捕获审查过程中变化，不能锁住外部编辑器最后一瞬间的写入；后续扫描继续发现新变化。

A 变化使直接依赖 B 待复核；C 依赖 B 时可能显示间接 upstream_pending。B 确认兼容且无需修改后，C 不必无条件重审。普通 references 不传播，depends_on 的环为错误。

`explain` 选择匹配当前依据的历史记录，否则选择最近记录，提供当前与被审查正文差异。它不会审批。`context ID` 遍历显式 depends_on 上游，限制正文字符数并标记截断；位置、依赖和问题等元数据不计入正文预算。

## 扫描、问题与存储

扫描按内容 hash 缓存解析，不单靠 mtime/size。SQLite 事务串行化并发调用。解析错误保留旧快照，当前扫描返回无效；不将未知内容当成删除，也不因图不可用就把已有问题标为解决。

稳定问题 ID 包含规则、条目、目标和关系类型；问题解决/再次出现都保留历史。`history` 返回复核、采纳/退役、问题事件及未完成文件操作。文件替换和 SQLite 不是跨资源原子事务；中断后 pending operation 是需人工检查的审计线索，工具不会自动重写文档来猜测恢复。

`.specalign/state.sqlite3` 包含快照、复核与历史，不能当缓存删除。backup 使用 SQLite backup API；restore 验证 SQLite 完整性和基础表，只恢复到尚无数据库的目录，拒绝覆盖现有账本。文档由 Git/文件备份单独保存。0.1 数据表保留，新增表自动建立，解析缓存按协议版本失效。

## 配置

根目录 `specalign.yaml`：

```yaml
version: 1
roots: [spec]
exclude: []
remind_after: 8
stop_on_errors: false
```

roots 是项目内非隐藏文档目录，不能指向项目根或越界目录；接受并规范化 `./spec` 与分隔符。exclude 使用项目相对 POSIX 路径 glob。未知键拒绝。init 创建缺失目录和默认配置，不自动安装集成。

## 提醒与接入

PostToolUse 调用扫描，将当前问题经 JSON additionalContext 返回；不读 transcript/tool_response 或聊天。Codex 安装器将它配置为 `async=true`，因此工具结果先完成，提醒在后续安全点送达；它不能阻塞触发它的工具。以问题及相关版本去重，无变化不刷屏，默认每八次同类检查可再提醒。Stop 使用独立通知计数并保持同步，默认 UI 警告。stop_on_errors 启用后，结构错误可以请求继续，但 stop_hook_active=true 时不再次续回合；warning 不强制继续。

宿主 hook 不是完整执行隔离边界。安装配置、命令执行成功、模型确实收到提醒是不同证据。项目与 hook 信任需要正常宿主流程；工具不修改信任或认证。

Git gate 检查暂存的配置和 Markdown，不被工作区未暂存内容替代；只检查结构，不将本地 review 数据库当作 Git 内的审查证据。

MCP 服务支持两种启动模式：传入 `--root` 时绑定该项目；不传入时以未绑定模式启动，不在启动时扫描任何目录。未绑定模式的每次项目工具调用都必须提供绝对 `root`，需要建立项目时先调用 `spec_init(root=...)`。每个成功的 MCP 投影都带有 `project_root`，客户端必须核对它与当前项目绝对路径一致；缺失或不一致时不得提交 review/decide，应改用带显式 `--root` 的 CLI。不要把相对路径或 shell 变量当作 root；MCP 不会替客户端展开它们。跨项目使用 MCP 时可复用一个未绑定服务，或在目标项目中运行 `install --codex` 生成项目级绑定配置；全局固定到某个仓库的旧条目应停用。

## 输出与退出码

JSON 报告包含 schema_version、snapshot、valid、findings 等；valid 只表示无结构错误，不保证全部语义一致。未纳管文件明确列出。

- 0：命令成功；检查无达到门槛的问题。
- 2：检查存在问题；默认 warning 也计入，`check --fail-on error` 仅计结构错误。
- 3：配置、输入或执行失败。
- argparse 参数使用错误也返回 2，并输出参数说明。

hook 使用协议 JSON 返回，扫描失败通过 systemMessage 明示，不冒充清洁报告。MCP 使用标准 SDK stdio，工具错误通过 MCP isError；查询不改文档，但会刷新索引与问题历史。没有 LLM API 或模型依赖。

## 0.3 Agent 交互扩展

不改变 Markdown 字段。MCP spec_init 用显式 root 创建默认配置和受管目录，不扫描或覆盖已有配置；spec_check 默认 summary，detail=full 返回正文。未绑定服务的每个工具调用都需要绝对 root，绑定服务可以省略；成功结果带 project_root。CLI check/scan 保留 full 默认，提供 --detail summary、--scope、--since-snapshot、--limit。单项 MCP review/decide 为摘要回执，分别附 reviewed_ids/decision。旧客户端若依赖 items 应显式请求 full 或 context。

summary 包含 snapshot、valid、project_error_count、project_unresolved_count、unresolved_count、affected_ids、findings（默认20条，limit 1..200）、findings_omitted 和 item_count。affected_ids 是范围内待处理条目，不等于变更集合。scope 仅投影显示；valid 始终为全项目结果，CLI warning 门槛仍考虑全项目问题。完整 ID 列表可能较长，摘要不承诺固定字节上限。

since_snapshot 必须存在于本地账本且当前结构有效；未知基线或无效当前状态明确拒绝。按条目 version 比较，含删除和 scope 移动；文件移动/注释变更可能改变 snapshot 但不改变条目 version。change_affected_ids 是新旧依赖图的下游并集加 changed_ids；是保守影响范围，不意味着这些条目均需重写。

context 接受一个或多个显式 ID（最多20），CLI context ID1 ID2；MCP item 与 items 二选一。共享正文预算，最多 max_items 条（默认30，最大200），省略 ID 明示。related/--related 添加目标的一跳类型关系以及已选条目间关系（最多200边），不无限扩展。matching_review 仅指是否存在匹配版本记录，不是语义有效性保证。

spec_review_batch(snapshot,reviews) / CLI review-batch --snapshot TOKEN --file reviews.json：输入为1..200个 {item,reason}，不允许重复/空理由/非active目标。所有逐项审查记录和 review_batches 关联在同一 SQLite 事务内提交，二次扫描变化则整体回滚。batch_id 仅关联操作，不代替逐项理由；history 的 batches 可对应 review_sequence。外部编辑器不被事务锁住，提交后修改由后续扫描捕获。

spec_migration_plan(scope) / CLI migration-plan --scope：只读预演已采纳替代关系，返回直接依赖旧项的 active 条目、声明继任链、有效候选和换边循环检查。requires_judgment=true，applied=false；不改文件或审计决定，不推断遗漏依赖。批量accept、多文件回滚、全局账本、代码/测试关联均不在此扩展范围内。

## 0.4 变更摘要与影响查询

提供 since_snapshot 时，检查结果还返回 changed_items（新增/修改/删除、前后状态、实际改变的元数据字段或正文）、changed_proposed_count、downstream_impact（一个可追溯的 depends_on 链与变更源）、downstream_active_count 和 downstream_proposed_count。已改变的下游条目只列在 changed_items，downstream_impact 列其他受影响条目，避免重复。changed_items 与 downstream_impact 各最多返回 limit 项，超出分别计入 *_omitted；原有 changed_ids/change_affected_ids 保留完整 ID 列表。字段只描述可验证的文档差异和已声明的关系，不推断语义原因或要求所有提案复核。没有先前快照时，检查不能准确声称“本次改动”。hook 若观察到已纳管提案相对上次可解析扫描发生变化，会另外发一次简短提示，附带旧快照供进一步查询；当前结构无效时，先修复结构再运行 since_snapshot 查询。这不产生 needs_review，也不修改提案状态。

spec_impact(item) / CLI impact ID 默认返回精简的 depends_on 下游链、状态和数量，不带节点正文或全图边；limit（默认50、最大200）与 offset 支持分页，next_offset 为 null 表示结束。detail=full / CLI --detail full 显式返回原先的完整图；CLI graph 仍用于完整图导出。影响链是可能需要人检查的范围，不表示条目内容已失效。正文使用 spec_context/spec_explain 按需读取。
