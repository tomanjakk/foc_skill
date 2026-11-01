---
name: foc-skill
description: 协助将现有 FOC 移植到目标 MCU 并分阶段调试，覆盖 PWM/ADC、编码器、校准存储、IAP，以及 Keil 和 MKLink 工具。
---

# FOC 移植与调试

此 Skill 协助将用户提供的 FOC 代码移植到目标工程并调试，包含 PWM/ADC、编码器、校准存储、IAP 和历史调试经验。配套工具支持 Keil 工程检查、编译、烧录，以及 MKLink 符号重载和变量读取。各专题是适配与验证指导，不等于自动移植或板级验证完成；FOC 算法源码须由用户提供或从目标工程确认。

## 移植顺序

进行完整 FOC 移植或首次调试时，先读 [FOC 移植与验证总流程](references/porting-workflow.md)，按实际任务范围执行适用阶段，记录每阶段的验证依据和未完成事项；只处理某个专题时读取对应文档即可。

分析 FOC 的参数辨识、电流环、采样或轨迹调试时，按需读取 [历史调试经验](references/foc-debug-evidence.md)。这些经验是历史案例和检查思路，不能替代目标工程的源码分析和实测。

移植或调试编码器时，读取 [编码器移植与调试](references/encoder.md)，结合目标器件手册、原理图和实际采样时序核对。

移植或调试 PWM 定时器及 ADC 采样时，读取 [定时器与 ADC 采样](references/timer-and-adc.md)，结合目标芯片手册和板级电路核对。

移植或修改校准数据保存、恢复及 IAP 升级时，读取 [校准数据存储与 IAP 升级](references/storage-and-iap.md)，结合目标工程核对全部存储分区、擦写约束和升级协议。

默认中文沟通。先确认 FOC 来源、用户指定的目标工程、Target、工具链和操作范围。`python/keil/config.json` 包含初始工程配置；移植到其他目标时先按 [工具配置说明](python/keil/README.md) 检查和修改配置。路径类配置的相对路径以配置文件所在目录为基准，不修改无关项目。

## 操作边界

- 编译、烧录、连接或采集设备、重配观察项和写目标分别遵循用户的明确授权；修改代码后不自动编译、下载或运行。
- 烧录脚本会先完整重建，使用已保存的 Keil 下载配置，**不限制擦除区域**。执行前确认目标、固件、下载器、Flash 算法、擦除范围以及可能受影响的 App、标记和数据；无法确认则停止。
- MKLink 变量读取会访问设备；采集中对缺失变量可能添加观察项并短暂重配置采集。符号重载会改变共享后台状态。未经对应授权不执行。
- 不运行 `python/history` 或其他实机诊断脚本；它们可能写源码、目标变量或驱动电机，不属于本框架当前范围。

## Keil

从此 Skill 目录执行，使用本机已安装的 Python：

```powershell
python python/keil/keil_check.py
python python/keil/keil_build.py
python python/keil/keil_flash.py
```

检查脚本读取工程及下载配置，不启动 Keil 或连接设备。先核对输出路径、Target、`flash_ranges` 和实际下载设置；镜像范围检查不检查分区安全，也不约束下载擦除范围。编译脚本执行完整重建并检查终态、产物新鲜度和 AXF/HEX 一致性；烧录脚本独立触发重建。根据本次日志报告结果，不以旧日志代替实际执行。

## MKLink

现有脚本使用 `config.json` 中的 `mklink_sdk_path` 和 `mklink_probe`。它们只查找已存在的共享后台，不启动后台或建立新的探针连接；需要用户先在 MKLink 中连接目标。脚本从配置目录加载 MKLink 包并检查来源和所需接口；后台协议兼容性仍需实际核对。核对当前设备、固件和 AXF 匹配，不能仅凭路径相同认定固件一致。

```powershell
python python/mklink/reload_symbols.py
python python/mklink/read_variables.py FOC.Vbus FOC.Vbus_filt
```

重载脚本要求后台当前 AXF 路径与配置相同；读取脚本一次支持 1 至 16 个不重复的符号。重载或读取失败时报告原始错误和后台状态，不自动切换工程、重置设备或重试写入。MKLink 内部运行库接口可能随版本变化。

历史脚本和归档文件可能依赖原工程路径；实际路径以本目录 `config.json` 和工具配置说明为准。离线测试不能证明下载或设备连接成功。
