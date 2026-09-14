> **历史归档 · 非当前规格**
> 归档日期：2026-09-14。本文已被后续讨论取代，仅供追溯，不作为当前实现依据。
> 当前设计入口：[SPEC-ALIGN-CURRENT.md](../../SPEC-ALIGN-CURRENT.md)。

# Spec Align 软件设计说明

## 1. 文档目的

本文定义 Spec Align 的产品边界、文档协议、软件架构和可执行的 MVP 方案。

Spec Align 解决的问题是：在使用 AI coding agent 开发软件时，需求、决策、设计、任务和讨论记录分散在多个 Markdown 文件中，修改其中一处后容易留下重复、过期、断裂或互相冲突的描述，导致后续 Agent 读取到不一致的上下文。

本文的目标不是规定一个“万能的 AI 文档自动改写器”，而是把问题拆成三部分：

1. 用稳定 ID 和引用关系把文档组织成可检查的图；
2. 用确定性程序发现结构、引用和变更传播问题；
3. 用 skill、命令返回值和 hooks 把问题直接送入 Agent 当前工作流。

语义判断和产品决策仍由用户或 Agent 提议、用户确认；确定性程序不擅自替用户选择冲突版本。

## 2. 产品定位

### 2.1 一句话定位

> 面向 AI 软件开发的、Agent-agnostic 的规格治理和一致性检查层。

### 2.2 它不是什么

- 不是一个新的 IDE；
- 不是把所有 Markdown 自动重写成同一份文档的同步器；
- 不是试图用规则表达全部自然语言语义的形式化验证器；
- 不是要求项目一次性完成大型需求分析的瀑布流程；
- 不是只服务于某一个 coding agent 的插件。

### 2.3 它是什么

- 一个本地优先的 CLI；
- 一个 Markdown 文档协议和目录约定；
- 一个构建规格依赖图的解析器；
- 一个可用于 pre-commit、CI 和 Agent skill 的检查器；
- 一个向 Agent 生成“当前任务所需上下文”的工具；
- 一组面向 Kiro、Spec Kit、OpenSpec、Codex、Claude Code、Cursor 等生态的适配接口。

## 3. 设计原则

### 3.1 单一事实源

一个具有规范权的事实只允许在一个位置定义。其他文档通过稳定 ID 引用它，而不是复制一份看起来相同的自然语言。

### 3.2 讨论、决策、规范分层

对话记录是证据，决策记录是授权，规范是事实源，设计和任务是派生视图。原始对话中的一句话不能自动获得规范权。

### 3.3 变更优先于全文重写

对于已有系统，变更应描述为 ADDED、MODIFIED、REMOVED 等 delta。Agent 需要看到相对当前基线的变化，而不是重新阅读和重写所有全文。

### 3.4 确定性优先，语义能力可插拔

重复 ID、悬空引用、循环依赖、过期引用、生成区块漂移等问题必须由确定性代码判断。自然语言潜在冲突可以被发现和聚类，但最终结论必须标记为需要决策。

### 3.5 Agent 读取检查结果，而不是依赖静默文件

`.specalign/findings.json` 是持久化产物，但主要交互是 `spec check --agent` 的直接返回值。阻塞问题通过非零退出码进入 Agent 当前上下文。

### 3.6 只自动修改机器拥有的内容

工具可以更新自己生成的索引、上下文和生成区块；不应未经明确命令重写用户的普通自然语言段落。

### 3.7 Git 友好、本地优先

核心状态应能在仓库中以可 diff 的文本和 JSON 表示，不依赖云端数据库。后续可增加跨仓库 spec store，但不能让 MVP 依赖服务端。

## 4. 概念模型

### 4.1 文档类型

每个受管控的 Markdown 文件通过 frontmatter 声明 `kind`。MVP 支持以下类型：

| kind | 作用 | 是否具有规范权 | 默认生命周期 |
| --- | --- | --- | --- |
| `conversation` | 用户与 Agent 的原始讨论、调研和反馈 | 否 | append-only 或 archived |
| `proposal` | 待确认的候选方案或变更提议 | 否 | proposed / rejected / accepted |
| `decision` | 用户或授权角色确认的决策记录 | 作为决策依据 | accepted / superseded |
| `intent` | 产品目标、用户体验偏好、原则 | 视配置而定，通常为约束来源 | active / retired |
| `normative` | 当前系统行为和正式需求的事实源 | 是 | draft / active / deprecated |
| `derived` | 设计、接口、任务、测试计划等派生内容 | 否 | draft / active / stale |
| `change` | 一次待审核的变更包，包含 delta spec | 否，直到归档 | proposed / approved / applied / archived |
| `generated` | 由工具生成的索引、上下文和矩阵 | 否 | generated |

