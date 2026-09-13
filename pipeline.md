# Pipeline 使用说明

唯一入口为：

```bash
python scripts/pipeline.py <stage> [参数]
```

可用 stage：

```text
author
questions
description
generate
review
qa-judge
summarize
```

完整视频实验需要显式执行：

```bash
python scripts/pipeline.py author --group <group_name>
python scripts/pipeline.py questions --group <group_name>
python scripts/pipeline.py generate --group <group_name>
python scripts/pipeline.py qa-judge --group <group_name> --input video \
  --qa-model qwen3.8-max
```

不再提供 `split-source`、`describe`、`all`、`qa`、`judge`、`summary`、
`report` 或 `compare` stage。

## 数据组与目录

`--group` 将 source cases、case JSON、视频和结果分别映射到：

```text
dataset/source_cases/<group>/
dataset/cases/<group>/
videos/seedance/<group>/<case_id>/
results/<group>/
```

不传 `--group` 时使用平铺目录。`--case-id`、`--video-id` 和
`--question-id` 均可重复传入以缩小运行范围。

## 环境变量

```powershell
$env:OPENROUTER_API_KEY = "<openrouter-api-key>"
$env:ARK_API_KEY = "<ark-api-key>"
$env:DASHSCOPE_API_KEY = "<dashscope-api-key>"
$env:MOONSHOT_API_KEY = "<moonshot-api-key>"
```

Qwen 需要 DashScope Python SDK 1.24.6 或更新版本：

```powershell
python -m pip install -U "dashscope>=1.24.6"
```

可选 endpoint 覆盖：

```powershell
$env:ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
$env:DASHSCOPE_BASE_HTTP_API_URL = "https://dashscope.aliyuncs.com/api/v1"
$env:MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"
```

历史 `QWEN_BASE_URL` 仍兼容；`/compatible-mode/v1` 后缀会自动转换为
`/api/v1`。

## 数据准备阶段

Source cases 需要预先按“一份 Markdown 对应一个 case”放入
`dataset/source_cases/<group>/`，pipeline 不再负责拆分源 Markdown。

生成 schema 4.0 case 和 Seedance prompts：

```bash
python scripts/pipeline.py author \
  --group classic_fairy_tale_film_conflicts \
  --case-workers 2 \
  --openrouter-workers 2 \
  --openrouter-rpm 20
```

生成中性 questions：

```bash
python scripts/pipeline.py questions \
  --group classic_fairy_tale_film_conflicts
```

`questions --force` 会替换问题并清除选中 case 的全部 QA 和 judgment。
新问题 ID 直接使用 `q001`、`q002`、`q003`，不再保存
`question_pair_id` 或 `question_type`。

为 conflict prompts 生成文字 context：

```bash
python scripts/pipeline.py description \
  --group classic_fairy_tale_film_conflicts
```

Description QA 收到的文本格式固定为：

```text
{context}

Question:
{question}

Conclude with exactly one final line in this format: Final answer: <your clear, direct answer in one sentence>.
```

`description --force` 重写 context，并只清除对应的 description QA。

生成或续跑 Seedance 视频：

```bash
python scripts/pipeline.py generate \
  --group classic_fairy_tale_film_conflicts \
  --seedance-workers 3 \
  --seedance-total-workers 6
```

失败任务使用 `--retry-failed`。视频重新生成成功后只清除 video QA，保留
description QA。

记录人工审核：

```bash
python scripts/pipeline.py review \
  --group classic_fairy_tale_film_conflicts \
  --case-id alice_drink_makes_her_grow \
  --video-id v001 \
  --decision verified
```

## QA 与 Judge

`qa-judge` 先运行 QA，再用 Luna Pro 判定本次筛选范围内尚未判定的回答：

```bash
python scripts/pipeline.py qa-judge \
  --group classic_fairy_tale_film_conflicts \
  --input video \
  --qa-model qwen3.8-max \
  --thinking-effort all
```

纯文字实验：

```bash
python scripts/pipeline.py qa-judge \
  --group classic_fairy_tale_film_conflicts \
  --input description \
  --qa-model qwen3.8-max \
  --thinking-effort all
```

`--input` 只接受 `video` 或 `description`，默认 `video`。不再支持
`--input-mode`。

