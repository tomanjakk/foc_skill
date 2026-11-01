---
name: foc-skill
description: 面向 FOC 代码移植和调试的工作流；当前提供 Keil 工程检查、编译、烧录及 MKLink 共享后台和符号操作的基础流程。
---

# FOC 移植与调试

此 Skill 的目标是协助将 FOC 代码移植到目标工程并进行调试。当前版本仅建立 Keil 和 MKLink 基础工具流程；FOC 移植分析、板级适配与控制调试流程尚未完成，不能宣称已经支持自动移植或调试。

分析 FOC 的参数辨识、电流环、采样或轨迹调试时，按需读取 [历史调试经验](references/foc-debug-evidence.md)。这些经验是历史案例和检查思路，不能替代目标工程的源码分析和实测。

移植或调试编码器时，读取 [编码器移植与调试](references/encoder.md)，结合目标器件手册、原理图和实际采样时序核对。

移植或调试 PWM 定时器及 ADC 采样时，读取 [定时器与 ADC 采样](references/timer-and-adc.md)，结合目标芯片手册和板级电路核对。

移植或修改校准数据保存、恢复及 IAP 升级时，读取 [校准数据存储与 IAP 升级](references/storage-and-iap.md)，结合目标工程核对全部存储分区、擦写约束和升级协议。

默认中文沟通。先确认 FOC 来源、用户指定的目标工程、Target、工具链和操作范围。`python/keil/config.json` 包含初始工程配置；移植到其他目标时，核对并按需修改目标配置，同时检查脚本中的目标芯片及工程固定假设。配置中的相对路径以配置文件所在目录为基准，不修改无关项目。

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

检查脚本读取工程及下载配置，不启动 Keil 或连接设备。先核对输出路径、Target 和实际下载设置；`partitions` 和 AXF Flash 范围检查是原工程及 G474 的固定假设，不可用于断言其他工程的分区安全。编译脚本执行完整重建并检查终态、产物新鲜度和 AXF/HEX 一致性；烧录脚本独立触发重建。根据本次日志报告结果，不以旧日志代替实际执行。

## MKLink

现有脚本使用 `config.json` 中的 `mklink_sdk_path` 和 `mklink_probe`。它们只查找已存在的共享后台，不启动后台或建立新的探针连接；需要用户先在 MKLink 中连接目标。核对当前设备、固件和 AXF 匹配，不能仅凭路径相同认定固件一致。

```powershell
& 'D:/my_exe/python-3.9.13/python.exe' python/mklink/reload_symbols.py
& 'D:/my_exe/python-3.9.13/python.exe' python/mklink/read_variables.py FOC.Vbus FOC.Vbus_filt
```

重载脚本要求后台当前 AXF 路径与配置相同；读取脚本一次支持 1 至 16 个不重复的符号。重载或读取失败时报告原始错误和后台状态，不自动切换工程、重置设备或重试写入。MKLink 内部运行库接口可能随版本变化。

复制的 `python/keil/README.md` 和 `python/README.md` 中的工程相对路径针对原目录；实际路径以本目录 `config.json` 和本文件为准。离线测试不能证明下载或设备连接成功。
