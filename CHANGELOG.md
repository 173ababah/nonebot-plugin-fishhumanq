# 0.1.0（2026-11-01）

从 [astrbot_plugin_human_chat_quality](https://github.com/chengzhi-c/astrbot_plugin_human_chat_quality) 转写。

## 转写

- 宿主胶水改为「传 prompt 进 / 传 prompt 出」：`decorate_system_prompt()` + `runtime_hint()`，
  不再需要 `on_llm_request` 钩子（宿主可能根本不用 astrbot 那套请求对象）
- 规则块带首尾 marker（`[Human Chat Quality Rules v20|人格]` … `[Human Chat Quality end]`），
  贴之前先拔旧的，所以幂等、切人格也能换
- 动态提醒改插在**用户消息之前**（不进 system prompt 的稳定前缀 → 网关前缀缓存不失效）
- 让位（正式写作 / 小说创作）只让位动态提醒；固定规则保持不动（否则整段前缀缓存作废）
- 保留上游的 261 例冻结评测集门禁（0 误报 / 0 漏报）

## 人格适配（新增）

- `persona_profiles.py`：肥鱼 / 塔菲 / 黑鱼三个人格各一套
  - 规则叠加（进 system prompt）
  - 专属套话（进检测器的自定义避用词）
  - 提醒尾句（进动态提醒）
- 不认识的人格走通用兜底；`FISHHUMANQ_PERSONA_ADAPT=false` 可整体关掉
- 宿主可用 `set_persona_resolver()` 告诉插件每个会话用哪个人格

## 命令

- `/humanq status | on | off | reset | rules | stats`（超管，当前会话生效；别名 `/去腔` `/人味`）

## 测试

- 24 项，`python tests/run_tests.py`，不需要 nonebot / astrbot
