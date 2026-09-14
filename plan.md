# Video Knowledge Conflict 实验框架

## 目标

实验用于测量视频问答模型在“画面事实与经典知识冲突”时，是否忽略当前输入
证据并退回经典答案。每个 case 包含 1–5 个 conflict 视频和 1 个匹配的正常
control 视频，并为每个独立语义目标生成一个中性问题。

Luna Pro 负责 case authoring、问题生成、文字 context 生成和答案判定；
Seedance 负责生成视频；Gemini、Qwen 或 Kimi 负责视频或文字 context QA。

## 数据结构

正式 case 默认位于 `dataset/cases/<case_id>.json`；使用 `--group` 时位于
`dataset/cases/<group>/<case_id>.json`。只支持 schema `4.0`。

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
      "question_id": "q001",
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
      "description": {
        "context_en": "In Alice in Wonderland, Alice eats the cake and her body shrinks.",
        "context_prefix_en": "In Alice in Wonderland,",
        "source": "seedance_prompt_en",
        "source_sha256": "...",
        "generator_model": "openai/gpt-5.6-luna-pro",
        "generated_at": "...",
        "generator_request_id": "..."
      },
      "qa_results": []
    }
  ]
}
```

case JSON 是运行状态的唯一持久化单元。视频状态、任务 ID、description、QA
完整回答 `raw_answer`、明确末行 `final_answer`、usage 与 judgment 均直接写回，
写入使用临时文件替换。
`description` 是仅用于 conflict 视频的可选扩展。

新 QA 记录不再包含 `context_sha256` 或 `video_sha256`。旧记录中的这些字段
继续兼容读取，但不参与去重或统计。

新生成的问题直接使用连续 ID `q001`–`q003`，不包含
`question_pair_id`、`question_type` 或 implicit/explicit 后缀。删除问题后允许 ID
出现缺口，其他问题不会重编号。旧 case 的问题格式仅为读取现有数据而兼容，不再
生成，也不再进入分组指标。

## 模型配置

- Author / Questions / Judge：`openai/gpt-5.6-luna-pro`，通过 OpenRouter。
- Gemini QA：CLI 名称为 `gemini`，实际模型为
  `google/gemini-3.1-pro-preview`；CLI effort 为 `default`，实际 reasoning
  effort 为 `medium`，`temperature=0`。
- Qwen QA：`qwen3.8-max`，通过 DashScope SDK 上传本地视频；支持 `none` 和
  `default`，固定 `fps=2`，`temperature=0`。
- Kimi QA：`kimi-k3`，CLI effort 为 `default`，实际 reasoning effort 为
  `max`，有效温度为 `1.0`。

Gemini 和 Kimi 把本地视频编码为 Base64 Data URL。Qwen 使用中国大陆
DashScope endpoint，并把本地绝对路径转换为 `file:///...` URI 交给 SDK。
Qwen 本地视频最大 100 MiB；Kimi 请求体最大 100 MB。

## 判断与指标

每个 QA user prompt 最后固定追加：

```text
Conclude with exactly one final line in this format: Final answer: <your clear, direct answer in one sentence>.
```

Pipeline 保留完整 `raw_answer`，但只从最后一个非空行的精确
`Final answer:` 标记提取 `final_answer`。缺少标记或标记后为空时，仅当前
question/effort 失败且不保存记录，不进行格式重试；其他 QA 和 Judge 继续运行。

Judge 只读取问题、`final_answer`、输入角色、冲突事实和两类 reference，绝不读取
或推断 `raw_answer`：

- conflict 输入回答 conflict reference：`context_grounded`
- conflict 输入回答 normal reference：`knowledge_trapped`
- control 输入回答 normal reference：`context_grounded`
- 混合、矛盾、含糊、回避、无关或无法可靠归类：
  `ambiguous_or_unjudgeable`

Judge 不再从多项表述中选择所谓 main answer。结构化输出仅包含 `verdict` 和
`confidence`；持久化 judgment 另保存时间、Judge 模型和请求 ID，不再保存
`extracted_answer` 或 `evidence`。

