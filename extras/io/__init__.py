import importlib
import pkgutil
from pathlib import Path

from utilities.console import console


class IOFormatBase:
    """导入导出格式基类"""
    ext: str = ""  # 文件后缀

    def import_file(self, context, filepath, temp_dir):
        raise NotImplementedError

    def export_file(self, context, filepath, temp_dir):
        raise NotImplementedError


_handlers = {}


def _discover():
    """自动扫描目录下的 py 文件并加载格式处理器"""
    global _handlers
    _handlers.clear()
    package_dir = Path(__file__).parent
    for _, name, _ in pkgutil.walk_packages([str(package_dir)], prefix=f"{__name__}."):
        if name.startswith("_"):
            continue
        mod = importlib.import_module(name)
        for attr in dir(mod):
            cls = getattr(mod, attr)
            if isinstance(cls, type) and cls.__base__.__name__ == IOFormatBase.__name__ and cls.ext:
                _handlers[cls.ext] = cls()


def get_handler(ext):
    return _handlers.get(ext)


def get_extensions():
    return list(_handlers.keys())


_discover()