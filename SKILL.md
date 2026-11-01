---
name: foc-skill
description: 使用本套 Python 工具检查 Keil 工程、编译和烧录，以及连接既有 MKLink 共享后台、重载符号和读取变量。适用于用户要求操作或排查对应 Keil 和 MKLink 工作流时。
---

# Keil 和 MKLink 工程工具

默认中文沟通。先确认用户指定的工程、Target、工具链和操作范围；配置在 `python/keil/config.json`，相对路径以该配置文件所在目录为基准。当前配置指向 P50w Bootloader，不代表其他工程可以直接使用。更换工程前先核对并按需修改配置及脚本假设，不修改无关项目。

## 操作边界

- 编译、烧录、连接或采集设备、重配观察项和写目标分别遵循用户的明确授权；修改代码后不自动编译、下载或运行。
- 烧录脚本会先完整重建，使用已保存的 Keil 下载配置，**不限制擦除区域**。执行前确认目标、固件、下载器、Flash 算法、擦除范围以及可能受影响的 App、标记和数据；无法确认则停止。
- MKLink 变量读取会访问设备；采集中对缺失变量可能添加观察项并短暂重配置采集。符号重载会改变共享后台状态。未经对应授权不执行。
- 不运行 `python/history` 或其他实机诊断脚本；它们可能写源码、目标变量或驱动电机，不属于本框架当前范围。

## Keil

从此 Skill 目录执行，使用配置中指定的 Python：

```powershell
& 'D:/my_exe/python-3.9.13/python.exe' python/keil/keil_check.py
& 'D:/my_exe/python-3.9.13/python.exe' python/keil/keil_build.py
& 'D:/my_exe/python-3.9.13/python.exe' python/keil/keil_flash.py
```

检查脚本读取工程及下载配置，不启动 Keil 或连接设备。先核对输出路径、Target 和实际下载设置；`partitions` 和 AXF Flash 范围检查是当前 P50w/G474 假设，不可用于断言其他工程的分区安全。编译脚本执行完整重建并检查终态、产物新鲜度和 AXF/HEX 一致性；烧录脚本独立触发重建。根据本次日志报告结果，不以旧日志代替实际执行。

## MKLink

现有脚本使用 `config.json` 中的 `mklink_sdk_path` 和 `mklink_probe`。它们只查找已存在的共享后台，不启动后台或建立新的探针连接；需要用户先在 MKLink 中连接目标。核对当前设备、固件和 AXF 匹配，不能仅凭路径相同认定固件一致。

```powershell
& 'D:/my_exe/python-3.9.13/python.exe' python/mklink/reload_symbols.py
& 'D:/my_exe/python-3.9.13/python.exe' python/mklink/read_variables.py FOC.Vbus FOC.Vbus_filt
```

重载脚本要求后台当前 AXF 路径与配置相同；读取脚本一次支持 1 至 16 个不重复的符号。重载或读取失败时报告原始错误和后台状态，不自动切换工程、重置设备或重试写入。MKLink 内部运行库接口可能随版本变化。

复制的 `python/keil/README.md` 和 `python/README.md` 中的工程相对路径针对原目录；实际路径以本目录 `config.json` 和本文件为准。离线测试不能证明下载或设备连接成功。