Description 输入复用相同 verdict，其中 `context_grounded` 表示回答遵循所提供的
文字 context。旧 JSON 的 `video_grounded` 在加载和汇总时映射为
`context_grounded`，原文件不迁移。

报告分别统计 answer-level 和 video-level 指标。同一视频的多个问题同时出现
grounded 与 trapped 时，video-level verdict 为 ambiguous。

## 执行流程

统一入口为 `scripts/pipeline.py`。视频实验显式运行：

```bash
python scripts/pipeline.py author --group <group>
python scripts/pipeline.py questions --group <group>
python scripts/pipeline.py generate --group <group>
python scripts/pipeline.py qa-judge --group <group> \
  --input video --qa-model qwen3.8-max --thinking-effort all
python scripts/pipeline.py summarize --group <group> \
  --input video --qa-model qwen3.8-max --thinking-effort all
```

文字描述实验：

```bash
python scripts/pipeline.py description --group <group>
python scripts/pipeline.py qa-judge --group <group> \
  --input description --qa-model qwen3.8-max --thinking-effort all
python scripts/pipeline.py summarize --group <group> \
  --input description --qa-model qwen3.8-max --thinking-effort all
```

数据清理使用 `delete`。删除视频或问题时一次命令只操作一个 case，可同时指定
多个 `--video-id` 和 `--question-id`；`--all` 可同时删除同一 group 下多个完整
case 的 JSON 和视频目录。单独删除视频仅允许 conflict，并且必须至少保留一个
conflict。删除问题会同时清除其全部 QA/Judge 历史。

不提供 `split-source`、自动串联全部阶段的 `all` 命令，也不提供
video/description 配对 `compare`。Source cases 必须预先按每个 case 一个 Markdown
文件准备，各阶段显式执行。文字 context stage 名称为 `description`。

`qa-judge` 使用 case 层与输入层两级并发，所有请求共享 limiter、RPM pacing 和
retry 策略。QA 在当前 video 对象中按以下键去重：

```text
input + question_id + qa_model + thinking_effort
```

视频输入预检会检查本地 `local_path`。本次选中的视频如果文件存在但 `status`
不是 `ready`，预检会先把状态修正为 `ready` 并写回 case JSON；非 `ready` 且文件
不存在的视频继续跳过。已经标记为 `ready` 但本地文件不存在时仍视为数据错误，
整个 `qa-judge` 在调用模型前失败。

视频文件不会为去重而计算 SHA-256。通过 pipeline 重新生成视频、description
或 questions 时会清除相应 QA；手工替换同路径视频后必须使用 `--force-qa`。

QA 去重键保持不变，不为最终回答协议增加版本。旧记录允许加载和被
`--force-qa` 清除，但不会猜测或迁移 `final_answer`；普通运行或
`--force-judge` 选中旧格式记录时，会在任何模型请求前要求先执行
`--force-qa`。

`--force-qa` 和 `--force-judge` 互斥。前者删除匹配的全部 QA 和 judgment，
后者只清空 judgment。Force 会先预检全部选中 case 和依赖，再统一清理并写回
所有 case；全部清理成功前禁止调用模型，避免不同 case 中新旧结果混合。

命令结束打印 QA 和 Judge 各自的完成数/总数。部分 QA 失败时仍判定其他已完成
回答，最终以非零状态退出。

`summarize` 为每个实际 effort 生成：

```text
results/<group>/<qwen|kimi|gemini>_<video|description>_<none|default>_summary.json
```

同一模型和 input 的不同 effort 合并到：

```text
results/<group>/<qwen|kimi|gemini>_<video|description>_report.md
```

Report 同时展示 QA 的完整 `raw_answer`、Judge 实际使用的 `final_answer`、verdict
和 confidence。

## 运行时代码

```text
scripts/
├── pipeline.py
└── vconflict_pipeline/
    ├── cli.py
    ├── settings.py
    ├── core.py
    ├── transport.py
    ├── authoring.py
    ├── descriptions.py
    ├── generation.py
    ├── deletion.py
    ├── qa.py
    ├── evaluation.py
    └── reporting.py
```

`scripts/seed/seed21_pro_video_qa.py` 和 `scripts/videohallu/` 下的独立脚本不属于
主 pipeline。
