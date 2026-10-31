"""测试支持：把插件目录当成包挂上，但**不执行 __init__.py**（那里 import nonebot）。

这样单测可以在没装 nonebot 的机器上跑（和肥鱼机器人其它测试一个思路：
只测纯逻辑，宿主环境的东西放到线上探针里测）。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = "nonebot_plugin_fishhumanq"


def ensure_package() -> None:
    if PKG in sys.modules:
        return
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT / PKG)]  # type: ignore[attr-defined]
    sys.modules[PKG] = pkg
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def import_sub(name: str):
    ensure_package()
    return __import__(f"{PKG}.{name}", fromlist=["*"])
