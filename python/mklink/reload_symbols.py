"""通过 MKLink 当前共享后台重新加载已选中的 AXF，不操作 MCU。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from sdk_loader import load_runtime

CONFIG_PATH = Path(__file__).resolve().parents[1] / 'keil/config.json'


def same_path(first, second):
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def reload_symbols(info, request, axf, force=False):
    axf = Path(axf).resolve()
    if not axf.is_file():
        raise ValueError(f'AXF 文件不存在: {axf}')
    before = request(info, 'GET', '/api/symbols/status')
    if not before.get('loaded') or not same_path(before.get('axf_path', ''), str(axf)):
        raise ValueError('后台当前符号文件与配置的 AXF 不一致，不自动切换工程')
    event = before.get('file_source_change') or {}
    changed = bool(before.get('stale') or event.get('pending'))
    if changed or force:
        # 使用 GUI 的共享后台入口；后台负责冲突仲裁及采集重绑定。
        request(info, 'POST', '/api/symbols/reload-sources', {})
    after = request(info, 'GET', '/api/symbols/status')
    digest = hashlib.sha256(axf.read_bytes()).hexdigest()
    if (not after.get('loaded') or after.get('stale') or
            (after.get('file_source_change') or {}).get('pending') or
            not same_path(after.get('axf_path', ''), str(axf)) or
            after.get('fingerprint', {}).get('sha256') != digest):
        raise RuntimeError('符号重载后状态或 AXF 摘要不一致')
    if (changed or force) and after.get('generation') == before.get('generation'):
        raise RuntimeError('请求重载后符号版本没有更新')
    return {'status': 'reloaded' if changed or force else 'already_current',
            'axf': str(axf), 'generation': after.get('generation'), 'sha256': digest,
            'rebind': (after.get('file_source_change') or {}).get('rebind')}


def main():
    parser = argparse.ArgumentParser(description='重新加载当前 MKLink 后台的 AXF 符号')
    parser.add_argument('--force', action='store_true', help='即使符号最新也重新加载')
    args = parser.parse_args()
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    runtime = load_runtime(CONFIG_PATH.parent / config['mklink_sdk_path'])
    info = runtime.selected_runtime(config['mklink_probe'])
    if info is None:
        raise RuntimeError('未找到配置的 MKLink 共享后台，请先在 MKLink 中连接目标')
    axf = (CONFIG_PATH.parent / config['axf']).resolve()
    print(json.dumps(reload_symbols(info, runtime.request, axf, args.force), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'符号重载失败: {exc}', file=sys.stderr)
        sys.exit(1)
