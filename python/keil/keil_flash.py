"""使用 Keil 工程现有的下载配置编译并烧录。"""
import json
import re
from keil_common import config, run_keil, fail
from keil_build import build


def flash_result(text):
    if re.search(r'Error:|Erase Failed|Programming Failed|Verify Failed|Flash Download failed', text, re.I):
        return 'failed'
    if re.search(r'Erase Done\.', text) and re.search(r'Programming Done\.', text) and re.search(r'Verify OK\.', text) and re.search(r'Flash Load finished', text):
        return 'success'
    return None


def flash():
    c = config()
    result = build()
    state, log = run_keil(c, '-f', 'flash', flash_result)
    if state != 'success': raise RuntimeError(f'烧录失败；日志: {log}')
    print(json.dumps({'status': state, 'log': str(log), 'image': result['image']}, indent=2))


if __name__ == '__main__':
    try: flash()
    except (OSError, ValueError, KeyError, RuntimeError) as e: fail(e)