模型与 effort：

- Qwen `qwen3.8-max`：`none` 或 `default`；`all` 同时执行两者。
- Kimi `kimi-k3`：仅 `default`，实际 reasoning effort 为 `max`。
- Gemini：CLI 使用 `--qa-model gemini`，实际调用
  `google/gemini-3.1-pro-preview`；仅支持 `default`，实际 reasoning effort 为
  `medium`。

QA 在每个 video 对象内部按以下字段去重：

```text
input + question_id + qa_model + thinking_effort
```

所有 QA backend 都会把以下要求放在 user prompt 的最后；视频输入中，这段文字
也是最后一个多模态 content item：

```text
Conclude with exactly one final line in this format: Final answer: <your clear, direct answer in one sentence>.
```

模型可以在此前输出分析，但最后一个非空行必须严格以 `Final answer:` 开头，且
标记后必须有内容。Pipeline 将完整响应保存为 `raw_answer`，并将标记后的内容
单独保存为 `final_answer`。缺少有效末行时，该 question/effort 立即失败，不保存
QA 记录、不额外重试；同批其他 QA 和已有成功回答的 Judge 继续执行。

重复运行不会读取整个视频计算 SHA-256，也不会追加重复结果。视频、description
或 questions 由 pipeline 重建时，相应 QA 会被自动清理。若手工替换同路径视频，
必须使用 `--force-qa`。

旧 QA 没有 `final_answer`。Pipeline 不猜测或迁移旧回答；普通运行或
`--force-judge` 选中这类记录时，会在任何模型请求前报错。使用 `--force-qa`
统一清除并重新生成即可。

强制运行有两个互斥选项：

```bash
python scripts/pipeline.py qa-judge ... --force-qa
python scripts/pipeline.py qa-judge ... --force-judge
```

- `--force-qa` 删除筛选范围内全部 QA 记录及其中的 judgment，再重新执行。
- `--force-judge` 保留 QA 回答，只清空全部匹配 judgment，再重新判定。

Force 会先加载和验证全部选中 case、依赖、凭据、视频或 description，然后统一
计算并写回所有清理。只有全部 case 清理完成后才会发出第一个模型请求。不会执行
一个 case 后再清理下一个 case。若清理失败，本次运行不发出任何新请求。

部分 QA 请求失败时，Judge 仍会处理其余已完成回答，最终返回非零退出码。命令
结束打印：

```text
QA: <已完成>/<总数>
Judge: <已完成>/<总数>
```

Judge 的新标签为：

- `context_grounded`
- `knowledge_trapped`
- `ambiguous_or_unjudgeable`

Judge 只收到 `final_answer`、问题、输入角色和参考事实，不会收到
`raw_answer`。混合、矛盾、含糊、回避或无法匹配的最终回答统一判为
`ambiguous_or_unjudgeable`，不再通过“main answer”推断结论。新 judgment 只保存
`verdict`、`confidence`、时间、Judge 模型和请求 ID，不再生成
`extracted_answer` 或 `evidence`。

旧 JSON 中的 `video_grounded` 无需迁移；读取和统计时会解释为
`context_grounded`。

## Summary 与 Report

`summarize` 同时生成按 effort 拆分的 JSON summary 和一份合并 Markdown
report。必须指定一个 QA 模型：

```bash
python scripts/pipeline.py summarize \
  --group classic_fairy_tale_film_conflicts \
  --input description \
  --qa-model qwen3.8-max \
  --thinking-effort all
```

模型短名映射为 `qwen`、`kimi` 和 `gemini`。以上命令自动生成：

```text
results/classic_fairy_tale_film_conflicts/qwen_description_none_summary.json
results/classic_fairy_tale_film_conflicts/qwen_description_default_summary.json
results/classic_fairy_tale_film_conflicts/qwen_description_report.md
```

不指定 `--thinking-effort` 或使用 `all` 时，只为现有已判定结果中实际存在的
effort 分别生成 summary；若没有结果，则生成模型默认 effort 的空 summary。
不同 effort 的最新结果放在同一份 report 中，report 同时展示完整
`raw_answer` 和实际送审的 `final_answer`。不再支持手工指定 `--output`。
