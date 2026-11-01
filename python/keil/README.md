# Keil 与 MKLink 工具配置

本目录的 `config.json` 是历史工程配置，不是其他电脑或工程的默认配置。首次使用或更换目标前，复制记录现有配置，再根据目标工程修改；相对路径以 `config.json` 所在目录为基准。不得通过填写错误范围来使检查通过。

| 配置项 | 应填写或核对的内容 |
|---|---|
| `python_executable` | 本机 Python 可执行文件路径；检查工具会验证该文件存在。运行命令使用的 Python 应与预期环境一致。 |
| `uv4_executable` | 本机 Keil `UV4.exe` 路径。 |
| `project`、`target` | 目标 `.uvprojx` 的路径和准确 Target 名称；确认对应 `.uvoptx` 是当前保存的下载配置。 |
| `axf`、`object_dir` | Target 实际输出的 AXF 与输出目录；必须与工程配置一致，且工程启用 AXF 和 HEX。 |
| `log_dir`、`timeout_seconds` | 本机日志目录和编译超时时间；日志只证明对应那次执行。 |
| `flash_ranges` | 根据目标实际地址映射配置镜像 Flash 地址范围，可指定多个不重叠区间；`start` 含首地址、`end_exclusive` 不含尾地址，使用十六进制字符串。此项只用于检查 AXF/HEX 内容一致与地址范围，**不检查分区或下载器擦除范围**。 |
| `mklink_sdk_path` | MKLink 桌面程序附带的 Python 运行库根目录，目录下应存在 `mklink/__init__.py` 和 `mklink/runtime.py`；必须与当前后台版本兼容。 |
| `mklink_probe` | 当前使用的探针稳定 ID；更换探针后重新确认，不照搬历史 ID。 |

例如 `"flash_ranges": [{"start": "0x08000000", "end_exclusive": "0x08080000"}]` 表示 `[0x08000000, 0x08080000)`；只是格式示例，不能证明目标具备该容量或该区域可擦写。更换 MCU、Bank 配置或工程后，结合手册、链接设置及实际硬件重新确定。

## 首次检查和执行

在 Skill 根目录执行 `python python/keil/keil_check.py`。它读取已保存的工程和下载配置，不启动 Keil、不连接设备；核对输出中的 Target、路径、芯片、Flash 范围和下载配置。缺少 Flash 范围或配置错误时先修正；编译产物不存在时不会据此声称镜像一致。检查结果不证明固件分区、校准数据或擦除策略安全。

有编译授权时运行 `python python/keil/keil_build.py`。它完整重建，并核对日志终态、产物新鲜度和 AXF/HEX 数据。烧录 `python python/keil/keil_flash.py` 会重新编译并使用 Keil 已保存的下载器与擦除设置，**不限制擦除范围**；先确认目标、算法、下载范围和所有保留数据，并取得对应授权。

使用 MKLink 前由用户启动程序并连接目标。按授权运行 `python python/mklink/reload_symbols.py` 或 `python python/mklink/read_variables.py FOC.Vbus`。脚本使用配置指定的 SDK；版本或接口不兼容时报告错误，不自动切换 SDK、工程或后台。符号文件摘要一致不证明 MCU 内实际固件相同。

## 离线测试和历史文件

在 Skill 根目录执行：

```powershell
python python/keil/test_keil_tools.py
python python/mklink/test_sdk_loader.py
python python/mklink/test_read_variables.py
python python/mklink/test_reload_symbols.py
```

这些测试使用临时文件或模拟后台，不启动 Keil、不连接设备。`archive/MDK-ARM/` 和 `logs/` 是历史工程或日志，路径与当时环境相关，只作参考，不作为当前构建或下载成功的证据。其他历史脚本可能修改源码、写设备或驱动电机，不因存在而执行。
