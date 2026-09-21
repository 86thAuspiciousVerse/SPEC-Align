# Spec Align

个人使用的本地文档依赖与审查工具。纯代码解析显式 Markdown 声明，维护当前依据、版本复核、变更影响和历史。不会推断漏写的依赖或判断全部自然语言是否一致。

- 当前协议：[docs/PROTOCOL.md](docs/PROTOCOL.md)
- 实施顺序：[IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md)
- 交付证据：[ACCEPTANCE.md](ACCEPTANCE.md)
- 产品意图：[SPEC-ALIGN-CURRENT.md](SPEC-ALIGN-CURRENT.md)

## 安装和起步

Windows x64 也提供单文件 `specalign.exe`，无需安装 Python，支持相同 CLI 和 `serve` MCP 接口。本地构建发布包后会得到 `dist/specalign-0.3.0-windows-x64.zip`；使用见 [Windows 说明](packaging/WINDOWS-README.md)，构建见 [打包流程](packaging/README.md)。安装后应固定 exe 位置；打包不会解决宿主切换提供商导致配置未加载的问题。

源码安装支持 Python 3.10–3.13；仓库内的 GitHub Actions 会在 Ubuntu 与 Windows 上运行测试和临时目录演示。Windows 单文件目前只面向 x64，构建脚本和验收证据见 `packaging/`。

需要 Python 3.10+。建议在虚拟环境安装：

```powershell
python -m pip install -e ".[test]"
specalign --root C:/path/to/project init
```

init 只创建配置和受管目录。将重要结论写入配置 roots 下的 Markdown，语法见协议；然后：

```powershell
specalign --root C:/path/to/project check --agent
specalign --root C:/path/to/project explain DESIGN-STORAGE
specalign --root C:/path/to/project review DESIGN-STORAGE --snapshot <返回的快照> --reason "具体检查了哪些变化，以及为何兼容"
```

`review` 只在阅读证据后调用；快照过期会拒绝。不要用替换 hash 的方式清理提醒。首次声明依赖也需要复核。

## 命令

| 命令 | 用途 |
| --- | --- |
| init | 初始化 specalign.yaml 与 roots |
| scan / check | JSON 扫描结果；--agent 为短报告；--fail-on error 忽略 warning 门槛 |
| explain ID | 当前正文、已审查基线和差异 |
| context ID --max-chars N | 条目及显式上游；正文截断会标明 |
| impact ID | 下游链与关系图 |
| graph --format json/mermaid | 导出完整声明图 |
| review ID --snapshot TOKEN --reason TEXT | 绑定版本的兼容性复核 |
| accept / retire ID --snapshot TOKEN --actor NAME --reason TEXT | 显式采纳或退役，记录理由 |
| history [ID] | 问题生命周期、复核和决策记录 |
| backup PATH / restore PATH | 账本备份；只恢复到没有现存数据库的目录 |
| install / uninstall --codex | 项目 hook、MCP 配置和 skill；保留已有非托管内容 |
| install / uninstall --git-hook | 可选暂存区结构检查；已有自定义 hook 不覆盖 |
| doctor | 本地接入诊断；不会把配置存在当成已送达 |
| hook | stdin/stdout JSON 宿主适配 |
| serve | 标准 MCP stdio 服务 |
| git-check | 检查 Git 暂存配置与文档，独立于工作区未暂存改动 |

默认检查返回 0/2/3：无问题／有问题（含 warning）／执行失败。参数用法错误由 argparse 返回 2。采纳或复核成功后，如果还有其他问题，也可能返回 2，应读报告判断。

## Codex 接入

```powershell
specalign --root C:/path/to/project install --codex
specalign --root C:/path/to/project doctor
```

安装器修改目标项目 `.codex/hooks.json`、`.codex/config.toml` 中自己的部分，并安装 `.agents/skills/spec-align/SKILL.md`。不会修改全局配置、认证或 hook 信任；需要在 Codex 正常流程中信任项目和 `/hooks` 内的具体定义。没有通过信任时，不能假设自动巡查已运行。

