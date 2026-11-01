"""从 MKLink 共享后台读取变量；运行采集中优先使用最新共享快照。"""
import argparse
import json
from pathlib import Path
import sys
import time
from sdk_loader import load_runtime

CONFIG = Path(__file__).resolve().parents[1] / 'keil/config.json'


def read_variables(info, request, names):
    if not names or len(names) > 16 or len(set(names)) != len(names):
        raise ValueError('变量必须为 1～16 个且不能重复')
    symbols = request(info, 'GET', '/api/symbols/status')
    if not symbols.get('loaded') or symbols.get('stale') or (symbols.get('file_source_change') or {}).get('pending'):
        raise RuntimeError('符号待重新加载，请先运行 reload_symbols.py')
    status = request(info, 'GET', '/api/dash/superwatch/status')
    if status.get('state') == 'stopped':
        rows = request(info, 'POST', '/api/device/watch', {'names': names})['rows']
        if {r['name'] for r in rows} != set(names):
            raise RuntimeError('读取结果不完整')
        return {'source': 'watch', 'values': {r['name']: r['value'] for r in rows}}
    if status.get('state') != 'running':
        raise RuntimeError(f"SuperWatch 状态不适合读取: {status.get('state')}")
    existing = {item['name'] for item in status.get('items', [])}
    for name in names:
        if name not in existing:
            request(info, 'POST', '/api/dash/superwatch/add', {'name': name})
    # 只读取后台共享缓存，等待新增通道出现在新一批采集中。
    deadline = time.monotonic() + 3.0
    while True:
        result = request(info, 'GET', '/api/dash/superwatch/latest')
        sample = result.get('sample') or {}
        channels = sample.get('channels') or []
        values = sample.get('values') or []
        readings = {channel['name']: value for channel, value in zip(channels, values)}
        age = result.get('age_seconds')
        if result.get('running') and age is not None and age <= 2.0 and all(n in readings for n in names):
            return {'source': 'superwatch', 'values': {n: readings[n] for n in names},
                    'sample_age_seconds': age, 'sequence': sample.get('sequence')}
        if time.monotonic() >= deadline:
            raise RuntimeError('没有取得包含全部变量的实时共享快照')
        time.sleep(0.05)


def main():
    parser = argparse.ArgumentParser(description='读取当前 MKLink 后台变量')
    parser.add_argument('names', nargs='+', help='变量名，例如 FOC.Vbus_filt')
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
    runtime = load_runtime(CONFIG.parent / cfg['mklink_sdk_path'])
    info = runtime.selected_runtime(cfg['mklink_probe'])
    if info is None:
        raise RuntimeError('未找到配置的 MKLink 共享后台，请先连接目标')
    print(json.dumps(read_variables(info, runtime.request, args.names), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'读取失败: {exc}', file=sys.stderr)
        sys.exit(1)
