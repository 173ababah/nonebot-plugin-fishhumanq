#!/usr/bin/env python3
"""冻结评测集门禁（上游 scripts/eval_detector.py 的 nonebot 版）。

    python scripts/eval_detector.py            # 打报告
    python scripts/eval_detector.py --check    # 有任何错就 exit 1
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests._support import import_sub  # noqa: E402

scene_guard = import_sub("scene_guard")
signal_detectors = import_sub("signal_detectors")

FIXTURE = ROOT / "tests" / "fixtures" / "detector_eval.json"


class _Ev:
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
    categories = {}
    for name, b in sorted(buckets.items()):
        tp, fp, fn = b["tp"], b["fp"], b["fn"]
        categories[name] = {
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "fp": fp,
            "fn": fn,
            "n": b["n"],
        }
    fp = fn = 0
    for row in rows:
        want = bool(row["formal_bypass"])
        got = scene_guard.is_formal_writing_request(_Ev(str(row["user"])))
        fp += int(got and not want)
        fn += int(want and not got)
    return {"count": len(rows), "categories": categories,
            "formal_bypass": {"fp": fp, "fn": fn, "n": len(rows)}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="不一致就返回非 0")
    args = ap.parse_args(argv)

    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected_names = {str(x) for row in rows for x in row["expected_signals"]}
    uncovered = sorted(n for n in signal_detectors.builtin_signal_names() if n not in expected_names)
    report = {
        "dev": _metrics([r for r in rows if r["split"] == "dev"]),
        "holdout": _metrics([r for r in rows if r["split"] == "holdout"]),
        "uncovered_signals": uncovered,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))

    bad = bool(uncovered)
    for split in ("dev", "holdout"):
        if report[split]["formal_bypass"]["fp"] or report[split]["formal_bypass"]["fn"]:
            bad = True
        if any(m["fp"] or m["fn"] for m in report[split]["categories"].values()):
            bad = True
    return 1 if (args.check and bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