项目可以增加自定义类型，但必须声明其规范权、允许的上游和下游关系。

### 4.2 关系类型

MVP 支持以下关系：

| 关系 | 方向 | 例子 |
| --- | --- | --- |
| `derived_from` | 派生项 -> 来源 | 需求来自某条对话或决策 |
| `decides` | 决策 -> 被决定事项 | 决策确认某个 proposal |
| `depends_on` | 派生项 -> 依赖项 | API 设计依赖需求 |
| `implements` | 代码/任务 -> 需求 | `src/auth.py` 实现需求 |
| `verifies` | 测试 -> 需求 | 测试验证需求 |
| `supersedes` | 新项 -> 旧项 | 新决策替代旧决策 |
| `conflicts_with` | 项 -> 项 | 明确记录的冲突 |
| `references` | 文档 -> 文档/条目 | 普通引用 |

关系写在 frontmatter 或正文引用中，扫描器统一归一化到图中。

### 4.3 稳定 ID

所有可以被其他文档引用的条目都必须有稳定 ID。推荐格式：

```text
REQ-AUTH-001
UX-DASHBOARD-003
DEC-CHECKOUT-007
PROP-CHECKOUT-002
TEST-AUTH-014
```

ID 一旦发布不应因为标题修改而改变。废弃条目保留 ID，并用 `status: deprecated` 或 `status: superseded` 指向新条目。

## 5. 文档协议

### 5.1 Frontmatter

MVP 使用 YAML frontmatter。最小示例：

```markdown
---
kind: normative
id: SPEC-AUTH
title: 用户认证
status: active
owner: team-platform
version: 1
---

# 用户认证
```

规范条目可以在标题中声明 ID：

```markdown
## REQ-AUTH-001 登录失败锁定
```

对于不希望把 ID 放进标题的项目，也支持显式标记：

```markdown
<!-- spec-id: REQ-AUTH-001 -->
连续登录失败 5 次后，账号锁定 15 分钟。
<!-- end-spec -->
```

MVP 首选标题 ID，因为它更容易阅读、review 和定位。

### 5.2 引用语法

统一使用以下形式之一：

```markdown
`REQ-AUTH-001`
```

或：

```markdown
<!-- ref: REQ-AUTH-001 -->
```

工具也可以支持短链接：

```markdown
[登录失败锁定](spec://REQ-AUTH-001)
```

MVP 先实现反引号 ID 和 frontmatter 列表，`spec://` 作为后续增强。

### 5.3 Normative 文档示例

```markdown
---
kind: normative
id: SPEC-AUTH
status: active
---

# 用户认证

## REQ-AUTH-001 登录失败锁定

连续登录失败 5 次后，账号锁定 15 分钟。

## REQ-AUTH-002 密码要求

密码至少包含 12 个字符，并且必须包含数字和字母。
```

### 5.4 Derived 文档示例

```markdown
---
kind: derived
id: DESIGN-AUTH-API
status: active
depends_on:
  - REQ-AUTH-001
  - REQ-AUTH-002
validated_against:
  REQ-AUTH-001: sha256:source-item-hash
  REQ-AUTH-002: sha256:source-item-hash
---

# 登录接口设计

本设计实现 `REQ-AUTH-001` 和 `REQ-AUTH-002`。

## 锁定响应

接口返回 HTTP 423，并附带剩余锁定时间。
```

Derived 文档可以有自己的实现细节，但不能重新定义上游规范。如果它与上游规范不一致，应产生 finding，而不是默默形成覆盖关系。

### 5.5 Conversation 文档示例

```markdown
---
kind: conversation
id: CONV-CHECKOUT-20260902
status: archived
participants:
  - user
  - agent
---

# 结账交互讨论

## msg-42 用户

我倾向于让结账流程在一个页面完成，不想拆成多个步骤。

## msg-43 Agent

单页表单可能增加首屏长度，但能减少页面跳转。

## msg-57 用户

确认采用单页表单。
```

扫描器不会把 `msg-42` 自动当成正式需求，只会允许后续 proposal 或 decision 通过 `derived_from` 建立来源。

### 5.6 Decision 文档示例

```markdown
---
kind: decision
id: DEC-CHECKOUT-007
status: accepted
decided_by: user
decided_at: 2026-09-02
derived_from:
  - CONV-CHECKOUT-20260902#msg-57
supersedes:
  - PROP-CHECKOUT-002
---

# 结账流程使用单页表单

结账流程采用单页表单，不拆分为多个步骤页面。

原因：减少页面跳转，满足移动端操作偏好。
```

### 5.7 Intent 文档示例

高层交互偏好不必降级为普通聊天，也不应直接变成组件实现。可以建模成产品意图：

