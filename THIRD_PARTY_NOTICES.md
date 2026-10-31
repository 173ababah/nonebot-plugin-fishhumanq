# 第三方来源

本仓库是以下项目的 **nonebot2 转写版**，检测器、状态机与冻结评测集原样沿用：

- **astrbot_plugin_human_chat_quality** — https://github.com/chengzhi-c/astrbot_plugin_human_chat_quality
  - 作者：chengzhi-c
  - 许可：MIT（见 `LICENSE`）
  - 沿用的部分：`signal_detectors.py`、`scene_guard.py`、`runtime_state.py`、`constants.py`、
    固定规则正文（`rules_text.py`，v20）、`tests/fixtures/detector_eval.json`（261 例冻结评测集）

- **natural-talk** — 规则规范源，作者 natural-talk，许可 MIT。
  本仓库只通过上面的 AstrBot 插件间接引用其「日常对话与问答核心准绳」文本。

## 本仓库改了什么

- 宿主胶水全部重写：从 AstrBot 的 `ProviderRequest` 钩子改为「传 prompt 进、传 prompt 出」的纯函数
  （`quality_rules.py`、`core.py`、`runtime.py`、`__init__.py`）
- 新增人格适配层（`persona_profiles.py`）：三个人格各一套规则叠加、专属套话与提醒尾句
- 新增测试（`tests/`）：261 例门禁 + 质量层行为 + 人格适配
- 新增 `scripts/eval_detector.py`（上游同名脚本的适配版）

原项目版权与许可声明保留，本仓库同样以 MIT 发布。
