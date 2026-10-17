# Video Knowledge Conflict 实验框架

运行命令和输出用法见 [pipeline.md](pipeline.md)，并发协调、额度与恢复机制见
[concurrency.md](concurrency.md)。本文定义当前实验设计和数据语义。

## 研究目标

测量问答模型在输入证据与经典知识冲突时，是否遵循当前证据，或退回经典答案。
每个 case 固定一组正常事实和冲突事实，以匹配的正常 control 视频作为对照。
Authoring 每次生成 1–5 个 conflict 视频方案和一个 control；入库的数学变体可
继续积累。普通 case 至少保留一个 conflict，control 可选且最多一个；保留带
`quality_curation` 和人工备份记录的裁剪例外。

问题按独立语义目标生成，默认每个上下文 1–3 题。题目须中性、自包含，不泄露
冲突结果或暗示评测意图；同一问题使用 conflict 与 normal 两类 reference。
Luna Pro 负责 authoring、问题生成与校验、生成式文字 context 和 Judge；Seedance
生成视频；各 QA 模型在相同实验条件下分别作答。

## 实验条件

| 输入 | 提供的证据 | 判分角色 |
|---|---|---|
| video | conflict 视频及其有效问题 | conflict |
| control | control 视频及其有效问题 | control |
| description | conflict 视频对应的中性事实文本和问题 | conflict |
| question_only | conflict 视频的有效原始问题，无额外证据 | control |

Description 不生成 control 文本。存在实际视频审核观察时，context 使用审核后的
事实段落；否则由 Seedance prompt 生成中性文本。Fairy context 自然地以作品名
开头，经典物化实验仅在名称确有公认含义时加入实验名，其余组不强加前缀。

仅 `classic_fairy_tale_film_conflicts` 的 video/control 条件区分有无作品名前缀；
作品名取当前上下文标题第一个冒号前的部分。Description 和其他组的视频不使用
此条件。Video/control/description 另区分 `based=false|true`，开启时加入中性的
依据输入回答指令；关闭时保持原有 prompt 和指纹。Control 复用视频请求流程，
QA 仍保存为 `input_mode: video`，通过所属视频的 role 区分，历史 control 结果可续用。

四种输入独立执行 QA → Judge。Video、control 和 description 不自动运行
question-only，也不要求其判定通过。独立 question-only 遍历 conflict 视频的
有效问题：共享问题按 case scope 去重，私有 `variant_context.questions` 按 video ID
隔离，均遵循视频的 `question_ids` 关联；不依赖视频文件、ready 状态或审核。

## 可选报告筛选

Video、control 和 description 默认执行、汇总全部有效目标。仅在汇总时显式选择
`summarize --filter passed`，才逐题保留同一问题、QA 模型和 thinking effort 的
有效 question-only 判定为 `context_grounded` 的目标回答。汇总只读取已有结果，
不补跑 QA 或 Judge；`--input question_only` 不能组合 `--filter passed`。

筛选单位包含 case、question scope、question ID、模型和 effort。共享题目 scope 为
`case`，私有 `variant_context.questions` 的 scope 为所属 video ID，ID 相同也不能跨
scope 复用。一题未通过不会排除同 case 或同视频的其他题目。

Question-only 只发送原始问题，不加 based 指令或作品名前缀；筛选身份和来源指纹均不
包含这两种目标条件。三种目标输入可复用同 scope、同问题、同模型和 effort 的
有效 question-only 回答。每个视频只筛选自己的有效问题；`question_ids` 可保留部分
题目，`variant_context.matched_control_path` 不参与筛选。缺少结果、过期、未判分或
判错只影响筛选报告，不影响目标执行、预检、force 清理或完成计数；已判错的
question-only 回答不会在普通续跑中自动反复重试到答对。

Video 报告只统计 conflict，control 报告只统计 control，未选角色的 JSON 计数为零。
全量报告统计所选角色的全部有效判定，不受当前 gate 是否通过影响；筛选报告先按题
保留 question-only 通过的回答，再重新聚合 video 标签，没有剩余题目的视频不计入分母。报告记录 gate 总数、通过数、排除原因和
逐题配置状态。各模型和 effort 的通过样本集合可能不同，不能当作相同样本集直接
比较；based、普通目标及有无作品名前缀共用原始 filter gate，但分别统计目标回答。

## 判分与指标

