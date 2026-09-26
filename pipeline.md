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
delete
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
python scripts/pipeline.py summarize --group <group_name> --input video \
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
results/<group>/<model>/
```

不传 `--group` 时结果位于 `results/<model>/`，其他数据使用平铺目录。
通常 `--case-id`、`--video-id` 和
`--question-id` 均可重复传入以缩小运行范围。删除视频或问题时只接受一个
`--case-id`；使用 `delete --all` 时可重复传入同一 group 下的多个 case ID。

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

`questions` 会分别检查 case 顶层问题和各视频的 `variant_context.questions`，
默认仅补齐空的问题列表。共享问题只使用继承该问题的 videos 作为生成上下文；
独立变体只使用该视频的 prompt 和自己的 `conflict_spec`，不会混入其他变体。
`questions --force` 会重生成选中 case 中所有实际使用的问题上下文。
每次更新会清除使用该问题上下文的视频 QA/judgment，并同步清除被替换顶层问题的
question-only 历史；
同一 case 的全部生成和校验成功后才一次性保存。
新问题 ID 直接使用 `q001`、`q002`、`q003`，不再保存
`question_pair_id` 或 `question_type`。使用删除功能后问题 ID 可以不连续；其他问题
不会被重编号。旧 JSON 中已有的旧式问题 ID 仅做兼容读取，pipeline 不会生成或
恢复旧问题字段。

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

视频默认生成 5 秒、720p；需要其他设置时可显式传入 `--duration` 和
`--resolution` 覆盖默认值。

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

## 删除 case 内容

删除视频或问题时，`delete` 只接受一个 `--case-id`，但可以在该 case 内同时删除
多个 conflict 视频和多个问题：

```bash
python scripts/pipeline.py delete \
  --group classic_fairy_tale_film_conflicts \
  --case-id alice_drink_makes_her_grow \
  --video-id v001 \
  --video-id v002 \
  --question-id q001
```

删除视频会从 JSON 中移除完整 video 对象，并删除其本地视频、description、QA、
judgment 和其他历史。只能单独删除 conflict 视频，且删除后必须至少保留一个
conflict；control 或最后一个 conflict 只能通过删除整个 case 处理。本地视频已经
缺失时仍会清理 JSON。删除问题会清除所有视频中该 question ID 对应的全部 QA 和
judgment。任一指定 ID 不存在时不会执行任何删除。

删除整个 case：

```bash
python scripts/pipeline.py delete \
  --group classic_fairy_tale_film_conflicts \
  --case-id alice_drink_makes_her_grow \
  --case-id alice_eat_cake_makes_her_shrink \
  --all
```

`--all` 不能与 `--video-id` 或 `--question-id` 混用，但允许重复传入同一 group 下
的多个 `--case-id`。所有 case JSON 都会先完成存在性、schema 和路径预检；任一
case 预检失败时不会删除其中任何一个。预检成功后，它会删除每个 case JSON，并
递归删除 JSON 中各视频 `local_path` 所在的目录，包括目录内未记录的文件；缺失的
视频目录不影响 JSON 删除。删除问题也会删除其 `question_only_results` 并计入清理
数量。Source Markdown、远端 Seedance task 和 `results/`
不会被删除。任何删除都会使已有 summary/report 过期。

## QA 与 Judge

`qa-judge` 先运行 QA，再用 Luna Pro 判定本次筛选范围内尚未判定的回答：

```bash
python scripts/pipeline.py qa-judge \
  --group classic_fairy_tale_film_conflicts \
  --input video \
  --qa-model qwen3.8-max \
  --thinking-effort all
```

上述命令会先执行下面的逐 question 双 baseline 筛选，再运行通过筛选的 conflict
视频 QA。运行 Fairy video 的默认 `no_prefix` 条件。只有 Fairy video 可以选择加入
作品名前缀；对照条件显式执行：

```bash
python scripts/pipeline.py qa-judge \
  --group classic_fairy_tale_film_conflicts \
  --input video \
  --qa-model qwen3.8-max \
  --thinking-effort all \
  --with-work-title-prefix
```

此时每个问题发送为：

```text
This is a video clip from the work <title>. <question>
```

`<title>` 取 case `title` 第一个冒号前的作品名。其他 group、description 或
question-only 使用 `--with-work-title-prefix` 会在任何模型请求前报错。

纯文字实验：

```bash
python scripts/pipeline.py qa-judge \
  --group classic_fairy_tale_film_conflicts \
  --input description \
  --qa-model qwen3.8-max \
  --thinking-effort all