```markdown
---
kind: intent
id: UX-PRINCIPLE-004
status: active
derived_from:
  - DEC-DASHBOARD-003
---

# 支持快速扫描和比较

后台操作界面优先支持快速扫描、比较和重复操作，减少与任务无关的装饰。
```

之后再派生出具体需求：

```markdown
## REQ-DASHBOARD-UX-003 默认采用表格视图

指标列表默认采用表格视图，并提供筛选和排序。

<!-- derived-from: UX-PRINCIPLE-004 -->
```

## 6. 推荐仓库结构

```text
project/
  AGENTS.md
  specalign.yaml
  spec/
    normative/
      auth.md
      checkout.md
    decisions/
      DEC-CHECKOUT-007.md
    intents/
      dashboard-ux.md
    proposals/
      PROP-CHECKOUT-003.md
    conversations/
      2026-09-02-checkout.md
    derived/
      api-checkout.md
      ui-checkout.md
      test-checkout.md
    changes/
      2026-09-02-single-page-checkout/
        proposal.md
        specs/
          checkout.md
        design.md
        tasks.md
  .specalign/
    manifest.json
    graph.json
    findings.json
    findings.md
    context.md
    index.md
```

项目可以采用现有的 `.kiro/`、`.specify/` 或 `openspec/` 目录，但需要通过 `specalign.yaml` 映射到同一内部模型。MVP 默认使用 `spec/`，减少与特定 Agent 的耦合。

## 7. 配置文件

`specalign.yaml` 示例：

```yaml
version: 1
spec_roots:
  - spec
include:
  - "**/*.md"
exclude:
  - "node_modules/**"
  - ".git/**"
  - "dist/**"
generated_dir: .specalign
agent:
  max_findings: 20
  fail_on:
    - blocking
    - error
rules:
  require_frontmatter: true
  require_stable_ids_for:
    - normative
    - decision
    - proposal
  forbid_normative_text_in:
    - derived
  require_tests_for: normative
```

MVP 不允许在仓库中写任意脚本表达复杂规则。规则先固定，配置只控制目录、严重级别和少量类型映射，避免配置系统本身成为第二个项目。

## 8. 软件架构

### 8.1 总体结构

```text
Markdown files + specalign.yaml
              |
              v
        File Discovery
              |
              v
        Markdown Parser
              |
              v
      Normalized Spec IR
              |
       +------+------+
       |             |
       v             v
   Graph Builder   Content Index
       |             |
       v             v
  Rule Checkers   Context Builder
       |             |
       +------v------+
         Finding Store
       /      |       \
      v       v        v
   CLI     JSON/MD   Hooks/CI
                      |
                      v
                    Agent
```

### 8.2 组件职责

#### File Discovery

- 根据 `spec_roots`、include、exclude 发现文件；
- 记录相对路径和文件 hash；
- 不执行文档中的命令或代码块；
- 不把所有仓库 Markdown 默认视为 spec。

#### Markdown Parser

- 解析 frontmatter；
- 解析标题、条目 ID、引用、关系声明；
- 保留行号和字符位置；
- 对无法解析的文件生成 `parse_error` finding；
- 不尝试理解完整自然语言逻辑。

#### Normalized Spec IR

内部中间表示不依赖具体文件格式：

```json
{
  "items": [
    {
      "id": "REQ-AUTH-001",
      "kind": "requirement",
      "document_id": "SPEC-AUTH",
      "source": {
        "path": "spec/normative/auth.md",
        "start_line": 8,
        "end_line": 12,
        "sha256": "..."
      },
      "status": "active",
      "text": "连续登录失败 5 次后，账号锁定 15 分钟。",
      "references": [],
      "relations": []
    }
  ]
}
```

#### Graph Builder

- 建立 ID 到条目的唯一索引；
- 建立引用边和关系边；
- 计算上游、下游和变更影响范围；
- 检测循环；
- 输出稳定排序的 `graph.json`，便于 Git diff。

#### Rule Checkers

MVP 的检查器应是纯函数：输入 IR 和 Git 基线，输出 Finding 列表。检查器之间不互相修改文档。

#### Context Builder

根据任务或 finding 生成 Agent 上下文：

- 相关规范条目全文；
- 上游 decision/intent；
- 下游设计、任务和测试；
- 变更前后 diff；
- 当前阻塞问题；
- 明确标记为“需要用户决策”的问题。

它不输出整个仓库，避免把无关文档再次塞入 Agent 上下文。

#### Finding Store

- 持久化 `findings.json` 和 `findings.md`；
- finding ID 在同一文件和同一 fingerprint 下保持稳定；
- 记录首次发现、最近发现和已解决状态；
- 不把“上一次已经报告过”当成忽略理由，除非用户显式配置 suppression。

