"""固定规则 / 动态提醒的拼装（宿主无关）。

和上游的差别：上游改写的是 astrbot 的 `ProviderRequest`（system_prompt + contexts + extra parts）；
肥鱼机器人是**自己拼 prompt 直连 DeepSeek** 的，所以这里只做字符串：
给你一段 system prompt，返回「加好规则」的那段。

三个 marker 的设计（marker 是幂等的前提，重复调用不会叠两份）：

    [Human Chat Quality Rules v20|feiyu]   ← 规则块开头，|后面是人格
    ……规则正文……
    [Human Chat Quality end]               ← 规则块结束（没有它就不知道块到哪，会吃掉后面的内容）

    [Human Chat Quality Runtime]           ← 动态提醒（每轮不同，绝不能进 system prompt 的稳定前缀）
    ……
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .constants import MAX_AVOID_ITEM_LEN, MAX_AVOID_ITEMS
from .persona_profiles import persona_profile
from .rules_text import LITE_CORE, PLUGIN_EXTRAS

# 规则版本：跟随上游（升级 natural-talk 时 +1）
RULES_VERSION = 20
INJECTED_MARKER_PREFIX = "[Human Chat Quality"
STABLE_END_MARKER = f"{INJECTED_MARKER_PREFIX} end]"
RUNTIME_HINT_MARKER = f"{INJECTED_MARKER_PREFIX} Runtime]"

_RUNTIME_INSTRUCTION = "本轮避开这些重复项，换种自然说法，别提本提示："
_RUNTIME_PREFIX = f"{RUNTIME_HINT_MARKER}\n{_RUNTIME_INSTRUCTION}\n"
_RUNTIME_ITEM_SEPARATOR = "、"

# 任何版本、任何人格的规则块：从 marker 行到 end 行整段拔掉（非贪婪到第一个 end）
_RULES_BLOCK_RE = re.compile(
    r"^[ \t]*\[Human Chat Quality Rules v\d+[^\]]*\][ \t]*\r?\n[\s\S]*?^[ \t]*"
    + re.escape(STABLE_END_MARKER)
    + r"[ \t]*\r?\n?",
    re.MULTILINE,
)
# 只剩 marker、没有 end 的残块：保守起见只删 marker 那一行
_RULES_STRAY_RE = re.compile(r"^[ \t]*\[Human Chat Quality Rules v\d+[^\]]*\][ \t]*\r?\n", re.MULTILINE)
# 历史里残留的动态提醒（整段，直到下一个 marker 或文末）
_RUNTIME_BLOCK_RE = re.compile(
    r"^[ \t]*" + re.escape(RUNTIME_HINT_MARKER) + r"[ \t]*\r?\n(?:.*(?:\r?\n|$))*?(?=^[ \t]*\[Human Chat Quality|\Z)",
    re.MULTILINE,
)


def stable_marker(persona_id: str = "") -> str:
    """规则块开头那一行（带人格，切人格时能认出旧块是别人的）。"""
    pid = str(persona_id or "").strip().lower()
    suffix = ("|" + pid) if pid else ""
    return f"{INJECTED_MARKER_PREFIX} Rules v{RULES_VERSION}{suffix}]"


def build_stable_rules(persona_id: str = "") -> str:
    """固定规则正文：上游那套 natural-talk 轻量版 + 插件附加 + 人格附加（带首尾 marker）。"""
    profile = persona_profile(persona_id)
    parts = [
        stable_marker(profile.id),
        "遵循 natural-talk 原则（natural-talk MIT）：",
        LITE_CORE.rstrip(),
        PLUGIN_EXTRAS.rstrip(),
    ]
    if profile.rules.strip():
        parts.append(profile.rules.rstrip())
    parts.append(STABLE_END_MARKER)
    return "\n\n".join(parts)


def strip_rules(text: str) -> str:
    """把（任何人格、任何版本的）规则块从文本里拔掉。"""
    text = _RULES_BLOCK_RE.sub("", text or "")
    text = _RULES_STRAY_RE.sub("", text)
    return text.rstrip()


def apply_stable_rules(system_prompt: str, persona_id: str = "", *, enabled: bool = True) -> str:
    """把规则块贴到 system prompt 末尾（幂等：先拔旧的，再贴当前人格的）。"""
    base = strip_rules(system_prompt)
    if not enabled:
        return base
    return f"{base}\n\n{build_stable_rules(persona_id)}" if base else build_stable_rules(persona_id)


_SIGNAL_HINT_MAP: dict[str, str] = {
    "翻案腔": "别用“不是A而是B”式对比，直接说肯定面",
    "结尾拔高": "别在结尾升大命题，写完最后一件事实就停",
    "空转提示语": "删掉“核心是：”这类空转提示语，内容自然承接",
    "揭示式破折号": "别用破折号制造揭晓，改成完整句",
    "模糊叠加": "可能或许等推测词堆叠",
    "编号小标题连发": "机械编号列表",
    "然而连发": "连用然而",
    "路标词堆砌": "堆砌路标词",
    "破折号": "别用破折号（——），改用常规标点",
    "感叹号": "别堆感叹号",
}

# 块所有权校验的单项上限：按渲染后的实际产出推导（渲染会把信号名换成模型端指令）
_RUNTIME_ITEM_MAX_LEN = max(MAX_AVOID_ITEM_LEN, *(len(v) for v in _SIGNAL_HINT_MAP.values()))
_RUNTIME_ITEM_FORBIDDEN = (_RUNTIME_ITEM_SEPARATOR, "\r", "\n")


def select_runtime_hint_names(openers: Sequence[str], max_chars: int) -> list[str]:
    """挑出这轮要塞进提示的项（先按危害排序过，再按字数装，只装完整项）。"""
    openers = [
        item
        for item in openers
        if item and len(item) <= MAX_AVOID_ITEM_LEN and not any(c in item for c in _RUNTIME_ITEM_FORBIDDEN)
    ][:MAX_AVOID_ITEMS]
    if not openers:
        return []
    prefix_len = len(_RUNTIME_PREFIX)
    sep_len = len(_RUNTIME_ITEM_SEPARATOR)
    selected: list[str] = []
    current_len = prefix_len
    for raw_item in openers:
        item = _SIGNAL_HINT_MAP.get(raw_item, raw_item)
        increment = (sep_len if selected else 0) + len(item)
        if current_len + increment > max_chars:
            break
        selected.append(raw_item)
        current_len += increment
    return selected


def render_runtime_hint(names: Sequence[str], extra: str = "") -> str:
    """渲染成一段可注入的文本；`extra` 是人格附加的一句（放在末尾）。"""
    if not names:
        return ""
    rendered = [_SIGNAL_HINT_MAP.get(item, item) for item in names]
    text = _RUNTIME_PREFIX + _RUNTIME_ITEM_SEPARATOR.join(rendered)
    if extra:
        text = f"{text}\n{extra}"
    return text


def build_runtime_hint(openers: Sequence[str], max_chars: int, extra: str = "") -> str:
    return render_runtime_hint(select_runtime_hint_names(openers, max_chars), extra)


def strip_runtime_hint(text: str) -> str:
    return _RUNTIME_BLOCK_RE.sub("", text or "").rstrip()
