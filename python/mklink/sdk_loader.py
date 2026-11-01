"""从配置指定的 MKLink 安装目录加载运行库。"""
import importlib
import importlib.util
from pathlib import Path
import sys


def load_runtime(sdk_path):
    sdk = Path(sdk_path).resolve()
    package = sdk / 'mklink'
    init = package / '__init__.py'
    if not init.is_file() or not (package / 'runtime.py').is_file():
        raise ValueError(f'MKLink Python 运行库不存在或不完整: {sdk}')
    existing = sys.modules.get('mklink')
    if existing is not None:
        origin = getattr(existing, '__file__', None)
        if not origin or Path(origin).resolve() != init.resolve():
            raise RuntimeError('已加载其他 MKLink 运行库，请使用新 Python 进程并检查 SDK 路径')
    else:
        # 仅指定 mklink 包的来源，标准库仍优先于安装目录中的其他模块。
        sys.path.append(str(sdk))
        spec = importlib.util.spec_from_file_location('mklink', init, submodule_search_locations=[str(package)])
        if spec is None or spec.loader is None:
            raise RuntimeError(f'无法加载 MKLink 运行库: {sdk}')
        module = importlib.util.module_from_spec(spec)
        sys.modules['mklink'] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop('mklink', None)
            raise
    runtime = importlib.import_module('mklink.runtime')
    if Path(runtime.__file__).resolve() != (package / 'runtime.py').resolve():
        raise RuntimeError('MKLink runtime 来源与配置不一致，请使用新 Python 进程')
    if not callable(getattr(runtime, 'request', None)) or not callable(getattr(runtime, 'selected_runtime', None)):
        raise RuntimeError(f'MKLink 运行库接口不兼容: {sdk}')
    return runtime