#### Baseline Validator

为了让“下游文档是否重新确认”可确定地判断，派生文档可以记录上游条目的内容 hash：

```yaml
validated_against:
  REQ-AUTH-001: sha256:4d7...
```

扫描器计算当前 `REQ-AUTH-001` 的规范文本 hash。如果 hash 发生变化，而派生文档仍保存旧 hash，则产生 `stale_validation`。这不是判断设计是否正确，而是确定地判断“该设计尚未针对新的规范版本重新确认”。`spec sync` 不自动替换这个 hash；只有 Agent 或用户在重新审查后运行 `spec acknowledge`（后续命令）或手动更新它，才能解除 finding。

## 9. 确定性检查规则

### 9.1 MVP 必须实现

| 规则 ID | 名称 | 严重级别 |
| --- | --- | --- |
| `S001` | frontmatter 缺失或格式错误 | error |
| `S002` | required kind/id 缺失 | error |
| `S003` | ID 重复 | blocking |
| `S004` | 引用不存在 | blocking |
| `S005` | 引用 deprecated/superseded 条目 | error |
| `S006` | 依赖关系循环 | blocking |
| `S007` | 孤儿条目 | warning |
| `S008` | derived 文档缺少上游依赖 | warning |
| `S009` | 规范条目没有关联设计、实现或测试 | warning |
| `S010` | generated 区块与源条目 hash 不一致 | error |
| `S011` | `validated_against` 中的上游 hash 已过期 | error |
| `S012` | 文档引用和 frontmatter 关系不一致 | error |

### 9.2 不在 MVP 中自动判定

- 两段自然语言是否逻辑矛盾；
- 一段高层意图是否已经充分落实到 UI；
- 某个设计是否技术上最优；
- Agent 生成的实现是否真正满足业务语义；
- 讨论记录中的哪一句话代表用户最终意愿。

这些问题可以在后续增加“语义审查器”，但其输出必须是 `needs_review`，不能伪装成确定性结论。

### 9.3 潜在冲突的表示

语义冲突 finding 示例：

```json
{
  "id": "FND-00017",
  "type": "potential_semantic_conflict",
  "severity": "blocking",
  "requires_user_decision": true,
  "sources": [
    "spec/order.md#REQ-ORDER-001",
    "spec/payment.md#REQ-PAYMENT-004"
  ],
  "evidence": [
    "未支付订单 30 分钟后取消",
    "未支付订单 60 分钟后取消"
  ],
  "message": "两个条目可能描述同一业务规则，但值不同。"
}
```

程序只负责聚合证据和阻断后续自动化，不负责选择 30 分钟或 60 分钟。

## 10. Finding 协议

### 10.1 Finding 字段

```json
{
  "id": "FND-00017",
  "fingerprint": "sha256:...",
  "rule": "S003",
  "type": "duplicate_id",
  "severity": "blocking",
  "status": "open",
  "requires_user_decision": false,
  "message": "ID REQ-AUTH-001 定义了两次。",
  "locations": [
    {
      "path": "spec/normative/auth.md",
      "start_line": 8,
      "end_line": 12
    },
    {
      "path": "spec/derived/auth-api.md",
      "start_line": 14,
      "end_line": 17
    }
  ],
  "related_ids": ["REQ-AUTH-001"],
  "suggested_actions": [
    "保留 normative 文档中的定义",
    "将 derived 文档中的重复文本改为引用"
  ],
  "detected_at": "2026-09-02T10:00:00+08:00"
}
```

### 10.2 Finding 生命周期

```text
open -> acknowledged -> resolved
  |                         |
  +-------> suppressed <----+
```

`suppressed` 必须有原因、操作者和过期时间，不能通过删除报告文件实现永久忽略。

## 11. CLI 设计

### 11.1 命令总览

```text
spec init                         初始化目录、配置和 Agent 协议
spec scan                         只扫描并写入中间产物
spec check                       扫描并在终端输出问题
spec check --agent               输出适合 Agent 的精简报告
spec check --staged               只检查 Git 暂存区相关影响
spec index                       生成 SPEC-INDEX.md
spec graph                       生成 graph.json 或图形报告
spec impact <id>                 输出某个条目的上下游影响
spec context --for-agent         生成当前 Agent 上下文
spec context --finding <id>      生成某个问题的修复上下文
spec diff <git-ref>              比较当前工作树和 Git 基线
spec sync                        更新 generated 区块和索引
spec promote <proposal-id>       将 proposal 生成为待确认 decision 草稿
spec archive <change-id>        归档 change 并合并 delta
spec explain <finding-id>        显示问题证据和规则解释
```

### 11.2 `spec check --agent`

这是 MVP 的核心命令。输出应短、稳定、可直接被 Agent 使用：

