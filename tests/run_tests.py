#!/usr/bin/env python3
"""跑全部测试（不需要 nonebot / astrbot）。

    python tests/run_tests.py          # 全跑
    python tests/run_tests.py persona  # 只跑名字带 persona 的
"""

from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:  # Windows 控制台默认 GBK，中文/✓ 会炸
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MODULES = ["test_detector_eval", "test_quality_layer", "test_persona"]


def main(argv: list[str]) -> int:
    only = argv[1] if len(argv) > 1 else ""
    passed = failed = 0
    for name in MODULES:
        if only and only not in name:
            continue
        mod = importlib.import_module(f"tests.{name}")
        for attr in dir(mod):
            if not attr.startswith("test_"):
                continue
            fn = getattr(mod, attr)
            if not callable(fn):
                continue
            try:
                fn()
            except Exception:
                failed += 1
                print(f"FAIL  {name}.{attr}")
                traceback.print_exc()
            else:
                passed += 1
                print(f"ok    {name}.{attr}")
    print()
    print(f"{'全部通过 ✓' if not failed else '有失败 ✗'}   {passed} 项通过，{failed} 项失败")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
