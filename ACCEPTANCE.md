# Spec Align v0.2 验收记录

日期：2026-09-14。范围：个人使用版，按 [实施计划](IMPLEMENTATION-PLAN.md) 的 M1–M6 实施。最新结论：v0.3 本地功能、MCP、Windows x64 分发和仓库外 smoke 验收通过；用户信任后，新 Codex CLI 的自动 PostToolUse 模型送达及复核清零后静默已实测通过，当前桌面原生 MCP 也已通过。桌面 PostToolUse 仍未观察到触发。公开源代码已推送到 [github.com/86thAuspiciousVerse/SPEC-Align](https://github.com/86thAuspiciousVerse/SPEC-Align)。以下保留阶段性历史证据，最新详情见工作流实测末节。

后续真实工作区模拟见 [工作流实测](experiments/workflow/README.md)：MCP 文档演进闭环通过；已实际编辑受管文档，但当前会话未观察到宿主 hook 自动调用或提醒。最终自用快照已随模拟条目变化，不再是下面最初验收快照。

继续诊断已确认：新 Codex app-server 能发现全部 7 个 MCP 工具；两个项目 hook 均已加载且无解析错误，但 trustStatus=untrusted。用户正常信任具体定义之前，自动送达仍不具备验收条件。此结果来自新 CLI 宿主，不代表当前桌面会话已经重新加载。

## 已完成与证据

| 范围 | 实际证据 |
| --- | --- |
| 协议与核心 | 全套 34 项 pytest 测试通过；包含缓存、配置、解析失败保留旧依据、循环/断链、问题复发、并发扫描、快照过期拒绝、备份恢复 |
| 生命周期 | 提案、采纳、退役、替代、挑战、历史查询；测试覆盖重复继任者与采纳者依赖被替代目标的拒绝 |
| 查询 | explain/context/impact/graph、精简 agent 输出；关系区分与上下文正文截断有测试 |
| Codex 安装器 | 临时项目真实执行生成的 hook 命令；安装/卸载幂等、保留其他配置和用户改动、非法 TOML 在写入前拒绝 |
| Git 门槛 | 测试暂存文档与暂存配置，未暂存配置不干扰；保留已有或用户修改过的 hook |
| MCP | 使用官方 SDK ClientSession 启动真实 stdio 子进程，完成 initialize、工具发现、调用、复核及错误响应；未经过 Codex 模型 |
| 分发 | 最终 wheel 在仓库外临时目录安装，确认从安装位置导入，执行 init/install/doctor/check/uninstall；打包 skill 与源逐字节相同 |
| 演示与 skill | examples/walkthrough.py 五项闭环断言通过；skill quick_validate 通过 |
| 自用 | spec/architecture.md 纳管四个条目；阅读实现后按返回快照复核两个设计，最终 findings 为空；本地保存审查及备份 |

最终安装包：`dist/spec_align-0.2.0-py3-none-any.whl`，24,539 字节。

SHA-256：`89ad19c8bd31bc60de4a7f6990172802f9af7fd4a03e9f03049a55fdf17a5b8d`。

## 独立审查

核心与集成分别由隔离上下文的只读 agent 审查，主 agent 修复。已处理：不同关系的问题 ID 碰撞、重复直接继任者、采纳者依赖其替代目标、Git hook 用户改动保护、roots 规范化、暂存检查被未暂存配置干扰、inline MCP TOML 无法安全追加。相关回归测试通过，跟进复查未发现剩余相关阻塞。

## 当前工作区接入

已安装项目 PostToolUse/Stop hook、MCP 配置、配套 skill 和可选 Git pre-commit。生成的本机解释器路径保留在本地 `.codex/` 配置，不提交。安装器没有设置项目或 hook 信任，也没有修改认证。

自用快照：`eef113c2f59c4df270a2ca8a54abff345d5d54c3411179e61646dcf4fb1a281c`。审查账本与备份 `.specalign/backups/acceptance-v0.2.sqlite3` 留在本地；克隆 Git 不会获得这些复核记录，应重新复核或显式恢复账本。

## 未验证及使用边界

- **Codex 实际模型送达待实测。** 前次隔离 CLI 请求在采样阶段认证失败/超时，未进入工具事件；该结果不证明 hooks 不支持。doctor 如实返回 `not_verified`。官方要求正常信任项目及具体 hook；在 Codex 中完成信任后，仍需观察一次“修改上游 → 无主动 check 的提醒 → 模型复核”的真实链路。见 [探针记录](experiments/hooks/README.md) 与 [官方文档](https://developers.openai.com/codex/hooks)。不以本地协议测试替代此项。
- runtime 不理解自然语言，不发现漏声明依赖，不证明审查理由正确；actor 是声明而非鉴权。手工改 Markdown 状态不会自动生成采纳理由。
- 文件替换与数据库提交不能跨资源原子化；中断后 pending operation 留待核对，不自动猜测恢复。审查与外部编辑器也不存在全局文件锁，后续变动由再次扫描发现。
- context 字数预算限定正文；graph 的 Mermaid 导出是展示，结构有效性应以 check 或 JSON 为准。
- 无常驻监听、可视化编辑器、跨仓库同步或其他宿主的已验证适配；这些不属于本版计划。

## 可重复验证

```powershell
python -m pytest -q
python examples/walkthrough.py
python -m specalign --root C:/CodeX/Spec-align check --agent
python -m specalign --root C:/CodeX/Spec-align doctor
```

截至 v0.2 验收时仅做本地 Git 提交，未创建远程；v0.3 的公开仓库地址见本文档开头。

## 0.3 工作流升级验证（2026-09-14）

### Windows exe 分发补充

- 生成 `dist/windows/specalign.exe`，15,430,325 字节，Windows x64 单文件，内嵌 Python 与依赖；同一入口支持 CLI 和 stdio MCP。
- exe SHA256：`53164018e9c055f4a370ceb05a08334713be3ad2cf6d5ae7cc119501bdea8f28`。
- 发布包 `dist/specalign-0.3.0-windows-x64.zip` 包含说明、协议、依赖环境清单、许可证和exe校验和；ZIP校验和位于同名 `.zip.sha256` 文件。
- 仓库外中文/空格路径复制运行、子进程 PATH 移除 Python；初始化、安装/卸载、备份、生成hook、9项MCP发现、摘要/上下文/批量复核均通过。hook本次0.812秒，小于15秒超时，非性能保证。
- 41项pytest通过；新上下文独立审查无发布阻塞。重复打包已改为全新staging目录，避免带入历史残留。
- 未修改本工作区实际MCP/hook配置、信任或认证。未签名、未上传远程、未在干净VM或其他架构验收；无Python PATH的本机验证不冒充干净机器验证。使用/重建见 `packaging/`。

当前实现、自动验证与独立代码审查通过；不覆盖前述 v0.2 历史验收。

- 41 项 pytest 全部通过，含新 MCP 默认摘要/full、多 ID context、review_batch 和 migration_plan 的真实 stdio 调用。
- 回归覆盖：范围查询保留项目级错误；批次目标无效零写入；批次中途文件变化回滚；逐项理由及 batch 历史；删除/scope移动比较；候选换边导致循环；正文/条目截断。
- 当前44条目项目摘要查询返回 item_count=44、零问题，无 items 正文，快照仍为像素实验最终快照。
- 配套 skill 验证通过，随包副本逐字节一致。0.3 wheel 在仓库外安装后通过初始化、摘要、迁移预演和安装卸载验证。
- 安装包 `dist/spec_align-0.3.0-py3-none-any.whl`，SHA256 `cc3872515660c67e65ee296730d3abcc901b9ba87669d3de3294ebc5723a4856`。
- 前次独立审查因429未完成；本轮新上下文审查完成，核对 query、批次事务、CLI/MCP 和测试，未发现阻塞缺陷。重新运行41项测试及walkthrough全部通过；实际44条目项目仍为零问题，快照未变。
- 本轮未更改 hook 定义或信任；运行中的旧 MCP 服务需重新加载才使用0.3接口，真实stdio子进程测试不代表旧服务已热更新。

