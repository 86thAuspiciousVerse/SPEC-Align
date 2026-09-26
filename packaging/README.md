# Windows 可执行分发构建

在 Windows x64 Python 3.10 环境构建。本目录不修改宿主信任或凭据。

```powershell
python -m venv .venv-build
& ./.venv-build/Scripts/python.exe -m pip install --no-user -r packaging/build-requirements-windows.txt
& ./.venv-build/Scripts/python.exe -m pip install --no-user --no-deps .
& ./.venv-build/Scripts/python.exe packaging/build_exe.py
& ./.venv-build/Scripts/python.exe packaging/smoke_exe.py dist/windows/specalign.exe
& ./.venv-build/Scripts/python.exe -m pytest -q
& ./.venv-build/Scripts/python.exe packaging/release_zip.py
```

产物是 `dist/windows/specalign.exe` 和按当前包版本命名的 `dist/specalign-<version>-windows-x64.zip`，ZIP 内有可执行文件、说明、协议、环境清单和许可证。构建依赖已锁定具体版本；未承诺跨构建字节级复现。

smoke 将 exe 复制到仓库外的中文/空格目录，移除子进程 PATH 中的 Python，执行初始化、安装/卸载、生成的 hook 命令、真实 MCP 握手/10工具发现/查询/批量复核和备份，并验证未绑定 MCP 的显式 root 模式。驱动测试的 Python 不是被测 exe 的运行依赖。

单文件使用 PyInstaller 内嵌解释器与依赖；安装器以冻结后的 sys.executable 生成持久配置，不能使用临时解包路径，也不能附带 `-m specalign`。[PyInstaller 运行说明](https://pyinstaller.org/en/stable/runtime-information.html)。

测试为当前主机实测，不等同于无 Python 的干净虚拟机验收。发行前应核对 CI、分发包内容及校验和；Windows EXE 未签名，不能承诺 SmartScreen 信誉。
