# Video Knowledge Conflict 实验框架

## 目标

实验用于测量视频问答模型在“画面事实与经典作品知识冲突”时是否会忽略视频证据、退回作品中的经典答案。每个 case 包含 1–5 个 conflict 视频和 1 个匹配的正常 control 视频，并为每个独立语义目标生成一个 `implicit_prior` 问题。问题必须明确包含对应童话、小说或影视作品名，例如 `In the fairy tale Cinderella, ...?`，但不使用 normally、usually、should 等显式 prior 提示词。

Luna Pro 负责 case authoring、问题生成与答案判定；Seedance 负责生成视频；Gemini、Qwen 或 Kimi 负责视频 QA。

## 数据结构

正式 case 默认位于 `dataset/cases/<case_id>.json`；使用 `--group` 时位于
`dataset/cases/<group>/<case_id>.json`。只支持 schema `4.0`。核心结构如下：

```json
{
  "schema_version": "4.0",
  "case_id": "alice_eat_cake_makes_her_shrink",
  "title": "Alice in Wonderland: The Cake Makes Alice Shrink",
  "conflict_spec": {
    "normal_fact_en": "The cake makes Alice grow.",
    "intended_video_fact_en": "The cake makes Alice shrink."
  },
  "questions": [
    {
      "question_id": "q001_implicit",
      "question_pair_id": "q001",
      "question_type": "implicit_prior",
      "text_en": "In Alice in Wonderland, what happens to Alice after she eats the cake?",
      "conflict_video_reference_en": "She shrinks.",
      "normal_control_reference_en": "She grows."
    }
  ],
  "videos": [
    {
      "video_id": "v001",
      "role": "conflict",
      "seedance_prompt_en": "...",
      "task_id": null,
      "status": "pending",
      "local_path": "videos/seedance/alice_eat_cake_makes_her_shrink/v001.mp4",
      "human_review": "pending",
      "qa_results": []
    }
  ]
}
```

每个问题对共享 mutually exclusive 的 conflict/control reference。视频状态、任务 ID、QA 原始回答、usage 与 judgment 都直接写回 case JSON，写入采用临时文件替换，避免半写状态。

## 模型配置

- Author / Questions / Judge：`openai/gpt-5.6-luna-pro`，通过 OpenRouter。
- Gemini QA：`google/gemini-3.1-pro-preview`，`temperature=0`；默认 reasoning effort 为 `medium`，可用 `low/medium/high/all`。
- Qwen QA：`qwen3.8-max`，通过 DashScope Python SDK 直接上传本地视频，`temperature=0`；`none` 发送 `enable_thinking=false`，`default` 发送 `enable_thinking=true`，固定以 `fps=2` 取帧，不传 completion token 上限。
- Kimi QA：`kimi-k3`，始终开启 thinking。请求不传 `reasoning_effort`、`temperature` 或 completion token 上限；服务默认 reasoning effort 为 `max`，有效温度为 `1.0`。结果记录 `thinking_effort: "default"` 和 `effective_reasoning_effort: "max"`。

Gemini 与 Kimi 把本地视频编码为 Base64 Data URL。Qwen 使用中国大陆 DashScope endpoint `https://dashscope.aliyuncs.com/api/v1`，把本地绝对路径转换为 `file:///...` URI 交给 SDK 上传；本地视频最大 100 MiB，更大的文件需要改用公开 URL 或 OSS。Kimi 在发送前检查完整 JSON 请求体不超过 100 MB。

Qwen QA 运行环境需要 `dashscope>=1.24.6` 和 `DASHSCOPE_API_KEY`。可用 `DASHSCOPE_BASE_HTTP_API_URL` 覆盖原生 endpoint；历史 `QWEN_BASE_URL` 仍兼容，且其 `/compatible-mode/v1` 后缀会自动转换为 `/api/v1`。

## 判断与指标

Judge 只读取问题、QA 原始回答、视频角色、冲突事实和两类 reference：

- conflict 视频回答 conflict reference：`video_grounded`
- conflict 视频回答 normal reference：`knowledge_trapped`
- control 视频回答 normal reference：`video_grounded`
- 缺失、混合、无关或无法可靠归类：`ambiguous_or_unjudgeable`

报告分别统计 answer-level 和 video-level 指标。新生成的问题均为 `implicit_prior`；读取旧 case 时仍兼容历史 `explicit_prior` 问题。video-level verdict 聚合一个视频的多个问题结果；grounded 与 trapped 同时出现时归为 ambiguous。

## 执行流程

统一入口为 `scripts/pipeline.py`：

```bash
python scripts/pipeline.py split-source --source-md SOURCE.md
python scripts/pipeline.py author
python scripts/pipeline.py questions
python scripts/pipeline.py generate
python scripts/pipeline.py qa --qa-model google/gemini-3.1-pro-preview
python scripts/pipeline.py judge
python scripts/pipeline.py summary
python scripts/pipeline.py report
```

完整流程入口只执行 `author → questions → generate → qa → judge`，不自动执行人工 review、summary 或 report：

```bash
python scripts/pipeline.py all --qa-model kimi-k3
```

可以用单层 `--group` 只运行一个 source case 子目录：

```bash
python scripts/pipeline.py all \
  --group classic_fairy_tale_film_conflicts \
  --qa-model kimi-k3
```

该参数将 source、case、视频和默认报告目录分别映射到：

```text
dataset/source_cases/<group>/
dataset/cases/<group>/
videos/seedance/<group>/<case_id>/
results/<group>/
```

不传 `--group` 时继续使用原有平铺目录；已有数据不会自动迁移。

并行分成 case 层与 case 内视频层。所有 QA 请求共享全局并发 limiter、RPM pacing 和 retry 策略。QA 用视频 hash、问题、模型与 thinking effort 去重；`--force` 才追加新一轮结果。

## 运行时代码

```text
scripts/
├── pipeline.py
├── seed21_pro_video_qa.py
└── vconflict_pipeline/
    ├── cli.py
    ├── settings.py
    ├── core.py
    ├── transport.py
    ├── authoring.py
    ├── generation.py
    ├── qa.py
    └── reporting.py
```

`seed21_pro_video_qa.py` 是保留的独立 Seed 2.1 Pro Files API / Responses API 调用，不属于主 pipeline 的三种 QA backend。
