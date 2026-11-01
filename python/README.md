# Python 脚本

当前可用的 Keil 和 MKLink 基础工具及换电脑配置步骤见 [工具配置说明](keil/README.md)。以下其他脚本和路径来自历史工程，未适配新目标时只作参考。

- `tests/`：离线单元测试与位置带宽模型。运行：`python -m unittest discover -s P50w_Bootloader/python/tests -v`；位置带宽模型单独运行 `python P50w_Bootloader/python/tests/test_position_bandwidth.py`。
- `mklink/`：连接 MKLink 的采集、诊断和实机测试脚本；部分脚本会写目标变量或驱动电机，使用前先查看源码。采集结果仍写入项目 `.mklink/`。
- `history/`：过去用于修改源码、创建调试工程的一次性脚本，仅供查阅；重复运行可能修改当前工程。
- `tools/`：其他工具脚本。`convert_encoding.py` 包含旧工程绝对路径和文件写入操作，使用前需先检查内容与目标路径。

脚本中的 Keil AXF 路径来自当时的测试版本，实机使用前应核对烧录固件和加载符号是否匹配。
