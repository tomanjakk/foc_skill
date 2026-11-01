import json
import time
from keil_common import config, project_info, image_info, run_keil, build_result, fail


def build():
    c = config(); c['log_dir'].mkdir(parents=True, exist_ok=True)
    record = c['log_dir'] / 'last_success.json'
    record.unlink(missing_ok=True)
    info = project_info(c)
    old = {p: p.stat().st_mtime_ns if p.exists() else None for p in (c['axf'], c['axf'].with_suffix('.hex'))}
    started_ns = time.time_ns()
    result, log = run_keil(c, '-r', 'build', build_result)
    output, errors, warnings = result
    if int(errors) != 0: raise RuntimeError(f'编译失败: {errors} 错误, {warnings} 警告；{log}')
    if output.replace('\\', '/').split('/')[-1].lower() != c['axf'].name.lower():
        raise RuntimeError(f'日志中的输出文件不匹配: {output}')
    for p, previous in old.items():
        if not p.is_file() or p.stat().st_mtime_ns == previous or p.stat().st_mtime_ns < started_ns - 2_000_000_000:
            raise RuntimeError(f'未确认本次生成文件: {p}；日志: {log}')
    if not list(c['object_dir'].glob('*.o')): raise RuntimeError('输出目录没有对象文件')
    if project_info(c) != info: raise RuntimeError('构建期间工程或下载配置发生变化')
    image = image_info(c)
    result = {'project': str(c['project']), 'target': c['target'], 'axf': str(c['axf']),
              'project_info': info, 'image': image, 'build_log': str(log),
              'started_ns': started_ns, 'warnings': int(warnings)}
    tmp = record.with_suffix('.tmp'); tmp.write_text(json.dumps(result, indent=2), encoding='utf-8'); tmp.replace(record)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    try: build()
    except (OSError, ValueError, KeyError, RuntimeError) as e: fail(e)