所有 QA 提示都要求末行使用 `Final answer:`。保存完整 `raw_answer` 供核查，但
Judge 只读取从正文提取的 `final_answer`，不从解释或 reasoning 中推断答案。
解析取最后一个非空行最后一次大小写匹配标记之后的非空文本，允许标记前有解释。
正常结束但标记缺失、答案为空或仅出现在更早的行时，由调度器完整重试原请求一次；
正文为空或只有 reasoning 也属于格式失败。重试的输入、提示词和生成参数完全相同，
不添加纠错提示，也不传回第一次回答。第二次有效时只保存第二次并进入 Judge，记录
可选 `final_answer_retry_count: 1`；第二次仍格式失败则终止该任务，不保存成功 QA，
不释放下游。输出截断直接拒绝，不进入格式重试；其他成功回答继续判分。

此规则统一用于全部 QA 模型、输入和 effort，包括独立 question-only 实验。判分错误
不触发 QA 重试，已有有效历史结果不自动重跑。每次格式重试重新申请共享并发和
RPM 额度，沿用同一任务认领；格式重试与网络重试分别计数，网络错误仍遵循
`--max-retries`，格式重试不会重置或占用其额度。

Judge 根据问题、最终答案、输入角色、事实和两类 reference 分类：

| 条件 | Verdict |
|---|---|
| conflict 回答 conflict reference | `context_grounded` |
| conflict 回答 normal reference | `knowledge_trapped` |
| control 回答 normal reference | `context_grounded` |
| 混合、矛盾、含糊、回避、无关或无法可靠归类 | `ambiguous_or_unjudgeable` |

Description 的 grounded 表示遵循文字 context。Control 和 question-only 均按正常
参考答案判定；匹配 conflict reference 或无法确认的回答为 ambiguous，不产生
`knowledge_trapped`。
Judgment 保存 verdict、confidence、时间、Judge 模型、请求 ID 和适用的来源指纹。

报告分别统计 answer-level 和 video-level。每个 video/model/effort 取每题最新有效
记录；只有 grounded 而没有 trapped 的视频聚合为 grounded，只有 trapped 而没有
grounded 时聚合为 trapped，两者同时出现或两者均无则为 ambiguous。

```text
grounded_answer_rate = role grounded answers / all valid judged role answers
trapped_answer_rate  = role trapped answers  / all valid judged role answers
grounded_video_rate  = role grounded videos  / all valid judged role videos
trapped_video_rate   = role trapped videos   / all valid judged role videos
```

汇总始终同时输出 grounded 和 trapped 比例，按 conflict/control 角色分别统计，
分母均包括 ambiguous，保留六位小数；对应角色无样本时两种 rate 均为 `null`。
Control 和 question-only 有样本时 trapped 比例按现有判分规则为 0。
Question-only 仅统计 answer-level control 指标，重复历史按 `(timestamp, run_id)`
选择最新记录；不产生 video-level 指标。原生 Markdown 按 effort、角色列出两种比例。

## 数据结构

正式 case 位于 `dataset/cases/` 的可选 group 子目录，唯一受支持的 schema 为 4.0。
每个 case JSON 保存实验运行状态，视频文件独立存放；JSON 使用原子替换写回。

| 对象 | 主要内容 |
|---|---|
| case | `schema_version`、`case_id`、英文 `title`、`conflict_spec`、`questions`、`videos` |
| conflict_spec | `normal_fact_en`、`intended_video_fact_en` |
| question | `question_id`、`text_en`、两类 reference，可选 `question_only_results` |
| video | `video_id`、`role`、`seedance_prompt_en`、`task_id`、`status`、`local_path`、`qa_results` |
| description | `context_en`、可选 `context_prefix_en`、来源、来源 SHA-256、生成模型、时间和请求 ID |
| QA | `run_id`、时间、输入模式、问题 ID/正文、模型、effort、温度、`raw_answer`、`final_answer`、可选 usage/reasoning、`final_answer_retry_count: 1`、judgment |
| variant_context | 私有 facts/questions、可选标题、`matched_control_path` |
| 画面与审题证据 | `video_observation`、`require_video_observation`、`question_audit` 和来源指纹 |

Description 仅属于 conflict 视频。Question-only 结果不含 context 文本、作品名前缀
或 based。共享结果属于 case 顶层 question，保存在 `question_only_results`；私有
结果保存在对应视频私有题目的 `filter_results`。报告筛选直接读取这些权威回答。

Video/control/description 结果记录布尔 `based`。仅 Fairy video/control 额外记录布尔
`work_title_prefix`；description 不得保存此字段，其他组的视频忽略历史 prefix 值。
下列去重键中的 video 指持久化输入介质，control 也使用该键：
容器内去重键为：

