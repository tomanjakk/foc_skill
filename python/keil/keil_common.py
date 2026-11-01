"""Keil 项目检查、日志解析及 Intel HEX 地址校验。"""
import hashlib
import json
import re
import struct
import sys
import time
import uuid
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BASE = Path(__file__).resolve().parent
CONFIG = BASE / 'config.json'


def config():
    c = json.loads(CONFIG.read_text(encoding='utf-8'))
    for key in ('python_executable', 'uv4_executable', 'project', 'axf', 'object_dir', 'log_dir'):
        p = Path(c[key]); c[key] = p.resolve() if p.is_absolute() else (BASE / p).resolve()
    return c


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_info(c):
    project = c['project']
    tree = ET.parse(project).getroot()
    targets = tree.findall('./Targets/Target')
    names = [t.findtext('TargetName') for t in targets]
    selected = [t for t in targets if t.findtext('TargetName') == c['target']]
    if len(selected) != 1: raise ValueError(f'Target 不唯一或不存在: {names}')
    t = selected[0]
    def get(tag):
        return t.findtext('.//' + tag, default='').strip()
    directory = (project.parent / get('OutputDirectory').replace('\\', '/')).resolve()
    output = directory / (get('OutputName') + '.axf')
    if directory != c['object_dir'] or output != c['axf']:
        raise ValueError(f'输出路径与配置不一致: {directory}, {output}')
    if get('CreateExecutable') != '1' or get('CreateHexFile') != '1':
        raise ValueError('工程未同时启用 AXF 和 HEX 输出')
    opt = project.with_suffix('.uvoptx')
    if not opt.is_file(): raise ValueError('缺少对应 .uvoptx，无法核对下载配置')
    options = ET.parse(opt).getroot()
    matches = [x for x in options.findall('./Target') if x.findtext('TargetName') == c['target']]
    if len(matches) != 1: raise ValueError('uvoptx 中未找到唯一的 Target 配置')
    debug = matches[0].findtext('.//DebugOpt/pMon', default='')
    registry = {x.findtext('Key', default=''): x.findtext('Name', default='')
                for x in matches[0].findall('.//TargetDriverDllRegistry/SetRegEntry')}
    scatter = (project.parent / get('ScatterFile').replace('\\', '/')).resolve()
    irom = t.find('.//OnChipMemories/IROM')
    if irom is None: raise ValueError('缺少 IROM 配置')
    use_scatter = get('useFile') == '1'
    if use_scatter and not scatter.is_file(): raise ValueError('启用的 scatter 文件不存在')
    return {'targets': names, 'device': get('Device'), 'cpu': get('Cpu'),
            'output_dir': str(directory), 'output_name': get('OutputName'),
            'scatter': str(scatter), 'scatter_enabled': use_scatter,
            'irom_start': irom.findtext('StartAddress'), 'irom_size': irom.findtext('Size'),
            'download_config': str(opt), 'opt_sha256': sha(opt),
            'project_sha256': sha(project),
            'scatter_sha256': sha(scatter) if use_scatter else None,
            'download_driver': get('Flash2'), 'use_target_dll': get('UseTargetDll'),
            'debug_monitor': debug, 'debug_registry': registry}


def ihex(path):
    data = {}; base = 0; eof = False
    for line in path.read_text(encoding='ascii').splitlines():
        if not line.startswith(':') or eof: raise ValueError('HEX 记录格式错误')
        raw = bytes.fromhex(line[1:]); n = raw[0]
        if len(raw) != n + 5 or sum(raw) & 255: raise ValueError('HEX 长度或校验错误')
        addr = int.from_bytes(raw[1:3], 'big'); typ = raw[3]; payload = raw[4:-1]
        if typ == 0:
            for i, byte in enumerate(payload):
                a = base + addr + i
                if a in data and data[a] != byte: raise ValueError('HEX 地址重叠')
                data[a] = byte
        elif typ == 1:
            if n != 0: raise ValueError('HEX EOF 错误')
            eof = True
        elif typ in (2, 4):
            if n != 2: raise ValueError('HEX 扩展地址错误')
            base = int.from_bytes(payload, 'big') << (4 if typ == 2 else 16)
        elif typ not in (3, 5): raise ValueError('不支持的 HEX 记录')
    if not eof or not data: raise ValueError('HEX 无有效数据或 EOF')
    return data


def axf_flash(path):
    b = path.read_bytes()
    if b[:7] != b'\x7fELF\x01\x01\x01': raise ValueError('仅支持 32 位小端 ELF AXF')
    phoff = struct.unpack_from('<I', b, 28)[0]
    entsize, count = struct.unpack_from('<HH', b, 42)
    if entsize < 32 or phoff + entsize * count > len(b): raise ValueError('AXF 段表错误')
    data = {}
    for i in range(count):
        typ, offset, _vaddr, physical, filesz, _memsz, _flags, _align = struct.unpack_from('<8I', b, phoff + i * entsize)
        if typ != 1 or filesz == 0 or not (0x08000000 <= physical < 0x08080000): continue
        if offset + filesz > len(b) or physical + filesz > 0x08080000: raise ValueError('AXF Flash 段越界')
        for j, byte in enumerate(b[offset:offset + filesz]):
            if physical+j in data and data[physical+j] != byte: raise ValueError('AXF 段重叠')
            data[physical+j] = byte
    if not data: raise ValueError('AXF 无 Flash 加载段')
    return data


def image_info(c):
    hx = c['axf'].with_suffix('.hex')
    hex_data = ihex(hx); elf_data = axf_flash(c['axf'])
    if hex_data != elf_data: raise ValueError('AXF 与 HEX Flash 数据不一致')
    return {'start': min(hex_data), 'end_exclusive': max(hex_data)+1,
            'bytes': len(hex_data), 'axf_sha256': sha(c['axf']), 'hex_sha256': sha(hx)}


def read_log(path):
    b = path.read_bytes()
    for enc in ('utf-8-sig', 'gbk', 'cp1252'):
        try: return b.decode(enc)
        except UnicodeDecodeError: pass
    raise ValueError('无法解码 Keil 日志')


def build_result(log):
    matches = re.findall(r'"([^"\r\n]+\.axf)"\s*-\s*(\d+) Error\(s\),\s*(\d+) Warning\(s\)\.', log, re.I)
    return matches[-1] if matches else None


def run_keil(c, action, name, parser):
    c['log_dir'].mkdir(parents=True, exist_ok=True)
    path = c['log_dir'] / (name + '_' + uuid.uuid4().hex + '.log')
    cmd = [str(c['uv4_executable']), action, str(c['project']), '-t', c['target'], '-o', str(path)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + c['timeout_seconds']; state = None
    # UV4 可能先返回，由 Keil 后台继续写日志；两者都必须完成。
    while time.monotonic() < deadline:
        if proc.poll() is not None and path.exists():
            text = read_log(path); state = parser(text)
            if state is not None: break
        time.sleep(.2)
    if state is None:
        if proc.poll() is None: proc.terminate()
        raise RuntimeError(f'Keil 结果无法确认或超时；日志: {path}')
    stdout, _ = proc.communicate()
    if stdout:
        with path.open('ab') as f: f.write(b'\n--- UV4 stdout/stderr ---\n' + stdout)
    if proc.returncode != 0: raise RuntimeError(f'Keil 退出码 {proc.returncode}；日志: {path}')
    return state, path


def fail(exc):
    print('失败:', exc, file=sys.stderr)
    sys.exit(1)
