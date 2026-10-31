"""冻结评测集门禁：261 例，要求 0 误报 / 0 漏报（和上游同一条门禁）。

检测器是从上游原样搬过来的，这条门禁就是"搬对了"的证明。
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests._support import import_sub  # noqa: E402

scene_guard = import_sub("scene_guard")
signal_detectors = import_sub("signal_detectors")

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "detector_eval.json"


class _Ev:
    """scene_guard 只读 text/message_str，给个最小对象就行。"""

    def __init__(self, text: str) -> None:
        self.text = text


def _metrics(rows):
    buckets = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "n": 0})
    for row in rows:
        expected = {str(x) for x in row["expected_signals"]}
        actual = set(signal_detectors.detect_cliches(str(row["answer"])))
        bucket = buckets[str(row["category"])]
        bucket["n"] += 1
        bucket["tp"] += len(expected & actual)
        bucket["fp"] += len(actual - expected)
        bucket["fn"] += len(expected - actual)
    return buckets


def _bypass_errors(rows):
    fp = fn = 0
    for row in rows:
        want = bool(row["formal_bypass"])
        got = scene_guard.is_formal_writing_request(_Ev(str(row["user"])))
        if got and not want:
            fp += 1
        elif want and not got:
            fn += 1
    return fp, fn


def test_fixture_shape():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(rows) >= 261, f"评测集被改小了：{len(rows)}"
    splits = {row["split"] for row in rows}
    assert splits == {"dev", "holdout"}, splits


def test_zero_false_positive_and_negative():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    problems = []
    for split in ("dev", "holdout"):
        part = [row for row in rows if row["split"] == split]
        buckets = _metrics(part)
        for category, bucket in sorted(buckets.items()):
            if bucket["fp"] or bucket["fn"]:
                problems.append(f"{split}/{category}: fp={bucket['fp']} fn={bucket['fn']}")
        fp, fn = _bypass_errors(part)
        if fp or fn:
            problems.append(f"{split}/formal_bypass: fp={fp} fn={fn}")
    assert not problems, "；".join(problems)


def test_all_builtin_signals_covered():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected = {str(item) for row in rows for item in row["expected_signals"]}
    uncovered = sorted(n for n in signal_detectors.builtin_signal_names() if n not in expected)
    assert not uncovered, f"评测集没覆盖到这些信号：{uncovered}"


def test_code_and_url_not_detected():
    # 代码块与 URL 不参与检测（上游硬性约定）
    text = "可以这样写：\n```python\nprint('好问题')\n```\n参考 https://example.com/?q=好问题"
    assert signal_detectors.detect_cliches(text) == [], signal_detectors.detect_cliches(text)
