# Keil 编译与下载脚本

使用 Python 标准库。编辑 `config.json` 设置 Keil、工程、Target、输出和日志路径；相对路径以本目录为基准。当前配置：

此前的 `codex_*.uvprojx`、配套 `.uvoptx` 和 `MDK-ARM` 根目录历史日志已归档到 `archive/MDK-ARM/`。这些工程的相对路径以原目录为基准，若需使用应先将相应工程和配置文件恢复到 `MDK-ARM`。历史文档与一次性脚本中提到的原路径同样需先恢复后才能使用。

- 工程：`P50w_Bootloader/MDK-ARM/STM32g474vet6.uvprojx`，Target：`STM32g474vet6`。
- AXF：`P50w_Bootloader/MDK-ARM/STM32g474vet6/STM32g474vet6.axf`；`.o` 和 HEX 在同一目录。
- 日志和上一次成功构建记录：`P50w_Bootloader/python/keil/logs/`。

在仓库根目录运行：

```powershell
python P50w_Bootloader/python/keil/keil_check.py
python P50w_Bootloader/python/keil/keil_build.py
python P50w_Bootloader/python/keil/test_keil_tools.py
```

`keil_build.py` 对指定 Target 执行完整重建；必须有本次更新的 AXF、HEX、Keil 终态日志和零错误，且 AXF/HEX Flash 内容一致才记录成功。未出现日志终态、非零退出码、旧文件或解析失败均报告失败。每次构建先移除上次成功记录。

Keil 中打开的工程可能缓存 `.uvprojx` 设置；本脚本不会控制已打开窗口，如输出设置被窗口重新覆盖，检查会报路径不一致。若出现 `.d` 文件被映射占用，请关闭相关 Keil 窗口后重试。

## 烧录

```powershell
python P50w_Bootloader/python/keil/keil_flash.py
```

脚本先完整重建，再使用 Keil 工程已有的下载器、Flash 算法和擦除设置烧录；编译失败不会执行烧录，日志显示擦除、编程和校验完成后才报告成功。Keil 窗口可以打开或关闭；修改代码和下载配置后应先保存。

J-Link 和 MKLink 在 Keil 中选择对应驱动，脚本不修改下载配置。**脚本不限制擦除区域**：若 Keil 选择整片擦除，会影响 APP、有效标记和片内数据。当前截图显示的是 Erase Sectors；实际设置以已保存的 Keil 工程为准。

## MKLink 重新加载符号

Keil 烧录成功后，若 MKLink 报告 AXF 已变化或等待重新加载，执行：

```powershell
python P50w_Bootloader/python/mklink/reload_symbols.py
```

只查询并重载配置中指定的已有 MKLink 共享后台和当前 AXF，不启动新后台、不下载、不修改 MCU；符号已是最新时直接报告 `already_current`。用于验证的 `--force` 会强制重载一次。请求由后台仲裁，遇到冲突或版本不匹配会报错，不会断开或强制停止其他操作。

配置项 `mklink_sdk_path` 指向桌面版当前附带的 Python 运行库，`mklink_probe` 为设备稳定 ID；更换安装路径或下载器后应更新这两项。脚本使用桌面端同一重载接口，MKLink 升级时该内部接口或运行库布局可能变化。重载后应重新连接使用旧符号版本的客户端。

验证：`python P50w_Bootloader/python/mklink/test_reload_symbols.py`；2026-10-30 已通过 MKLink 0.4.1 强制重载，并实际读取 FOC.Vbus 和 FOC.Vbus_filt。

## 读取 MKLink 变量

```powershell
python P50w_Bootloader/python/mklink/read_variables.py testmklnik FOC.Vbus FOC.Vbus_filt
```

可按需替换变量名，一次最多 16 个。SuperWatch 停止时直接读取；运行中读取共享采集的最新快照，未在采集中的变量会加入观察项。加入观察项可能导致后台短暂重配置采集，但脚本不主动停止采集、不删除现有观察项。读取结果包含来源；共享快照还包含时间差和序号。符号过期时先运行重载脚本。

读取工具使用同一 `mklink_sdk_path` 和 `mklink_probe` 配置。2026-10-30 已实测停止采集时的直接读取；运行中分支通过离线模拟验证，尚未用该脚本做实机采集验证。