```

不带视频或 description 的 question-only control：

```bash
python scripts/pipeline.py qa-judge \
  --group classic_fairy_tale_film_conflicts \
  --input question_only \
  --qa-model qwen3.8-max \
  --thinking-effort all
```

该模式只把 case 顶层原始 question 和 `Final answer:` 格式要求发给模型。结果存入
question 的可选 `question_only_results` 数组，按
`input + question_id + qa_model + thinking_effort` 去重，且不写
`context_text_en` 或 `work_title_prefix`。Gemini、Kimi 使用纯文本 payload；Qwen
发送不含 video URI 的文本请求。运行不读取视频文件，也不检查视频 status、
description 或 human review。

首版不支持 `variant_context.questions`：选中 case 只要含私有 question scope，
就会在 provider 请求和 force 清理前失败。`--video-id` 与
`--with-work-title-prefix` 均不能用于 question-only。Math group 暂不纳入这一模式。

`--input` 接受 `video`、`description` 或 `question_only`，默认 `video`。不再支持
`--input-mode`。

视频输入预检会检查本地 `local_path`：选中视频的文件存在而状态不是 `ready` 时，
先修正状态并写回 case JSON；状态不是 `ready` 且文件不存在时跳过。若状态已是
`ready` 但文件不存在，整次 `qa-judge` 会在调用模型前报错。

模型与 effort：

- Qwen `qwen3.8-max`：`none` 或 `default`；`all` 同时执行两者。
- Kimi `kimi-k3`：仅 `default`，实际 reasoning effort 为 `max`。
- Gemini：CLI 使用 `--qa-model gemini`，实际调用
  `google/gemini-3.1-pro-preview`；仅支持 `default`，实际 reasoning effort 为
  `medium`。
- Cosmos3-Nano：CLI 使用 `--qa-model cosmos3-nano`，调用单卡本地 vLLM 上的
  `nvidia/Cosmos3-Nano`；支持 `none` 和 `default`，视频以 4 fps 采样，
  `max_tokens` 默认 4096。`--cosmos-max-tokens` 可调整输出上限，
  `--cosmos-workers` 默认 4；
  Cosmos 的 `--qa-workers` 默认也为 4，其他模型仍为 3。

Cosmos 服务在仓库根目录运行 `./scripts/start_cosmos_vllm.sh` 启动；完整启动参数
和架构说明见 `plan.md` 的「模型配置」。视频路径须是服务端可读取、位于
`--allowed-local-media-path` 下的 MP4。预检从 `/v1/models` 获取实际请求模型 ID；
视频请求会自动采用 `plan.md` 中的全帧加载和 4 fps 处理器采样配置。
已有 Cosmos QA 需用 `--force-qa` 重跑，才能使用新的处理路径。
服务不可达、模型 ID 不明确或选中的视频格式错误时，`--force-qa` 不会清除旧回答。
输出达到 `max_tokens` 上限时该次 QA 失败，不保存截断回答。修改输出上限后需要
`--force-qa` 才能替换已有结果。Cosmos QA 不使用 OpenRouter RPM 限制；Judge
仍使用原有 OpenRouter 限制。

Description QA 在每个 video 对象内部按以下字段去重：

```text
input + question_id + qa_model + thinking_effort
```

仅 `classic_fairy_tale_film_conflicts` 的 Video QA 写入布尔字段
`work_title_prefix`，并按以下字段去重，因此 Fairy 的两种条件可以并存：

```json
"work_title_prefix": false
```

`with_prefix` 条件写入 `true`。Description QA 不得包含该字段。

```text
input + question_id + qa_model + thinking_effort + work_title_prefix
```

其他 group 的 Video QA 使用与 Description QA 相同的四字段去重键，新结果不写入
`work_title_prefix`。已有非 Fairy 结果无论缺少该字段还是保存了 `false` 或 `true`，
均忽略该字段且无需迁移。

所有 QA backend 都会把以下要求放在 user prompt 的最后；视频输入中，这段文字
也是最后一个多模态 content item：

```text
Conclude with exactly one final line in this format: Final answer: <your clear, direct answer in one sentence>.
```

模型可以在此前输出分析，但最后一个非空行必须严格以 `Final answer:` 开头，且
标记后必须有内容。Pipeline 将完整响应保存为 `raw_answer`，并将标记后的内容
单独保存为 `final_answer`。缺少有效末行时，该 question/effort 立即失败，不保存
QA 记录、不额外重试；同批其他 QA 和已有成功回答的 Judge 继续执行。

重复运行会按视频文件 SHA-256 检查已有 QA 的输入指纹，不会追加相同输入的重复
结果。视频、description 或 questions 由 pipeline 重建时，相应 QA 会被自动清理。
手工替换同路径视频会使旧 QA 过期，需重新运行 QA 和 Judge。

旧 QA 没有 `final_answer`。Pipeline 不猜测或迁移旧回答；普通运行或
`--force-judge` 选中这类记录时，会在任何模型请求前报错。使用 `--force-qa`
统一清除并重新生成即可。

旧 Fairy video QA 若没有 `work_title_prefix`，不会被猜测为任一条件。可以按当时
真实 prompt 手工补充 `true` 或 `false`；使用 `--force-qa` 时，pipeline 会清除当前
筛选范围内缺少该字段的旧 Fairy video 结果并按当前条件重跑，同时保留另一种已
明确标记的 prefix 结果和全部 description 结果。Description QA 不保存该字段。

强制运行有两个互斥选项：

```bash
python scripts/pipeline.py qa-judge ... --force-qa
python scripts/pipeline.py qa-judge ... --force-judge
```

- `--force-qa` 删除筛选范围内全部 QA 记录及其中的 judgment，再重新执行。
- `--force-judge` 保留 QA 回答，只清空全部匹配 judgment，再重新判定。

Question-only 的 force 只作用于匹配的 `question_only_results`；不会清理视频 QA。

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

Question-only 固定以 control 角色判定：normal reference 为 `context_grounded`；
conflict reference、混合或其他无法确认的回答为 `ambiguous_or_unjudgeable`，不会
产生 `knowledge_trapped`。

旧 JSON 中的 `video_grounded` 无需迁移；读取和统计时会解释为
`context_grounded`。

Conflict 的 answer-level `trapped_answer_rate` 和 video-level
`trapped_video_rate` 都以对应的全部 conflict 样本为分母，包括
`ambiguous_or_unjudgeable`：

```text
knowledge_trapped / (context_grounded + knowledge_trapped + ambiguous_or_unjudgeable)
```

没有 conflict 样本时 rate 为 `null`。Control 指标的计算方式不变。

## Question 级双 baseline 筛选

从 2026-09-26 起，`qa-judge --input video` 默认按如下顺序执行，不能绕过：

1. 同一 question、QA 模型、thinking effort 的 question-only QA + Judge。
2. 第一层为 `context_grounded` 后，执行该 question 对应的 control 视频 QA + Judge。
3. 两层都为 `context_grounded`，才允许该 question 的 conflict 视频 QA。

筛选单位是 `case_id + question_scope + question_id + model + thinking_effort`，
control 视频还匹配作品名前缀条件。共享 question 的 scope 为 `case`；私有
`variant_context.questions` 的 scope 为所属 `video_id`，即使 ID 相同也不能互用。
一个 question 未通过不会排除同 case / 同 video 的其他 question。
Control 视频是第二层 baseline，只要求第一层通过，不要求它先通过自身。
Description QA 的执行流程保持独立；其历史统计也可以选择下述 baseline 筛选。

共享题目的两层回答、判分、阶段和输入指纹分别保存在现有 `question_only_results` /
control `qa_results`；私有变体保存在该题目上的 `baseline_results`。每个回答只有一份
权威记录，避免重新判分后存在互相矛盾的副本。
指纹绑定题目内容、参考答案、事实和对应 control 文件 SHA-256；参考答案或视频变化
后旧结果不可作为通过依据。旧 control QA 仅在题目、配置和来源检查均匹配时复用；
旧 question-only 记录没有 baseline 来源指纹时会重新执行。错误回答是筛选失败；
缺失、过期、未判分和 control 不可用分别记录，不会被当作通过。请求失败保留已完成
阶段，下次继续；已判错的结果不会自动反复尝试到答对。

私有变体使用其显式 `variant_context.matched_control_path`，不会回退到共享 control。
缺少该映射或对应视频不可用时，该题不放行，并输出原因。该路径不会自动生成视频。
原有独立 `--input question_only` 命令仍仅支持共享问题；下面的新 baseline 入口支持
私有变体，不受该旧入口限制。

### 给已有 QA 补齐两层 baseline

只补 baseline，不重新运行 conflict QA，也不删除历史回答：

```bash
python scripts/pipeline.py qa-judge \
  --group classic_fairy_tale_film_conflicts \
  --input video --qa-model qwen3.8-max --thinking-effort all \
  --baselines-only