```text
question_only: input + question_id + model + thinking_effort
video/description: input + question_id + model + thinking_effort + based
Fairy video: input + question_id + model + thinking_effort + based + work_title_prefix
```

旧 question ID、`video_grounded`、旧 baseline 字段及旧哈希字段兼容读取，不批量迁移。
历史 `human_review`、`qualification_pending` 字段忽略，不再写入或校验；schema 保持 4.0。
`video_grounded` 解释为 grounded，缺失 based 解释为 false，Gemini medium effort
解释为 default。Filter 读取新字段优先，否则读取 baseline 别名；私有新旧容器共同
查找最新记录，续跑在原容器更新。命名变化不改变指纹算法或版本。

## 来源与过期规则

视频状态不能由文件存在推断为 ready。各组 video/control 的 QA 和汇总均按所选
角色及 ready 状态选择视频，不使用人工审核状态或资格门槛。数学 authoring 的参考
视频同样要求 conflict、ready、文件存在，并保留画面证据检查及原有排序。
独立模型审题回执供质量审计使用，不替代来源新鲜度检查。视频重新
生成后，已有观察失效；需要审核观察时，没有有效 observation 不得把生成意图
当作实际画面证据。Description 可使用有效的 prompt 来源文本，不要求视频 ready。

问题审核回执记录实际模型、时间、请求 ID、逐项检查和 scope 指纹；问题非空不
等于已通过独立审题。已入库变体的 `dataset/variant_cases` JSON 是历史来源快照，
`canonical_case_path` 指向正式数据，不能用于重新生成或删除正式视频。

QA 新鲜度绑定实际问题、视频文件 SHA-256 或 description 文本；Judgment 进一步
绑定最终答案、参考答案、事实、角色和 QA 来源。Filter 指纹绑定问题内容、参考
答案、事实和 scope。手工替换
同路径视频、修改题目/参考或文字 context 后，过期结果不会用于完成判断和统计。

无来源指纹的历史数学 QA 不能作为有效结果；旧 question-only 回答无 filter 来源
指纹时不能直接作为 filter 通过依据。旧 `context_sha256` / `video_sha256` 字段
可读取，但不作为去重键或独立统计条件；当前来源检查使用 input/filter 指纹。