```text
SPEC CHECK FAILED

Blocking: 2  Error: 1  Warning: 3

[FND-00017] duplicate_id (blocking)
ID REQ-AUTH-001 定义了两次。
  - spec/normative/auth.md:8
  - spec/derived/auth-api.md:14
Action: 保留单一事实源，将另一处改为引用。

[FND-00018] stale_reference (error)
design/payment-api.md:42 引用了已废弃的 REQ-PAYMENT-002。
Action: 更新为当前有效 ID，或记录 supersedes 关系。

Full report: .specalign/findings.json
Run `spec explain FND-00017` for details.
```

默认最多显示 20 个 finding，完整信息写入 JSON。`--format json` 用于脚本和 MCP 适配器。

### 11.3 退出码

```text
0  无问题
1  只有 warning 或 info
2  存在 blocking/error
3  配置、解析或工具执行失败
4  命令参数错误
```

Agent skill 以及 Git hook 都应依赖退出码，而不是解析自然语言。

### 11.4 Agent 调用边界

`spec check --agent` 必须是一次性、无交互的命令：

- 默认不启动编辑器、不等待用户输入、不询问是否修复；
- stdout 输出精简报告，stderr 只输出工具自身错误；
- 完整 JSON 写入 `.specalign/findings.json`；
- 在相同工作树上重复运行应得到相同 finding 集合和排序；
- 命令本身不能执行来自 Markdown 代码块或文档正文的命令；
- Windows PowerShell、Windows CMD、Git Bash 和 Linux/macOS shell 都应能运行同一 CLI。

如果需要 Agent 进入“请用户确认”的状态，报告中使用 `requires_user_decision: true`，而不是让 CLI 自己阻塞等待输入。

## 12. Agent 集成

### 12.1 Skill 的定位

Skill 是工作流合同，不是报告存储。它规定 Agent 在什么时机调用 CLI、如何解释退出码、什么时候停下来请求用户决策。

MVP 应生成一个 `skills/spec-align/SKILL.md` 或项目约定的等效文件：

````markdown
# Spec Align Workflow

开始任务时运行：

```bash
spec check --agent
```

规则：

1. 退出码为 2 时，先处理 blocking/error finding，不得继续扩大代码变更。
2. `requires_user_decision: true` 的 finding 不得由 Agent 擅自选择方案。
3. 修改 normative、decision、proposal 或 derived 文档后，运行 `spec impact` 和 `spec check --agent`。
4. 任务结束前必须再次运行 `spec check --agent`。
5. 只修改 generated 区块，不直接改写工具拥有的其他文件。
6. 新增可复用事实时，先创建稳定 ID，再在其他文档中引用。
7. 如果实现发现原设计不成立，先创建 change/proposal 或更新决策，再继续修改代码。
````

Skill 中不要塞入全部项目 spec。Skill 只负责流程和边界，具体上下文由 `spec context` 按需生成。

### 12.2 真实提醒的实现顺序

MVP 按以下强度实现：

1. Agent 明确调用 `spec check --agent`，结果直接进入当前工具输出；
2. 非零退出码使 Agent 看到失败状态；
3. pre-commit hook 阻止带阻塞问题的提交；
4. CI 再执行完整仓库检查；
5. 后续为不同 Agent 提供 MCP、IDE hook 或命令 wrapper。

后台文件监控可以作为辅助，但不能作为唯一通知方式。后台进程无法凭空把内容插入任意 Agent 的上下文。

### 12.3 MCP 适配器（非 MVP 必须）

未来可以暴露：

```text
spec_scan(config?)
spec_get_finding(finding_id)
spec_get_impact(item_id)
spec_get_context(item_ids, finding_ids?)
spec_validate_change(change_path)
```

MCP 返回的数据仍复用 CLI 的 Finding 和 IR 协议，不维护第二套检查逻辑。

## 13. 变更工作流

### 13.1 小改动

适用于拼写、局部代码和不改变行为的维护：

```text
spec check
  -> 修改代码或派生文档
  -> spec check
  -> 提交
```

### 13.2 规范行为改变

适用于修改已有需求：

```text
创建 change
  -> proposal 说明为什么改
  -> delta spec 写 ADDED/MODIFIED/REMOVED
  -> 用户或授权角色审核
  -> spec impact
  -> Agent 修改代码和测试
  -> spec verify/check
  -> archive 合并到 normative
```

### 13.3 Delta 示例

```markdown
---
kind: change
id: CHANGE-CHECKOUT-20260902
status: proposed
---

# 将结账流程改为单页表单

## MODIFIED Requirements

### REQ-CHECKOUT-UX-001

结账流程从分步向导改为单页表单。

## REMOVED Requirements

### REQ-CHECKOUT-UX-002

移除“每个步骤必须单独保存”的旧要求。

## ADDED Requirements

### REQ-CHECKOUT-UX-003

单页表单必须在移动端支持分组折叠。
```

