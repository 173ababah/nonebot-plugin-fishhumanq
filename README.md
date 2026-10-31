# nonebot-plugin-fishhumanq

回复**去 AI 腔**质量层 —— 从 astrbot 插件
[`astrbot_plugin_human_chat_quality`](https://github.com/chengzhi-c/astrbot_plugin_human_chat_quality)
转写成 nonebot2 版，并按人格做了适配。

两件事：

1. **固定规则**：一段 `natural-talk` 轻量规则（v20）写进 system prompt，常数不随轮次变 ——
   所以不会破坏网关的前缀缓存。
2. **动态提醒**：记录她最近说过的**开头**和命中的**套话**，下一轮在用户消息前插一小段
   「本轮避开这些，换种说法」，只装完整短语，最多 157 字。

检测器、状态机、冻结评测集（261 例，门禁 0 误报 / 0 漏报）都是从上游原样搬过来的；
换掉的只有**宿主胶水**：上游改写 astrbot 的 `ProviderRequest`，这里改成
「给我一段 prompt，我还你一段加好规则的 prompt」。

## 和上游的差别

| | 上游（astrbot） | 本版（nonebot / 肥鱼机器人） |
|---|---|---|
| 注入方式 | `on_llm_request` 钩子改 `ProviderRequest` | 宿主自己拼 prompt，调用 `decorate_system_prompt()` / `runtime_hint()` |
| 动态提醒位置 | `extra_user_content_parts`（临时 part） | 用户消息**前**的一条短 system 消息（前缀缓存不失效） |
| 让位（正式写作/创作） | 连固定规则一起不注入 | 只让位动态提醒，**固定规则不动**（一改整段前缀缓存就废） |
| 人格 | 一套通用规则 | 三个人格各叠一套条款 + 专属套话（可关） |
| 历史清理 | 每轮清 `contexts` 里的旧块 | 不需要（prompt 每轮重建）；`strip_rules()` 只在贴之前做幂等 |

## 安装

```bash
nb plugin install nonebot-plugin-fishhumanq
# 或者丢进 src/ 一样能加载
```

`.env`：

```ini
FISHHUMANQ_ENABLED=true
FISHHUMANQ_INJECT_RULES=true
FISHHUMANQ_INJECT_HINT=true
FISHHUMANQ_PERSONA_ADAPT=true
FISHHUMANQ_MAX_HINT_CHARS=157
FISHHUMANQ_RECENT_WINDOW=8
FISHHUMANQ_STATE_FILE=/opt/qqbot/data/fishhumanq_state.json
# 自定义避用词 / 静态禁用会话（逗号或换行分隔）
FISHHUMANQ_CUSTOM_CLICHES=
FISHHUMANQ_DISABLED_SESSIONS=
```

## 宿主怎么接（三个函数）

```python
from nonebot_plugin_fishhumanq.runtime import (
    decorate_system_prompt, runtime_hint, record_reply,
)

# ① 拼 system prompt 时贴固定规则（每轮一样 → 缓存友好）
prompt = decorate_system_prompt(prompt, session_key="group:123456", persona_id="taffy")

# ② 每条请求前取动态提醒，非空就插在用户消息前面
hint = runtime_hint("group:123456", "taffy", user_text=text)
if hint:
    messages.append({"role": "system", "content": hint})

# ③ 她说完之后记一笔（攒重复开头 / 套话）
await record_reply("group:123456", reply=answer, persona_id="taffy")
```

可选：让插件知道每个会话用哪个人格

```python
from nonebot_plugin_fishhumanq import set_persona_resolver
set_persona_resolver(persona_for)      # (chat_key) -> "feiyu" / "taffy" / "dsh"
```

插件没装、没启用、或者还没加载完时，这三个函数都是**原样返回 / 空操作**，
宿主不需要写 `if`。

## 命令

只给超管，作用范围都是**当前会话**：

| 命令 | 作用 |
|---|---|
| `/humanq status` | 状态（当前人格、下一轮避用项、累计注入） |
| `/humanq on` / `off` | 开关当前会话 |
| `/humanq reset` | 清空当前会话攒的信号 |
| `/humanq rules` | 看这个会话人格的固定规则原文 |
| `/humanq stats` | 本次运行的统计 |

别名：`/去腔`、`/人味`。

## 人格适配（三个人格）

`persona_profiles.py` 里给三个角色各写一套：**规则叠加**（进 system prompt）、
**专属套话**（进检测器）、**提醒尾句**（进动态提醒）。

| 人格 | 针对的毛病 |
|---|---|
| `feiyu` 肥鱼（软萌傲娇） | 语气词堆砌、心理按摩、把一句话说成三段 |
| `taffy` 塔菲（毒舌嘴臭） | 脏话密度、「说真的/讲道理」当前缀、骂完接客服话 |
| `dsh` 黑鱼（理性孤傲） | 揭幕腔（本质上/真相是）、综上收尾、把话甩回去 |

不认识的人格走**通用兜底**（只有上游那套规则，不报错）。
`FISHHUMANQ_PERSONA_ADAPT=false` 可以整体关掉，退回纯通用规则。

> ⚠️ 这三套文案是**人设类**内容。在肥鱼机器人里改它们要先问用户（见交接文档 §0′.50 开头的规矩）。

## 测试

```bash
python tests/run_tests.py            # 24 项，不需要 nonebot
python -S scripts/run_tests.py core  # 只跑核心（上游那条命令也保留兼容）
python scripts/eval_detector.py --check   # 261 例冻结评测集门禁
```

## 许可

MIT。规则正文与检测器来自
[astrbot_plugin_human_chat_quality](https://github.com/chengzhi-c/astrbot_plugin_human_chat_quality)（MIT），
规则规范源为 natural-talk（MIT）。见 `THIRD_PARTY_NOTICES.md`。
