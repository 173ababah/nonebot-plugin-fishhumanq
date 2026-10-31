"""只用于类型标注的 Protocol（运行时零依赖，不 import nonebot / astrbot）。

上游用它描述 astrbot 的 ProviderRequest/LLMResponse；这个端口只保留了"事件"那一小块 ——
scene_guard / runtime_state 里按属性探测宿主的形状（鸭子类型），标一下类型便于读代码。
"""

from __future__ import annotations

from typing import Protocol


class MessageEventProtocol(Protocol):
    """宿主消息事件：本端口只需要"文本 + 会话标识 + 群号"三样。"""

    unified_msg_origin: str

    def get_group_id(self) -> str | None: ...