```

可保留原实验的 `--case-id`、`--video-id`、`--question-id`、`--video-scope` 和
`--with-work-title-prefix` 选择。选择某个 conflict 视频仍会自动运行它对应的 control
baseline，不要求把 control 加入 `--video-id`。所有 baseline 阶段按题逐项保存。

普通 video 运行中的 `--force-qa` / `--force-judge` 只处理通过筛选的 conflict 结果，
不会清理 baseline 或未通过题目的历史结果。要主动重跑 baseline，显式组合
`--baselines-only --force-qa`；仅重新判分使用 `--baselines-only --force-judge`。

### 筛选历史统计

```bash
python scripts/pipeline.py summarize \
  --group classic_fairy_tale_film_conflicts \
  --input video --qa-model qwen3.8-max --thinking-effort all \
  --baseline-filter passed
```

该命令只读 case 数据，不发模型请求。JSON 指标与 Markdown 明细都仅保留两层通过
的 question；answer-level 指标先逐题过滤，video-level 标签由保留的问题重新聚合，
没有剩余问题的视频不计入分母。输出文件名增加 `_baseline_passed`，不会覆盖原始
报告。JSON 的 `baseline_gate` 包含题目总数、通过数、排除数、原因及逐题配置状态；
没有通过题目时分母为 0、rate 为 `null`。Control 统计同样按 question 过滤；需要完整
baseline 正确率时查看默认全量报告。

`--baseline-filter all`（默认）保留原有全量统计口径。Description 筛选使用对应的
无作品名前缀 video baseline。不同模型 / effort 的通过题目集合可以不同，不能把
筛选后指标当作相同样本集上的直接比较。

离线回归测试（不调用模型，不写真实 dataset / results）：

```bash
python -B -m unittest discover -s tests -v
```

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

模型短名映射为 `qwen`、`kimi`、`gemini` 和 `cosmos`。以上命令自动生成：

```text
results/classic_fairy_tale_film_conflicts/qwen/qwen_description_none_summary.json
results/classic_fairy_tale_film_conflicts/qwen/qwen_description_default_summary.json
results/classic_fairy_tale_film_conflicts/qwen/qwen_description_report.md
```

所有模型的新 summary 和 report 都写入各自的模型子目录，文件名保持原样。
旧的平铺结果留在原处，不移动或迁移。

Fairy video 的两种条件分别汇总：

```bash
# no_prefix
python scripts/pipeline.py summarize \
  --group classic_fairy_tale_film_conflicts \
  --input video --qa-model qwen3.8-max --thinking-effort all