Pipeline 重建问题时清理受影响的视频 QA，替换共享问题时清除其 question-only
历史；重建 description 只清理对应 description QA。显式重新生成 ready 视频会
清除其全部 QA、description 和审核观察，新任务提交也清空旧 description/观察。
删除或重建视频不影响独立 question-only 回答；删除问题时同步移除视频
`question_ids` 中的关联及该题历史。旧 QA 没有 final_answer，或旧 Fairy
video/control 缺少 prefix 元数据时，须按 [pipeline.md](pipeline.md#历史数据兼容) 处理。

## 模型配置与采样协议

| 职责 / CLI 名称 | 持久化模型 ID | 生成参数与 effort |
|---|---|---|
| Author / Questions / Judge | `openai/gpt-5.6-luna-pro` | OpenRouter 结构化请求 |
| `gemini` | `google/gemini-3.1-pro-preview` | temperature 0；default 对应 reasoning medium |
| `qwen3.8-max` | `qwen3.8-max` | temperature 0；none/default 关闭/开启 thinking |
| `kimi-k3` | `kimi-k3` | 有效 temperature 1；default 对应 reasoning max |
| `cosmos3-nano` | `nvidia/Cosmos3-Nano` | temperature 0、seed 0；none/default |
| `gemma4` | `google/gemma-4-31B-it` | temperature 0、seed 0；none/default |
| `qwen3.8-27b` | `Qwen/Qwen3.8-27B` | temperature 0、seed 0；none/default，开启 thinking 时 reasoning effort 为 xhigh |

省略 effort 时统一使用 default。本地服务请求模型 ID 取 `/v1/models` 返回值，
持久化 ID 保持表中实验标识。Gemma 通过 `chat_template_kwargs.enable_thinking`
显式控制推理；回答正文与可选 reasoning 分开保存，final_answer 仅从正文提取。
Qwen27B 同样显式设置 `chat_template_kwargs.enable_thinking`，开启时在该对象内设置
`reasoning_effort=xhigh`，正文和 reasoning 分开保存。本地默认输出上限为 Cosmos
8192、Gemma 2048、Qwen27B 32768；Qwen27B 服务默认上下文 65536。

- Gemini 和 Kimi 将本地视频编码为 Base64 Data URL，Kimi 请求体上限 100 MB。
- 云端 Qwen (`qwen3.8-max`) 使用中国大陆 DashScope SDK 上传本地视频，文件上限
  100 MiB，固定 fps=2。
- 本地 Qwen27B 使用服务端可读的 MP4 file URI。加载器保留原始帧，模型处理器
  采用官方默认 2 fps 和帧数边界，执行一次采样，避免重复采样。
- Cosmos 使用服务端可读的 MP4 file URI。加载器保留原始帧，再由模型视频处理器
  从头到尾均匀按 4 fps 采样，避免加载器和处理器重复采样。
- Gemma 使用服务端可读的 MP4 file URI，加载器对整段视频均匀采样最多 32 帧，
  不足时保留全部；视频处理路径每帧最多 70 个视觉 token，不叠加处理器 fps 采样。

Cosmos 视频请求参数：

```json
{
  "media_io_kwargs": {"video": {"video_backend": "opencv", "num_frames": -1, "fps": -1}},
  "mm_processor_kwargs": {"fps": 4, "do_sample_frames": true}
}
```

Gemma 视频请求参数：

```json
{
  "media_io_kwargs": {"video": {"video_backend": "opencv", "num_frames": 32, "fps": -1}}
}
```

Qwen27B 视频请求参数：

```json
{
  "media_io_kwargs": {"video": {"video_backend": "opencv", "num_frames": -1, "fps": -1}},
  "mm_processor_kwargs": {"fps": 2, "do_sample_frames": true}
}
```

Qwen27B 的 thinking 开关与 parser 参考 [vLLM 官方配方](https://recipes.vllm.ai/Qwen/Qwen3.8-27B)，
视频加载/采样行为参考 [vLLM 视频加载器](https://github.com/vllm-project/vllm/blob/main/vllm/multimodal/video.py)。

文字请求不包含视频或视频采样参数。目标实验和独立 question-only 使用相同 QA 模型配置，
本地模型不占 OpenRouter QA RPM，Judge 仍通过 OpenRouter。采样与生成参数属于
实验协议；部署和覆盖方法见 [pipeline.md](pipeline.md#模型服务与-qajudge)。

## 实现结构

统一入口为 `scripts/pipeline.py`，实现位于 `scripts/vconflict_pipeline/`：

| 模块 | 职责 |
|---|---|
| `cli.py` / `settings.py` | 参数校验、阶段分派、模型及路径配置 |
| `common.py` / `paths.py` / `storage.py` / `schema.py` | 共享异常与基础工具、路径发现、原子存储、schema 校验与构建 |
| `core.py` | 供已有独立脚本使用的显式兼容导出 |
| `authoring_definitions.py` / `authoring.py` | Prompt/schema 定义、生成校验修复与保存 |
| `generation.py` / `descriptions.py` / `deletion.py` | 视频、文本 context 和数据删除操作 |
| `result_rules.py` / `selection.py` / `filters.py` | 输入介质与角色、统一结果条件、有效视频/问题选择、question-only 来源及可选报告筛选 |
| `qa.py` / `qa_diagnostics.py` | 单次模型请求、回答解析、本次运行诊断 |
| `task_planning.py` / `task_execution.py` / `media_cache.py` | 任务身份与依赖规划、请求执行与结果合并、媒体准备与缓存 |
| `scheduler.py` / `runtime.py` | 调度、认领、额度准入、退避和进度；同机进程协调与锁 |
| `evaluation.py` / `reporting.py` | 共用目标规划的预检、force 清理与完成计数；按角色汇总快照与独立报告 |
| `evidence.py` / `integrity.py` / `audit.py` | 画面证据、来源新鲜度、离线结构审核 |
| `transport.py` | HTTP、凭据保护及其他阶段使用的限流重试 |

QA 单请求失败直接向调度器抛出异常，由调度器统一决定重试、限流和失败处理。
每条 QA 保存后即可判分，所选四种输入之间没有执行依赖。
`--force-qa` / `--force-judge` 直接清理所选输入、模型、effort 和 based/prefix 条件的
回答或判定，再执行该输入；不先运行 question-only，不清理其他输入条件。
完整协调实现约定仅在
[concurrency.md](concurrency.md) 维护。独立对比解码实验见
[scripts/mcd_v1/README.md](scripts/mcd_v1/README.md)。
