#!/usr/bin/env python3
"""和上游同名的测试入口（保持兼容）。

    python scripts/run_tests.py          # 全跑（= tests/run_tests.py）
    python scripts/run_tests.py core     # 只跑核心（不含人格适配）
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
argv = [sys.executable, str(ROOT / "tests" / "run_tests.py")]
if len(sys.argv) > 1 and sys.argv[1] == "core":
    argv.append("quality_layer")
elif len(sys.argv) > 1:
    argv.append(sys.argv[1])
raise SystemExit(subprocess.call(argv))
