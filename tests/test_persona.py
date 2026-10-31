"""人格适配：三个人格各自一套条款 + 专属套话；不认识的人格走通用兜底。

⚠️ 这三套文案是**人设类**内容（会进 system prompt）。改之前必须先问用户 ——
   见 01-文档/交接-机器人.md §0′.50 开头的规矩。
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests._support import import_sub  # noqa: E402

persona_profiles = import_sub("persona_profiles")
quality_rules = import_sub("quality_rules")
core_mod = import_sub("core")
runtime_state = import_sub("runtime_state")

AppConfig = core_mod.AppConfig
HumanQualityCore = core_mod.HumanQualityCore
RuntimeStateStore = runtime_state.RuntimeStateStore

EXPECT = {
    "feiyu": ("肥鱼", "诶嘿", "语气词"),
    "taffy": ("塔菲", "说真的", "毒舌"),
    "dsh": ("黑鱼", "本质上", "揭幕腔"),
}


def _core(tmp: str, **over) -> HumanQualityCore:
    base = dict(enabled=True, inject_rules=True, inject_hint=True, persona_adapt=True,
                debug_log=False, custom_cliches=(), disabled_sessions=frozenset(),
                state_file=str(Path(tmp) / "state.json"))
    base.update(over)
    cfg = AppConfig(**base)
    store = RuntimeStateStore(base["state_file"], retention_days=14, recent_reply_window=8,
                              custom_cliches=cfg.custom_cliches)
    return HumanQualityCore(cfg, store)


def test_three_profiles_exist():
    ids = [p.id for p in persona_profiles.known_personas()]
    assert ids == ["feiyu", "taffy", "dsh"], ids


def test_each_persona_has_its_own_rules():
    for pid, (label, _cliche, keyword) in EXPECT.items():
        profile = persona_profiles.persona_profile(pid)
        assert profile.label == label, (pid, profile.label)
        rules = quality_rules.build_stable_rules(pid)
        assert f"|{pid}]" in rules, pid
        assert label in rules, pid
        assert keyword in rules, (pid, keyword)
        assert "natural-talk" in rules, "通用规则不能丢"


def test_personas_do_not_leak_into_each_other():
    feiyu = quality_rules.build_stable_rules("feiyu")
    taffy = quality_rules.build_stable_rules("taffy")
    dsh = quality_rules.build_stable_rules("dsh")
    assert "讲道理" not in feiyu and "讲道理" in taffy
    assert "本质上" not in feiyu and "本质上" in dsh
    assert "诶嘿" not in dsh


def test_unknown_persona_falls_back_to_generic():
    rules = quality_rules.build_stable_rules("someone_new")
    assert "natural-talk" in rules
    assert "人格附加" not in rules, rules[-200:]


def test_persona_cliches_are_detected():
    with tempfile.TemporaryDirectory() as tmp:
        core = _core(tmp)
        for pid, (_label, cliche, _kw) in EXPECT.items():
            hits = core.cliches_for(pid)
            assert cliche in hits, (pid, cliche, hits)
        # 全局自定义词也要在
        core2 = _core(tmp, custom_cliches=("绝绝子",))
        assert "绝绝子" in core2.cliches_for("feiyu")


def test_persona_hint_tail_appears():
    with tempfile.TemporaryDirectory() as tmp:
        core = _core(tmp)
        for _ in range(3):
            asyncio.run(core.record_reply("group:1", "确实，这个我也这么想。", "taffy"))
        hint = core.runtime_hint("group:1", "taffy", "在吗")
        assert "锐评要具体" in hint, hint


def test_persona_adapt_can_be_turned_off():
    with tempfile.TemporaryDirectory() as tmp:
        core = _core(tmp, persona_adapt=False)
        rules = core.decorate_system_prompt("人设", "group:1", "taffy")
        assert "人格附加" not in rules
        assert "natural-talk" in rules
        assert "说真的" not in core.cliches_for("taffy")
