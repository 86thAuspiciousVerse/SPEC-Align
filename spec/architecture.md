# Spec Align 当前实现契约

来源：[产品讨论](../SPEC-ALIGN-CURRENT.md)、[实施计划](../IMPLEMENTATION-PLAN.md)。仅纳管以下可复用约束；讨论材料保留原位置。

<!-- spec
id: REQ-DETERMINISTIC
status: active
kind: requirement
-->

runtime 必须只依据显式文档声明、文件状态与工具参数运行，不调用 LLM，不从自然语言生成依赖，不读取对话猜测 agent 意图。

<!-- /spec -->

<!-- spec
id: REQ-AUDIT
status: active
kind: requirement
-->

文档复核必须绑定条目及依赖版本。自动扫描不得伪造复核；变化、采纳与复核依据必须可以追溯。历史审查账本不能当作可删除缓存。

<!-- /spec -->

<!-- spec
id: DESIGN-CORE
status: active
kind: design
depends_on: [REQ-DETERMINISTIC, REQ-AUDIT]
-->

Markdown AST 解析独立声明，按内容 hash 复用解析结果。SQLite 保存快照、显式审查及问题事件；扫描和复核在写事务中串行化。依赖传播与生命周期有效性由纯代码判断，数据库备份通过显式命令完成。

<!-- /spec -->

<!-- spec
id: DESIGN-ADAPTERS
status: active
kind: design
depends_on: [DESIGN-CORE]
-->

CLI、Codex hook 和标准 MCP stdio 服务调用同一核心。hook 只提供触发和送达通道，不解析对话。安装器只配置项目内 hook、MCP 和 skill，不写信任或认证。Codex 实际模型收到提醒需单独实测，不能由协议测试推定。

<!-- /spec -->

