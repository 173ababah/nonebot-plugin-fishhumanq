"""质量层核心：宿主无关的「拼 prompt / 记回复 / 出状态」。

上游 core.py 是围绕 astrbot 的 `ProviderRequest` 写的；肥鱼机器人自己拼 prompt 直连大模型，
所以这里把契约收窄成四个纯函数式入口（见 `__init__.py` 导出的 API）：

    decorate_system_prompt(prompt, session_key, persona_id)  加固定规则（每轮都一样 → 前缀缓存不失效）
    runtime_hint_text(session_key, persona_id, user_text)     出本轮动态提醒（可空）
    record_reply(session_key, persona_id, reply)             记她自己说的话，攒信号
    status_text(session_key, persona_id)                     /humanq status 用

让位（正式写作 / 小说创作）保留上游语义，但作用在**动态提醒**上，固定规则不动 ——
因为固定规则在 system prompt 的稳定前缀里，一改整段前缀缓存就废（肥鱼机器人很在意这个）。
让位时不静默：给一句「这轮按正式/创作要求写」的反向提示，比什么都不说更稳。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .constants import (
    DEFAULT_RECENT_REPLY_WINDOW,
    DEFAULT_STATE_RETENTION_DAYS,
    MAX_RECENT_REPLY_WINDOW,
    MAX_RUNTIME_HINT_CHARS,
    MAX_STATE_RETENTION_DAYS,
    MIN_RECENT_REPLY_WINDOW,
    MIN_RUNTIME_HINT_CHARS,
    MIN_STATE_RETENTION_DAYS,
    PENDING_SESSION_CAP,
    YIELD_STICKY_TTL_SECONDS,
)
from .persona_profiles import persona_profile
from .quality_rules import (
    apply_stable_rules,
    build_stable_rules,
    build_runtime_hint,
    strip_runtime_hint,
)
from .runtime_state import RuntimeStateStore, is_session_disabled
from .scene_guard import is_creative_writing_request, is_formal_writing_request, is_sticky_followup
from .signal_detectors import detect_cliches, signal_priority

logger = logging.getLogger(__name__)


@dataclass
class QualityStats:
    """进程内累计统计（不落盘）。"""

    total_injections: int = 0
    stable_rules_injected: int = 0
    runtime_hints_injected: int = 0
    avoid_items_seen: int = 0
    cliche_hits: dict[str, int] = field(default_factory=dict)

    def record_hits(self, cliches) -> None:
        for item in cliches:
            self.cliche_hits[item] = self.cliche_hits.get(item, 0) + 1

    def record_request(self, stable: bool, hint: bool) -> None:
        if stable:
            self.stable_rules_injected += 1
        if hint:
            self.runtime_hints_injected += 1
        if stable or hint:
            self.total_injections += 1

    def top(self, limit: int = 5) -> list[tuple[str, int]]:
        return sorted(self.cliche_hits.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


def _parse_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _parse_list(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        items = [str(v).strip() for v in value]
        return [v for v in items if v]
    if isinstance(value, str):
        return [p.strip() for p in value.replace("\r", "\n").replace(",", "\n").splitlines() if p.strip()]
    return []


@dataclass(frozen=True)
class AppConfig:
    """一次性快照（构造后不改）。"""

    enabled: bool = True
    inject_rules: bool = True
    inject_hint: bool = True
    persona_adapt: bool = True
    debug_log: bool = False
    max_hint_chars: int = MAX_RUNTIME_HINT_CHARS
    recent_window: int = DEFAULT_RECENT_REPLY_WINDOW
    retention_days: int = DEFAULT_STATE_RETENTION_DAYS
    custom_cliches: tuple[str, ...] = ()
    disabled_sessions: frozenset[str] = frozenset()
    state_file: str = ""

    @classmethod
    def from_mapping(cls, get) -> "AppConfig":
        """`get` 是 `dict.get` 或 pydantic config 的 `getattr` 包装，两种宿主都能用。"""
        return cls(
            enabled=_parse_bool(get("enabled", True), True),
            inject_rules=_parse_bool(get("inject_rules", True), True),
            inject_hint=_parse_bool(get("inject_hint", True), True),
            persona_adapt=_parse_bool(get("persona_adapt", True), True),
            debug_log=_parse_bool(get("debug_log", False), False),
            max_hint_chars=_parse_int(
                get("max_hint_chars", MAX_RUNTIME_HINT_CHARS),
                MAX_RUNTIME_HINT_CHARS,
                MIN_RUNTIME_HINT_CHARS,
                MAX_RUNTIME_HINT_CHARS,
            ),
            recent_window=_parse_int(
                get("recent_window", DEFAULT_RECENT_REPLY_WINDOW),
                DEFAULT_RECENT_REPLY_WINDOW,
                MIN_RECENT_REPLY_WINDOW,
                MAX_RECENT_REPLY_WINDOW,
            ),
            retention_days=_parse_int(
                get("retention_days", DEFAULT_STATE_RETENTION_DAYS),
                DEFAULT_STATE_RETENTION_DAYS,
                MIN_STATE_RETENTION_DAYS,
                MAX_STATE_RETENTION_DAYS,
            ),
            custom_cliches=tuple(_parse_list(get("custom_cliches", ""))),
            disabled_sessions=frozenset(v.lower() for v in _parse_list(get("disabled_sessions", ""))),
            state_file=str(get("state_file", "") or ""),
        )


_YIELD_HINTS = {
    "formal": "这轮是正式文稿任务：按任务要求的体裁写，对话层的句式约束先让位。",
    "creative": "这轮是小说/角色扮演创作：按设定和情节写，对话层的句式约束先让位。",
}
_YIELD_LABELS = {
    "formal": "正式写作让位",
    "creative": "创作场景让位",
}


class HumanQualityCore:
    """拼 prompt、记回复、出状态。所有入口都是同步的，只有写盘是 async。"""

    def __init__(self, cfg: AppConfig, store: RuntimeStateStore) -> None:
        self.cfg = cfg
        self.store = store
        self.stats = QualityStats()
        self._pending_yield: dict[str, tuple[float, str]] = {}

    # ---------------------------------------------------------------- 人格
    def profile(self, persona_id: str):
        return persona_profile(persona_id if self.cfg.persona_adapt else "")

    def stable_rules(self, persona_id: str = "") -> str:
        return build_stable_rules(self.profile(persona_id).id)

    def cliches_for(self, persona_id: str = "") -> tuple[str, ...]:
        """检测用的避用词：全局配置 + 这个角色的专属套话（去重保序）。"""
        extra = self.profile(persona_id).cliches
        seen: dict[str, None] = {}
        for item in (*self.store.custom_cliches, *extra):
            seen.setdefault(item, None)
        return tuple(seen)

    # ---------------------------------------------------------------- 开关
    def session_active(self, session_key: str) -> bool:
        session_key = str(session_key or "")
        if not self.cfg.enabled or not session_key:
            return False
        if not self.store.is_enabled(session_key):
            return False
        if is_session_disabled(self.cfg.disabled_sessions, session_key):
            return False
        return True

    # ---------------------------------------------------------------- 固定规则
    def decorate_system_prompt(self, prompt: str, session_key: str, persona_id: str = "") -> str:
        """给 system prompt 贴固定规则；关掉时把旧块拔掉。"""
        if not self.cfg.inject_rules or not self.session_active(session_key):
            return apply_stable_rules(prompt, "", enabled=False)
        self.stats.record_request(True, False)
        return apply_stable_rules(prompt, self.profile(persona_id).id, enabled=True)

    # ---------------------------------------------------------------- 动态提醒
    def _yield_kind(self, session_key: str, user_text: str, *, update: bool = False) -> str | None:
        now = time.monotonic()
        kind = None
        if is_formal_writing_request(_EventText(user_text)):
            kind = "formal"
        elif is_creative_writing_request(_EventText(user_text)):
            kind = "creative"
        if kind:
            if update:
                self._pending_yield[session_key] = (now, kind)
                self._evict_yield()
            return kind
        sticky = self._pending_yield.get(session_key)
        if sticky and now - sticky[0] <= YIELD_STICKY_TTL_SECONDS and is_sticky_followup(user_text or ""):
            if update:
                self._pending_yield[session_key] = (now, sticky[1])
                self._evict_yield()
            return sticky[1]
        if update:
            self._pending_yield.pop(session_key, None)
        return None

    def _evict_yield(self) -> None:
        while len(self._pending_yield) > PENDING_SESSION_CAP:
            self._pending_yield.pop(next(iter(self._pending_yield)))

    def runtime_hint(self, session_key: str, persona_id: str = "", user_text: str = "") -> str:
        """本轮要插在**用户消息之前**的那段短提示；没有信号返回空串。

        为什么不放进 system prompt：system prompt 的前缀里有历史，每轮都变的话网关那边的
        前缀缓存就废了（肥鱼机器人专门为这个把历史排在 prompt 开头）。
        """
        if not self.cfg.inject_hint or not self.session_active(session_key):
            return ""
        kind = self._yield_kind(session_key, user_text, update=True)
        if kind:
            return _YIELD_HINTS[kind]
        state = self.store.get(session_key)
        openers = list(state.avoid_openers)
        if not openers:
            return ""
        ordered = [item for _, item in sorted(enumerate(openers), key=lambda p: (signal_priority(p[1]), p[0]))]
        profile = self.profile(persona_id)
        hint = build_runtime_hint(ordered, self.cfg.max_hint_chars, extra=profile.hint)
        if hint:
            self.stats.record_request(False, True)
            if self.cfg.debug_log:
                logger.info("[fishhumanq] 动态提醒 %s persona=%s: %s", session_key, profile.id or "-", hint.replace("\n", " "))
        return hint

    # ---------------------------------------------------------------- 记回复
    async def record_reply(self, session_key: str, reply: str, persona_id: str = "") -> int:
        """把她这句话喂进状态：命中套话 + 高频重复开头 → 下一轮的提醒。"""
        session_key = str(session_key or "")
        text = strip_runtime_hint(reply or "")
        if not session_key or not text.strip():
            return 0
        if not self.session_active(session_key):
            return 0
        if self._yield_kind(session_key, "", update=False):
            return 0
        cliches = detect_cliches(text, self.cliches_for(persona_id))
        self.stats.record_hits(cliches)
        ordered = tuple(sorted(cliches, key=signal_priority))
        new_items = await self.store.record_response(session_key, text, ordered)
        self.stats.avoid_items_seen += new_items
        if self.cfg.debug_log:
            logger.info("[fishhumanq] 记回复 %s：命中 %s，新增避用项 %d", session_key, list(ordered), new_items)
        return new_items

    # ---------------------------------------------------------------- 会话控制
    async def set_enabled(self, session_key: str, enabled: bool) -> bool:
        return await self.store.set_enabled(str(session_key or ""), enabled)

    async def reset(self, session_key: str) -> bool:
        return await self.store.reset(str(session_key or ""))

    def status_text(self, session_key: str, persona_id: str = "") -> str:
        persistence = "待重试" if self.store.has_pending_save else "正常"
        profile = self.profile(persona_id)
        reasons: list[str] = []
        if not self.cfg.enabled:
            reasons.append("- 全局配置：关闭")
        if not self.store.is_enabled(session_key):
            reasons.append("- 当前会话：已用 /humanq off 关掉")
        if is_session_disabled(self.cfg.disabled_sessions, session_key):
            reasons.append("- 配置静态禁用：命中 disabled_sessions")
        yield_kind = self._yield_kind(session_key, "", update=False)
        if yield_kind:
            reasons.append("- " + _YIELD_LABELS[yield_kind])
        head = "去 AI 腔质量层（fishhumanq）状态："
        if reasons:
            return "\n".join([head, *reasons, "- 状态持久化：" + persistence])
        state = self.store.get(session_key)
        avoid = "、".join(state.avoid_openers) if state.avoid_openers else "无（还没攒够重复信号）"
        return "\n".join(
            [
                head,
                f"- 当前会话：启用（{profile.label}）",
                f"- 固定规则：{'注入' if self.cfg.inject_rules else '关闭'}（system prompt，规则 v20）",
                f"- 动态提醒：{'注入' if self.cfg.inject_hint else '关闭'}（插在用户消息前）",
                f"- 人格条款：{'按人格叠加' if self.cfg.persona_adapt else '只用通用规则'}",
                f"- 下一轮避用：{avoid}",
                f"- 自启动以来累计注入：{self.stats.total_injections} 次",
                f"- 状态持久化：{persistence}",
            ]
        )

    def stats_text(self) -> str:
        s = self.stats
        lines = [
            "去 AI 腔质量层统计（本次运行）：",
            f"- 累计注入：{s.total_injections} 次",
            f"  └ 固定规则：{s.stable_rules_injected} 次",
            f"  └ 动态提醒：{s.runtime_hints_injected} 次",
            f"- 累计避用项记录：{s.avoid_items_seen} 项次",
        ]
        top = s.top(5)
        if top:
            lines.append("- 高频信号 TOP 5：")
            lines.extend(f"  {count:>3} 次 {name}" for name, count in top)
        return "\n".join(lines)


class _EventText:
    """把一段用户文本伪装成事件对象，复用上游 scene_guard 的判据（它只读 text/message_str）。"""

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = str(text or "")

    def get_message_str(self) -> str:
        return self.text