归档前必须检查：被 MODIFIED/REMOVED 的 ID 确实存在、没有未处理下游、测试覆盖已经确认、没有未解决的 blocking finding。

## 14. 生成内容和同步策略

### 14.1 工具可写范围

MVP 工具只自动写入：

- `.specalign/manifest.json`；
- `.specalign/graph.json`；
- `.specalign/findings.json`；
- `.specalign/findings.md`；
- `.specalign/index.md`；
- `AGENTS.md` 或 skill 中由 `SPEC-ALIGN:BEGIN/END` 标记的托管区块；
- Markdown 中明确标记的 generated 区块。

### 14.2 生成区块

```markdown
<!-- spec-align:generated:start source=REQ-AUTH-001 hash=sha256:... -->
连续登录失败 5 次后，账号锁定 15 分钟。
<!-- spec-align:generated:end -->
```

如果用户修改了生成区块，`spec check` 报告 `generated_drift`，要求从源条目重新生成或显式解除生成关系。

### 14.3 `spec sync` 的行为

`spec sync` 只做确定性操作：

1. 根据当前 IR 生成索引和追踪矩阵；
2. 更新生成区块；
3. 更新 Agent 上下文；
4. 不自动改写普通自然语言；
5. 发现同一目标区块由两个源生成时直接失败。

## 15. 对话记录管理

### 15.1 为什么单独建模

对话记录具有高价值，但它同时包含猜测、反例、废案、上下文和最终决定。如果直接把整个聊天记录当成规范，Agent 会无法区分“用户考虑过”与“用户确认了”。

### 15.2 生命周期

```text
conversation
    -> proposal
    -> decision (用户确认)
    -> normative requirement
    -> derived design/task/test
```

每次晋升都必须保留来源：

```yaml
derived_from:
  - CONV-CHECKOUT-20260902#msg-57
```

### 15.3 自动化边界

Agent 可以从对话中提议：

- 可能的用户意图；
- 候选 requirement；
- 需要确认的冲突；
- 可能受影响的条目。

但只有以下动作可以改变规范权：

- 用户明确确认；
- 具备项目授权的角色明确确认；
- 通过 review/merge 流程批准。

工具应提供 `spec promote` 帮助创建 decision 草稿，但不应默认将聊天内容直接写入 active normative spec。

## 16. 实现建议

### 16.1 技术选型

MVP 推荐 Python 3.11+：

- `pathlib`：跨平台文件处理；
- `argparse` 或 Typer：CLI；
- `PyYAML`：frontmatter 和配置解析；
- `markdown-it-py`：Markdown 标题、位置和链接解析；
- `hashlib`：内容 fingerprint；
- `json`：中间产物和报告；
- `pytest`：测试。

不建议 MVP 引入数据库、LLM API、常驻服务或图数据库。IR 和图可以先完全由内存对象和 JSON 生成。

### 16.2 包结构

```text
src/specalign/
  cli.py
  config.py
  discover.py
  parser.py
  model.py
  graph.py
  rules/
    __init__.py
    structure.py
    references.py
    lifecycle.py
    generated.py
  findings.py
  context.py
  sync.py
  git.py
tests/
  fixtures/
  test_parser.py
  test_graph.py
  test_rules.py
  test_cli.py
```

### 16.3 解析策略

不要用正则表达式解析完整 Markdown。正则可以用于识别 ID 和简单引用，但标题层级、frontmatter 边界、代码块和行号应交给 Markdown parser 处理。

解析失败时要报告具体文件和行号，不要静默跳过；否则用户会误以为文档已纳入检查。

### 16.4 稳定输出

所有 JSON 输出按以下顺序排序：

1. item ID；
2. relation type；
3. source path；
4. line number。

这样同一内容重复运行不会产生无意义的 Git diff。

### 16.5 运行环境和性能边界

MVP 面向单仓库运行，目标边界为：

- 不超过 2,000 个受管 Markdown 文件；
- 不超过 50,000 个可引用条目；
- 冷启动扫描在普通开发机上小于 5 秒；
- 增量扫描只重新解析内容 hash 发生变化的文件及其下游；
- 不要求常驻 daemon，不要求网络连接；
- Windows 路径统一在 IR 中保存为 `/` 分隔的仓库相对路径。

超过这些边界后再引入持久化索引或文件监控服务，不把未来的规模优化提前塞进 MVP。

## 17. MVP 范围

### 17.1 MVP 必须有

