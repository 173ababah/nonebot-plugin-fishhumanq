"""对宿主暴露的入口（**不依赖 nonebot**，可以单独 import / 单测）。

肥鱼人设.py 里就调这几个函数：

    from nonebot_plugin_fishhumanq.runtime import (
        decorate_system_prompt, runtime_hint, record_reply,
    )

插件没装、没启用、或者还没加载完时，这些函数全都是「原样返回 / 空操作」，
宿主不用写 if（2026-11-01 的约定：可选依赖要能静静地不在）。
"""

from __future__ import annotations

import json
import os
from typing import Any

from .core import HumanQualityCore
from .quality_rules import build_stable_rules

_CORE: HumanQualityCore | None = None
_PERSONA_RESOLVER = None

# 宿主没注册解析器时的兜底：从肥鱼机器人的注册表里猜
DEFAULT_BOT_DIR = os.environ.get("FISH_BOT_DIR") or "/opt/qqbot"
_PERSONA_FILES = ("data/personas.json", "data/persona_bindings.json")


def configure(core: HumanQualityCore | None) -> None:
    """插件加载完时把 core 装进来（测试也可以直接装一个假的）。"""
    global _CORE
    _CORE = core


def set_persona_resolver(fn) -> None:
    """让宿主告诉插件「这个会话现在用哪个人格」（肥鱼人设.py 会注册 persona_for）。"""
    global _PERSONA_RESOLVER
    _PERSONA_RESOLVER = fn


def available() -> bool:
    return _CORE is not None


def core() -> HumanQualityCore | None:
    return _CORE


# ---------------------------------------------------------------- 人格
def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def persona_of(session_key: str, bot_dir: str = "") -> str:
    """这个会话的人：先用宿主注册的解析器，没有就读注册表（绑定 → 当前 → 默认）。"""
    key = str(session_key or "")
    if _PERSONA_RESOLVER is not None:
        try:
            pid = _PERSONA_RESOLVER(key)
            if pid:
                return str(pid)
        except Exception:
            pass
    base = bot_dir or DEFAULT_BOT_DIR
    bindings = _read_json(os.path.join(base, _PERSONA_FILES[1]))
    if isinstance(bindings, dict) and key:
        pid = str(bindings.get(key) or "").strip()
        if pid:
            return pid
    reg = _read_json(os.path.join(base, _PERSONA_FILES[0]))
    if isinstance(reg, dict):
        active = str(reg.get("active") or "").strip()
        if active:
            return active
    return "feiyu"


# ---------------------------------------------------------------- 宿主直接调用的四个
def decorate_system_prompt(prompt: str, session_key: str = "", persona_id: str = "") -> str:
    """把固定规则贴到 system prompt 末尾（幂等；插件不在就原样返回）。"""
    if _CORE is None:
        return prompt
    try:
        return _CORE.decorate_system_prompt(prompt, session_key, persona_id or persona_of(session_key))
    except Exception:
        return prompt


def runtime_hint(session_key: str = "", persona_id: str = "", user_text: str = "") -> str:
    """本轮动态提醒（没信号就是空串；插件不在也返回空串）。"""
    if _CORE is None:
        return ""
    try:
        return _CORE.runtime_hint(session_key, persona_id or persona_of(session_key), user_text)
    except Exception:
        return ""


async def record_reply(session_key: str = "", reply: str = "", persona_id: str = "") -> int:
    """记她自己这句回复（攒重复开头 / 套话信号）。"""
    if _CORE is None:
        return 0
    try:
        return await _CORE.record_reply(session_key, reply, persona_id or persona_of(session_key))
    except Exception:
        return 0


def stable_rules(persona_id: str = "") -> str:
    """固定规则原文（/humanq rules 用）。插件不在也能看。"""
    return build_stable_rules(persona_id)


def status_text(session_key: str = "", persona_id: str = "") -> str:
    if _CORE is None:
        return "去 AI 腔质量层没启用（插件没加载）。"
    return _CORE.status_text(session_key, persona_id or persona_of(session_key))


def stats_text() -> str:
    if _CORE is None:
        return "去 AI 腔质量层没启用（插件没加载）。"
    return _CORE.stats_text()


async def set_enabled(session_key: str, enabled: bool) -> bool:
    if _CORE is None:
        return False
    return await _CORE.set_enabled(session_key, enabled)


async def reset_session(session_key: str) -> bool:
    if _CORE is None:
        return False
    return await _CORE.reset(session_key)
