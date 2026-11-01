import json
import sys
from pathlib import Path
from keil_common import config, project_info, image_info, fail

try:
    c = config()
    for key in ('python_executable', 'uv4_executable', 'project'):
        if not c[key].is_file(): raise FileNotFoundError(c[key])
    info = project_info(c)
    info.update({'python_running': sys.executable, 'python_version': sys.version,
                 'python_configured': str(c['python_executable']), 'uv4': str(c['uv4_executable']),
                 'project': str(c['project']), 'target': c['target'], 'axf': str(c['axf']),
                 'log_dir': str(c['log_dir']), 'erase_range': '由 Keil 下载设置决定，脚本不限制范围',
                 'partitions': {'boot_start': '0x08000000', 'marker': '0x08018800', 'app_start': '0x08019000'}})
    try: info['existing_image'] = image_info(c)
    except (OSError, ValueError) as e: info['existing_image'] = f'不可确认: {e}'
    print(json.dumps(info, ensure_ascii=False, indent=2))
except (OSError, ValueError, KeyError) as e: fail(e)
