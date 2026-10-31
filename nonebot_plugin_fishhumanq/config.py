"""配置：`FISHHUMANQ_` 前缀，跟其它 fish* 插件一致。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Config(BaseModel):
    fishhumanq_enabled: bool = Field(default=True, description="总开关")
    fishhumanq_inject_rules: bool = Field(default=True, description="注入固定规则（system prompt）")
    fishhumanq_inject_hint: bool = Field(default=True, description="注入动态提醒（每轮变化的短提示）")
    fishhumanq_persona_adapt: bool = Field(default=True, description="按人格叠加条款与专属套话")
    fishhumanq_max_hint_chars: int = Field(default=157, description="每轮动态提示最大字符数（80~157）")
    fishhumanq_recent_window: int = Field(default=8, description="重复开头看最近 N 条（3~50）")
    fishhumanq_retention_days: int = Field(default=14, description="会话状态几天没动就清理（1~365）")
    fishhumanq_custom_cliches: str = Field(default="", description="自定义避用词，逗号/换行分隔")
    fishhumanq_disabled_sessions: str = Field(default="", description="静态禁用会话，逗号/换行分隔（群号或 group:123）")
    fishhumanq_state_file: str = Field(default="", description="状态文件路径，默认 <bot>/data/fishhumanq_state.json")
    fishhumanq_debug: bool = Field(default=False, description="调试日志")