PostToolUse 扫描文件并返回 additionalContext。Stop 默认只警告；配置 `stop_on_errors: true` 后结构错误最多请求继续一次，避免无限循环。普通待复核 warning 不阻塞回合。

**用户信任后，新 Codex CLI 的自动提醒已实测送达模型，复核清零后再次运行不再提醒。** 当前桌面会话原生 MCP 调用也已通过，但桌面 PostToolUse 尚未观察到触发；CLI 结果不代替桌面验证。详见 [工作流实测](experiments/workflow/README.md)。

MCP 暴露 `spec_init`、`spec_check`、`spec_explain`、`spec_context`、`spec_impact`、`spec_history`、`spec_review`、`spec_decide`、`spec_review_batch`、`spec_migration_plan`。服务可以在启动时绑定项目，也可以无参数启动为未绑定模式。未绑定服务启动时不扫描目录，agent 每次调用项目工具都要传入当前项目的绝对 `root`；首次使用可调用 `spec_init(root=...)`。每个成功返回都带有 `project_root`，客户端应先核对它与当前项目一致，再使用 snapshot 做复核或决策。不要启用把根目录固定到本仓库的旧全局条目。

如果不想为每个项目写 MCP 配置，可在全局配置中使用未绑定服务：

```toml
[mcp_servers.SpecAlign]
command = 'C:\CodeX\Spec-align\dist\windows\specalign.exe'
args = ['serve']
```

它启动时不会扫描任何目录。agent 先确认当前工作区绝对路径，再调用 `spec_init(root="C:\\path\\to\\project")`（需要初始化时）和 `spec_check(root="C:\\path\\to\\project")`。不要把 `--root` 留成相对路径或 shell 变量；工具不会从 MCP 会话自动获取工作区目录。

## Skill 与数据

仓库 skill 源位于 [.agents/skills/spec-align/SKILL.md](.agents/skills/spec-align/SKILL.md)。`specalign/assets/SKILL.md` 是随 wheel 交付的副本，修改源后必须同步并验证分发包内容。安装到其他项目时使用 `install --codex`，不用手工记忆流程。

Markdown 与配置纳入 Git；`.specalign/` 内的 SQLite 含不可重建的复核历史，需要单独备份，不能当缓存删掉。恢复前准备对应版本的文档；restore 拒绝覆盖现存数据库。

采纳使用单文件原子替换并保留操作意图日志。若文件替换后数据库提交前进程中断，history 会显示 pending operation；需核对磁盘与历史，不会自动猜测补写。普通外部编辑会在后续扫描中被发现。

## 验证与演示

```powershell
python -m pytest -q
python examples/walkthrough.py
```

演示只操作临时目录，覆盖变更提醒、去重、差异、旧快照拒绝和复核闭环。演示中的复核为明确标识的 fixture 断言，不代表真实技术判断。

本仓库 `spec/architecture.md` 是当前系统的自用约束和契约；它与所有其他项目使用同一 runtime。`codegraph/` 是独立本地参考仓库，不作为源码依赖、不纳入 Git。公开源代码仓库位于 [github.com/86thAuspiciousVerse/SPEC-Align](https://github.com/86thAuspiciousVerse/SPEC-Align)。

## 0.3 工作流改进

MCP 默认检查和写入回执改为摘要；完整正文用 `spec_check(detail="full")` 或按需 context/explain。CLI 为兼容旧脚本保留 full，可用 `check --detail summary --scope pixel-art-converter`。范围名使用文档实际 scope；范围过滤不会掩盖其他范围的结构错误。

新增 `spec_review_batch`、`spec_migration_plan`，以及多 ID 关系上下文和 `since_snapshot` 比较。详细输入、截断及审计边界见 [协议扩展](docs/PROTOCOL.md#03-agent-交互扩展)。CLI 对应 `review-batch --snapshot TOKEN --file reviews.json`、`migration-plan`、`context ID1 ID2 --related`。

更新代码后，已有 MCP 服务进程需要重新加载才能看到新接口；已运行的旧进程不作为新版本验收依据。hook 定义未改变，无需通过重新生成配置更换其信任 hash。