- Python CLI 可安装和运行；
- `specalign.yaml` 配置；
- Markdown frontmatter 解析；
- 稳定 ID 解析；
- 引用和依赖图；
- 重复 ID、断链、废弃引用、循环、孤儿和生成漂移检查；
- `spec check --agent`；
- 稳定退出码；
- `findings.json`、`findings.md`、`graph.json`、`index.md`；
- `AGENTS.md` 或 skill 托管区块生成；
- Git pre-commit 示例；
- 对话、decision、normative、derived 四种文档类型；
- 最小的 change/delta 格式；
- 单元测试、CLI 集成测试和 fixture 项目。

### 17.2 MVP 明确不做

- 自动用 LLM 修改任意文档；
- 自动判断两个自然语言段落必然矛盾；
- 在线协作后台；
- 多仓库实时同步；
- 直接生成完整业务代码；
- 绑定某个特定 Agent 的私有 API；
- 自动从所有聊天记录抽取正式 requirement；
- 替用户批准决策。

### 17.3 MVP 的可交付形态

第一版应当能以一个 Python 包交付：

```text
pipx install spec-align
spec init
spec check --agent
```

`spec init` 生成：

- `specalign.yaml`；
- `spec/` 的示例目录和四种基本文档模板；
- `AGENTS.md` 或 `skills/spec-align/SKILL.md` 的托管区块；
- `.git/hooks/pre-commit` 的可选示例；
- 一个最小 fixture 和验证命令。

MVP 的“完成”不是拥有漂亮的 Web UI，而是一个新仓库能在 10 分钟内初始化，Agent 能按 skill 调用检查命令，用户能在一次故意制造的断链或重复 ID 中看到阻塞结果，并且 Git 提交会被 hook 拦住。

## 18. 分阶段路线

### Phase 0：协议和样例

- 定义 frontmatter、ID、引用和 finding schema；
- 建立一个包含冲突、废弃引用、对话晋升和 delta 的 fixture 仓库；
- 手工验证 Agent skill 是否能按退出码工作。

### Phase 1：确定性 CLI

- 实现扫描、解析、图和基础规则；
- 实现 `spec check --agent`；
- 实现 JSON/Markdown 产物；
- 实现 Git hook 示例。

建议把 Phase 1 拆成两个可独立验收的里程碑：

1. **Parser/IR 里程碑**：给定 fixture，稳定生成 items、relations 和 source locations；
2. **Gate 里程碑**：给定 fixture，`spec check --agent` 的退出码和 JSON finding 完全符合 schema。

### Phase 2：工作流和生成视图

- 实现 `spec impact`、`spec context`、`spec sync`；
- 实现 generated 区块；
- 实现 change/delta/verify/archive；
- 提供 Spec Kit/OpenSpec/Kiro 目录映射。

### Phase 3：Agent 适配

- MCP server；
- Kiro hooks；
- Claude Code/Codex/Cursor skill 模板；
- IDE diagnostics 或 PR annotations。

### Phase 4：语义辅助

- 对可能重复或冲突的条目做相似度聚类；
- 生成“需要用户确认”的问题包；
- 从 conversation/proposal 生成带 provenance 的 decision 草稿；
- 仍然保留确定性检查作为最终 gate。

## 19. 关键用户场景和验收标准

### 场景 A：重复事实

用户在 normative 和 derived 文档中写了两个同 ID 条目。

验收：

- `spec check --agent` 返回退出码 2；
- 输出两个文件和行号；
- 指出规范权应保留在 normative；
- 不自动删除任何文本。

### 场景 B：修改需求后的影响分析

用户修改 `REQ-AUTH-001` 的行为。

验收：

- `spec impact REQ-AUTH-001` 列出所有下游设计、任务、实现和测试；
- `spec check` 能报告未重新确认的 derived 文档；
- `spec context --for-agent` 只包含相关上下文，而不是整个仓库。

### 场景 C：讨论记录转正式需求

用户在 conversation 中表达交互偏好并最终确认。

验收：

- 工具能识别 conversation 文件，但不把它当 normative；
- `spec promote` 生成带 `derived_from` 的 decision 草稿；
- decision 未被标记 accepted 前，不进入 active 规范图；
- accepted decision 可以被 normative requirement 引用。

### 场景 D：Agent 忘记检查

Agent 修改了 spec 后没有主动查看 `.specalign/findings.json`。

验收：

- skill 在任务协议中要求运行 `spec check --agent`；
- pre-commit hook 或 CI 会再次检查；
- blocking finding 时提交或 CI 失败；
- 报告内容直接出现在失败命令的返回值中。

### 场景 F：下游重新确认

`REQ-AUTH-001` 内容发生改变，但 `design/auth-api.md` 的 `validated_against` 仍保存旧 hash。

验收：

