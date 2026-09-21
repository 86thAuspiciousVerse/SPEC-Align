# Spec Align 0.3.0 — Windows x64

本地单文件 CLI / MCP 工具，无需安装 Python。不是双击打开的图形应用。

## 起步

将 specalign.exe 放到固定位置，例如 C:/Tools/specalign/specalign.exe。

```powershell
& C:/Tools/specalign/specalign.exe --root C:/Projects/my-project init
& C:/Tools/specalign/specalign.exe --root C:/Projects/my-project check --agent
& C:/Tools/specalign/specalign.exe --root C:/Projects/my-project install --codex
```

init 创建默认 spec/ 和 specalign.yaml。重要条目的写法见附带 PROTOCOL.md。
install 配置项目的 MCP、PostToolUse/Stop hooks 和配套 skill；保留不属于本工具的配置。
Codex 中仍需正常加载项目配置、审阅并信任具体 hook。更换模型提供商可能改变实际配置来源，exe 不负责绕过该配置层。

MCP 单独配置示例：

```toml
[mcp_servers.specalign]
command = 'C:\Tools\specalign\specalign.exe'
args = ['--root', 'C:\Projects\my-project', 'serve']
```

serve 使用 stdin/stdout 标准 MCP 协议，没有网页端口。无需 Python 参数 `-m specalign`。
MCP 单独配置不等于安装 skill 或 hook；需要自动提醒时使用 install --codex。

如果不想为每个项目保存一份 MCP 配置，也可以使用未绑定的全局条目：

```toml
[mcp_servers.SpecAlign]
command = 'C:\Tools\specalign\specalign.exe'
args = ['serve']
```

未绑定服务启动时不扫描任何目录。agent 必须从当前工作区取得绝对路径，并在每次工具调用中传入 `root`；首次使用时可调用 `spec_init(root=...)` 创建配置和 `spec/`。返回中的 `project_root` 必须与当前项目一致。服务不会从 MCP 会话自动获取工作目录，也不会展开相对路径或 shell 变量。

## 移动、升级与卸载

- 安装配置记录 exe 的绝对路径。不要安装后删除或移动它；若移动，应在新位置重新运行 install --codex，并重新核对宿主信任。
- 关闭使用该 exe 的 MCP 进程后替换文件，重新启动服务。Windows 不允许覆盖正在运行的 exe。
- 从 Python 版迁移时可以对同一 root 运行 exe install --codex，安装器只更新有归属记录且未被手改的内容；如果拒绝覆盖，按报告保留并核对用户改动，不删除账本绕过检查。
- `uninstall --codex` 移除归属本工具且未被用户修改的集成；不会删除规范或审计账本。
- `.specalign/` 含历史审查，不是缓存。用 `backup 文件路径` 备份；恢复用 `restore 文件路径`，目标必须没有现存数据库。
- Git 提交检查可选 `install --git-hook`，需要本机另装 Git；MCP 和一般文档检查不需要 Git。

## 发布与验证边界

本包为 Windows x64 本地构建，未进行代码签名，未上传远程发布；不宣称已获 SmartScreen 信誉。
程序启动会将单文件内嵌依赖解包到系统临时目录，需要可写临时目录。
在当前 Windows 主机完成仓库外运行、Unicode/空格路径、无 Python PATH、MCP 协议和 hook 命令验证；未在全新 Windows 虚拟机或其他架构验证。
hook 启动时间受磁盘和杀毒扫描影响，本机测量不能代表所有设备。

第三方依赖版本和可获取的许可证文本在 BUILD-ENVIRONMENT.json 与 licenses/。
当前压缩包不替代代码仓库的授权条款；未声明额外的开源授权。

