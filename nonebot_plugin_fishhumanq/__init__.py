"""nonebot-plugin-fishhumanq —— 回复去 AI 腔质量层（从 astrbot 版转写，适配肥鱼机器人三个人格）。

上游：https://github.com/chengzhi-c/astrbot_plugin_human_chat_quality （MIT）
本版做两件事：
  ① 把上游的检测器/状态机原样搬过来（261 例冻结评测集仍然是 0 误报 0 漏报的门禁）
  ② 换宿主胶水：上游改写 astrbot 的 ProviderRequest，这里改成「给一段 prompt，返回加好规则的 prompt」
     —— 因为肥鱼人设.py 是自己拼 prompt 直连大模型的，没有请求对象可以拦。

命令（都在当前会话生效，只有超管能用）：

    /humanq status    看状态（含当前人格、下一轮避用项）
    /humanq on|off    开关当前会话
    /humanq reset     清空当前会话攒的信号
    /humanq rules     看这个会话人格的固定规则原文
    /humanq stats     看本次运行的统计

宿主（肥鱼人设.py）调的是 runtime.py 里那四个函数；插件没加载时它们全是空操作。
"""

from __future__ import annotations

import os

from nonebot import get_driver, get_plugin_config, logger, on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.plugin import PluginMetadata

from .config import Config
from .core import AppConfig, HumanQualityCore
from .persona_profiles import known_personas
from .runtime import (
    configure,
    core as get_core,
    set_enabled,
    reset_session,
    set_persona_resolver,
    stats_text,
    status_text,
    stable_rules,
)
from .runtime_state import RuntimeStateStore

__plugin_meta__ = PluginMetadata(
    name="鱼式去 AI 腔",
    description="回复去 AI 腔质量层：固定规则进 system prompt，重复开头与套话进下一轮提醒（按人格适配）",
    usage="/humanq status | on | off | reset | rules | stats",
    type="application",
    config=Config,
    supported_adapters={"~onebot.v11"},
)

VERSION = "0.1.0"


def _default_state_file() -> str:
    """状态文件默认放 `<bot>/data/fishhumanq_state.json`（和肥鱼机器人别的状态放一起）。"""
    bot_dir = os.environ.get("FISH_BOT_DIR") or os.getcwd()
    return os.path.join(bot_dir, "data", "fishhumanq_state.json")


def _build_config() -> AppConfig:
    try:
        cfg = get_plugin_config(Config)
        dump = cfg.model_dump()
    except Exception as e:  # 配置读不到也别把插件弄崩
        logger.warning(f"[fishhumanq] 读配置失败，用默认值：{e!r}")
        dump = {}
    return AppConfig.from_mapping(
        lambda key, default=None: dump.get("fishhumanq_" + key, default)
    )


def _bootstrap() -> HumanQualityCore:
    cfg = _build_config()
    state_file = cfg.state_file or _default_state_file()
    store = RuntimeStateStore(
        state_file,
        retention_days=cfg.retention_days,
        recent_reply_window=cfg.recent_window,
        custom_cliches=cfg.custom_cliches,
    )
    core = HumanQualityCore(cfg, store)
    configure(core)
    logger.info(
        "[fishhumanq] 已加载 v%s：人格=%s，状态文件=%s，自定义避用词=%d，静态禁用=%d"
        % (
            VERSION,
            ",".join(p.label for p in known_personas()) if cfg.persona_adapt else "通用",
            state_file,
            len(store.custom_cliches),
            len(cfg.disabled_sessions),
        )
    )
    return core


_core = _bootstrap()

humanq = on_command("humanq", aliases={"去腔", "人味"}, priority=5, block=True)


def _is_admin(event: MessageEvent) -> bool:
    """超管才能用（和肥鱼人设.py 一个口径：driver.config.superusers）。"""
    try:
        supers = {str(s) for s in get_driver().config.superusers}
    except Exception:
        return False
    return str(getattr(event, "user_id", "")) in supers


def _chat_key(event: MessageEvent) -> str:
    gid = getattr(event, "group_id", None)
    return f"group:{gid}" if gid else f"private:{getattr(event, 'user_id', '')}"


def _arg(event: MessageEvent) -> str:
    import re

    return re.sub(r"^\s*/?\s*(humanq|去腔|人味)\s*", "", event.get_plaintext() or "").strip().lower()


@humanq.handle()
async def _humanq(bot, event: MessageEvent):
    if not _is_admin(event):
        await humanq.finish("这个只有主人能用。")
    sub = _arg(event)
    key = _chat_key(event)

    if sub in ("", "status", "状态"):
        await humanq.finish(status_text(key))
    if sub in ("on", "开", "开启"):
        ok = await set_enabled(key, True)
        await humanq.finish("去 AI 腔质量层：这个会话开了。" if ok else "开了，但状态文件没写进去，重启可能丢。")
    if sub in ("off", "关", "关闭"):
        ok = await set_enabled(key, False)
        await humanq.finish("去 AI 腔质量层：这个会话关了。" if ok else "关了，但状态文件没写进去。")
    if sub in ("reset", "重置", "清空"):
        ok = await reset_session(key)
        await humanq.finish("这个会话攒的重复开头/套话已经清掉了。" if ok else "清了，但状态文件没写进去。")
    if sub in ("rules", "规则"):
        cfg = get_core()
        pid = ""
        if cfg is not None:
            from .runtime import persona_of

            pid = persona_of(key)
        await humanq.finish(stable_rules(pid))
    if sub in ("stats", "统计"):
        await humanq.finish(stats_text())
    await humanq.finish("用法：/humanq status | on | off | reset | rules | stats")


__all__ = [
    "configure",
    "set_persona_resolver",
    "status_text",
    "stats_text",
    "stable_rules",
]