- `spec check --agent` 返回 `S011/stale_validation`；
- finding 同时列出上游当前 hash、下游记录的旧 hash 和派生文档位置；
- `spec sync` 不会静默把旧 hash 改成新 hash；
- Agent 重新审查后显式更新确认基线，finding 才消失。

### 场景 E：自然语言疑似冲突

两个不同文件写了不同的取消时间。

验收：

- 如果只依赖确定性规则，至少报告两个相关条目未建立唯一来源或存在重复主题；
- 如果启用语义插件，输出 `requires_user_decision: true`；
- Agent 不得自动选择一个版本并清理另一个版本。

## 20. 风险与应对

### 20.1 文档协议负担过重

风险：用户觉得每句话都要加 ID，最终放弃使用。

应对：只要求“可复用、会影响实现或测试的事实”拥有 ID；普通背景和讨论可以保持自由文本。

### 20.2 规则误报导致 Agent 忽略

风险：大量 warning 让 Agent 和用户习惯性忽略全部结果。

应对：MVP 严格控制规则数量；blocking 只用于可证明的结构错误和明确的未解决决策；warning 不阻断提交。

### 20.3 生成内容和人工编辑互相覆盖

风险：同步命令覆盖用户修改。

应对：只写明确的 generated 区块；发现漂移时失败并要求显式确认。

### 20.4 Agent 忽略 skill

风险：skill 只能约束 Agent，不能从操作系统层面强制执行。

应对：退出码、pre-commit、CI 和适配器形成多层 gate。skill 是第一层体验，Git/CI 是最终保护。

### 20.5 对话内容中的提示注入

风险：conversation 或外部资料里出现“请执行某条命令”之类文本。

应对：扫描器把文档当数据，不执行文档指令；Agent skill 明确要求把文档内容视为项目资料，命令执行仍由 Agent 的权限和用户批准控制。

### 20.6 过早引入语义 AI

风险：把模型猜测当成事实，反而制造新的错误。

应对：将语义审查作为插件；所有模型发现都标记为候选或需要复核，不得直接修改规范事实源。

## 21. 与现有工具的关系

Spec Align 不应和 GitHub Spec Kit、Kiro 或 OpenSpec 争夺完整的“从需求生成代码”流程。

推荐兼容方式：

- 把 Spec Kit 的 constitution/spec/plan/tasks 映射成对应文档类型；
- 把 Kiro 的 steering 映射成项目级 context，把 specs 映射成 change/derived；
- 把 OpenSpec 的 `specs/` 作为事实源，把 `changes/` 作为 change/delta；
- 将它们的 Agent 命令或 hooks 调用 `spec check --agent`；
- 统一输出 Finding、影响图和 provenance。

Spec Align 的差异化不在于“另一个模板”，而在于跨工具、跨文档、跨生命周期地维护引用和变更影响。

## 22. 推荐的第一份实现任务清单

```text
[ ] 初始化 Python package 和 console script `spec`
[ ] 定义 specalign.yaml schema
[ ] 定义 Item、Relation、Finding、SourceLocation 数据结构
[ ] 实现文件发现和排除规则
[ ] 实现 frontmatter 解析
[ ] 实现标题 ID 和反引号引用解析
[ ] 构建 ID 索引和依赖图
[ ] 实现 S001-S008 基础规则
[ ] 实现稳定 fingerprint 和 finding ID
[ ] 实现 `spec check --agent` 与退出码
[ ] 生成 graph.json、findings.json、findings.md
[ ] 生成 SPEC-INDEX.md
[ ] 生成 AGENTS.md/skill 托管区块
[ ] 增加 pre-commit 示例
[ ] 建立 conversation/decision/normative/derived fixture
[ ] 建立重复、断链、循环和变更影响测试
[ ] 编写一份 Agent 使用说明并用真实 coding agent 手工跑通
```

## 23. 最终判断

Spec Align 的 MVP 不应承诺“自动保持所有自然语言完全一致”。可落地的承诺应是：

1. 任何可复用规范都有稳定身份；
2. 规范事实只有一个权威来源；
3. 其他文档和代码通过关系表达依赖；
4. 规范修改会产生可查询的影响范围；
5. 结构和引用问题能由确定性程序稳定发现；
6. 发现结果会通过 `spec check --agent` 直接进入 Agent 当前上下文；
7. 需要产品判断的冲突会明确阻断，而不是被工具静默猜测；
8. 对话记录可以保留、检索和追溯，但只有确认后的决策和规范才具有约束力。

如果这八点稳定工作，后续再增加语义冲突检测、跨仓库共享和 IDE 集成才有可靠基础。否则，直接从“自动改写全部 spec”开始，会把自然语言的不确定性和 Agent 的不确定性叠加在一起，难以验证，也难以让用户信任。