# with_prefix
python scripts/pipeline.py summarize \
  --group classic_fairy_tale_film_conflicts \
  --input video --qa-model qwen3.8-max --thinking-effort all \
  --with-work-title-prefix
```

它们分别生成 `qwen_video_no_prefix_<effort>_summary.json` 和
`qwen_video_with_prefix_<effort>_summary.json`，以及各自的
`qwen_video_no_prefix_report.md` 和 `qwen_video_with_prefix_report.md`。Summary
JSON 包含布尔字段 `work_title_prefix`，report 显示 `no_prefix` 或
`with_prefix`。其他 group 的 video 和所有 description 保持原文件名，summary 和
report 也不输出 prefix 元数据。

不指定 `--thinking-effort` 或使用 `all` 时，只为现有已判定结果中实际存在的
effort 分别生成 summary；若没有结果，则生成模型默认 effort 的空 summary。
不同 effort 的最新结果放在同一份 report 中，report 同时展示完整
`raw_answer` 和实际送审的 `final_answer`。不再支持手工指定 `--output`。

Question-only 汇总生成：

```text
results/<group>/<model>_question_only_<effort>_summary.json
results/<group>/<model>_question_only_report.md
```

JSON 只包含 `answers.control` 和各 case 的 `control.answers`/`labels`，不包含
`videos`。`grounded_answer_rate` 的分母是全部 question-only 回答，包括
`ambiguous_or_unjudgeable`。同一 question/model/effort 有重复历史时按
`(timestamp, run_id)` 选择最新记录。Markdown 按 case/question 展示 raw answer、
final answer、verdict 与 confidence，不显示 video ID、文件链接或 context。
