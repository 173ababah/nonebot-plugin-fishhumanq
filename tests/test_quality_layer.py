"""质量层行为：规则注入 / 幂等 / 动态提醒 / 记回复 / 会话开关 / 落盘。"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests._support import import_sub  # noqa: E402

core_mod = import_sub("core")
quality_rules = import_sub("quality_rules")
runtime_state = import_sub("runtime_state")

AppConfig = core_mod.AppConfig
HumanQualityCore = core_mod.HumanQualityCore
RuntimeStateStore = runtime_state.RuntimeStateStore


def make_core(tmpdir: str, **over) -> HumanQualityCore:
    base = dict(enabled=True, inject_rules=True, inject_hint=True, persona_adapt=True,
                debug_log=False, custom_cliches=(), disabled_sessions=frozenset(),
                state_file=str(Path(tmpdir) / "state.json"))
    base.update(over)
    cfg = AppConfig(**base)
    store = RuntimeStateStore(base["state_file"], retention_days=14, recent_reply_window=8,
                              custom_cliches=cfg.custom_cliches)
    return HumanQualityCore(cfg, store)


def test_rules_injected_and_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp)
        p1 = core.decorate_system_prompt("你是肥鱼。", "group:1", "feiyu")
        assert "natural-talk" in p1 and "Human Chat Quality end" in p1
        p2 = core.decorate_system_prompt(p1, "group:1", "feiyu")
        assert p2 == p1, "重复贴不能叠两份"


def test_rules_swapped_when_persona_changes():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp)
        p = core.decorate_system_prompt("人设正文", "group:1", "feiyu")
        p2 = core.decorate_system_prompt(p, "group:1", "taffy")
        assert p2.count("[Human Chat Quality Rules v20") == 1, p2[:200]
        assert "|taffy]" in p2 and "|feiyu]" not in p2
        assert p2.startswith("人设正文")


def test_rules_removed_when_disabled_globally():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp, inject_rules=False)
        p = core.decorate_system_prompt("人设正文", "group:1", "feiyu")
        assert "Human Chat Quality" not in p


def test_disabled_session_gets_no_rules():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp)
        asyncio.run(core.set_enabled("group:9", False))
        assert "Human Chat Quality" not in core.decorate_system_prompt("人设", "group:9", "feiyu")
        assert core.runtime_hint("group:9", "feiyu", "在吗") == ""


def test_repeat_opener_becomes_hint():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp)
        for _ in range(3):
            asyncio.run(core.record_reply("group:1", "确实，这个我也这么想。", "feiyu"))
        hint = core.runtime_hint("group:1", "feiyu", "在吗")
        assert hint.startswith("[Human Chat Quality Runtime]"), hint
        assert "确实" in hint, hint


def test_cliche_signal_becomes_hint():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp)
        asyncio.run(core.record_reply("group:1", "希望能帮到你，有问题随时联系我。", "feiyu"))
        hint = core.runtime_hint("group:1", "feiyu", "嗯")
        assert "Human Chat Quality Runtime" in hint
        assert any(k in hint for k in ("希望", "联系", "客套", "随时")), hint


def test_formal_request_yields_hint():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp)
        for _ in range(3):
            asyncio.run(core.record_reply("group:1", "确实，我也这么想。", "feiyu"))
        hint = core.runtime_hint("group:1", "feiyu", "帮我写一份会议纪要")
        assert "正式" in hint, hint
        # 让位时不去动固定规则
        assert "natural-talk" in core.decorate_system_prompt("人设", "group:1", "feiyu")


def test_sticky_followup_keeps_yielding():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp)
        core.runtime_hint("group:1", "feiyu", "帮我写一段营销文案")
        assert "正式" in core.runtime_hint("group:1", "feiyu", "继续")


def test_reset_clears_hint():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp)
        for _ in range(3):
            asyncio.run(core.record_reply("group:1", "确实，这个我也这么想。", "feiyu"))
        assert core.runtime_hint("group:1", "feiyu", "在吗")
        asyncio.run(core.reset("group:1"))
        assert core.runtime_hint("group:1", "feiyu", "在吗") == ""


def test_state_persisted_and_reloaded():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp)
        for _ in range(3):
            asyncio.run(core.record_reply("group:7", "确实，这个我也这么想。", "feiyu"))
        asyncio.run(core.store.flush())
        core2 = make_core(tmp)
        assert core2.store.get("group:7").recent_openers, "状态没从文件读回来"


def test_status_text_mentions_persona():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp)
        text = core.status_text("group:1", "dsh")
        assert "黑鱼" in text, text
        assert "规则 v20" in text


def test_stats_counts_injection():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp)
        core.decorate_system_prompt("人设", "group:1", "feiyu")
        assert core.stats.total_injections >= 1
        assert "累计注入" in core.stats_text()


def test_hint_char_budget():
    with tempfile.TemporaryDirectory() as tmp:
        core = make_core(tmp, max_hint_chars=80)
        for word in ("确实", "当然", "对的", "没错", "哈哈"):
            for _ in range(3):
                asyncio.run(core.record_reply("group:1", f"{word}，这个我也这么想。", "feiyu"))
        hint = core.runtime_hint("group:1", "feiyu", "在吗")
        assert len(hint) <= 80 + 40, len(hint)   # 只装完整项，允许多一个人格尾句
