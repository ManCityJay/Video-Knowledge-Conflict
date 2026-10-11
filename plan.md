# Video Knowledge Conflict 实验框架

运行命令和输出用法见 [pipeline.md](pipeline.md)，并发协调、额度与恢复机制见
[concurrency.md](concurrency.md)。本文定义当前实验设计和数据语义。

## 研究目标

测量问答模型在输入证据与经典知识冲突时，是否遵循当前证据，或退回经典答案。
每个 case 固定一组正常事实和冲突事实，以匹配的正常 control 视频作为对照。
Authoring 每次生成 1–5 个 conflict 视频方案和一个 control；审核入库的数学变体可
继续积累，每个正式 case 始终保留至少一个 conflict 和恰好一个共享 control。

问题按独立语义目标生成，默认每个上下文 1–3 题。题目须中性、自包含，不泄露
冲突结果或暗示评测意图；同一问题使用 conflict 与 normal 两类 reference。
Luna Pro 负责 authoring、问题生成与校验、生成式文字 context 和 Judge；Seedance
生成视频；各 QA 模型在相同实验条件下分别作答。

## 实验条件

| 输入 | 提供的证据 | 判分角色 |
|---|---|---|
| video | 视频和问题 | conflict 或 control |
| description | conflict 视频对应的中性事实文本和问题 | conflict |
| question_only | 共享原始问题，无额外证据 | control |

Description 不生成 control 文本。存在实际视频审核观察时，context 使用审核后的
事实段落；否则由 Seedance prompt 生成中性文本。Fairy context 自然地以作品名
开头，经典物化实验仅在名称确有公认含义时加入实验名，其余组不强加前缀。

仅 `classic_fairy_tale_film_conflicts` 的 video 条件区分有无作品名前缀；作品名取
当前上下文标题第一个冒号前的部分。Description 和其他组的视频不使用此条件。
Video/description 另区分 `based=false|true`，开启时加入中性的依据输入回答指令；
关闭时保持原有 prompt 和指纹。Based video 的执行目标只有 conflict，已有 based
control 回答保留供历史统计。

独立 question-only 实验只支持 case 顶层共享问题，不依赖视频文件或审核；含私有
问题 scope 的 case 会被拒绝。数学组目前不纳入独立 question-only 实验，但其私有
变体问题仍参与下述 question-only filter。

## 筛选流程

Video 和 description 默认逐题进行两层 filter：

1. 同一问题、QA 模型和 thinking effort 的 question-only QA，由 Judge 判定。
2. 第一层为 `context_grounded` 后，对匹配的正常 control 视频执行 QA/Judge。
3. 两层均为 `context_grounded`，才执行该题的 conflict video 或 description QA。

筛选单位包含 case、question scope、question ID、模型和 effort；control filter
还匹配 video prefix 条件。共享题目 scope 为 `case`，私有
`variant_context.questions` 的 scope 为所属 video ID，ID 相同也不能跨 scope 复用。
一题未通过不会排除同 case 或同视频的其他题目。Control 自身只依赖第一层 filter。

Filter 始终不加 based 指令。Fairy video control 使用与目标相同的作品名前缀；
description control 使用无前缀条件；question-only filter 只发送原始问题。
两种目标输入可复用条件和来源均相同的 filter 回答。

私有变体必须显式提供 `variant_context.matched_control_path`，不能回退到共享
control，也不会自动生成匹配视频。缺少映射、视频不可用、结果缺失、过期或未判分
都不能视为通过；已判错的回答不会在普通续跑中自动反复重试到答对。

全量报告保留原始统计；筛选报告先按题保留两层通过的回答，再重新聚合 video
标签，没有剩余题目的视频不计入分母。报告记录 gate 总数、通过数、排除原因和
逐题配置状态。各模型和 effort 的通过样本集合可能不同，不能当作相同样本集直接
比较；based 和普通目标共用原始 filter gate，但分别统计目标回答。

## 判分与指标

所有 QA 提示都要求末行使用 `Final answer:`。保存完整 `raw_answer` 供核查，但
Judge 只读取从正文提取的 `final_answer`，不从解释或 reasoning 中推断答案。
解析取最后一个非空行最后一次大小写匹配标记之后的非空文本，允许标记前有解释。
正常结束但标记缺失、答案为空或仅出现在更早的行时，由调度器完整重试原请求一次；
正文为空或只有 reasoning 也属于格式失败。重试的输入、提示词和生成参数完全相同，
不添加纠错提示，也不传回第一次回答。第二次有效时只保存第二次并进入 Judge，记录
可选 `final_answer_retry_count: 1`；第二次仍格式失败则终止该任务，不保存成功 QA，
不释放下游。输出截断直接拒绝，不进入格式重试；其他成功回答继续判分。

此规则统一用于全部 QA 模型、输入和 effort，包括主实验及两层 filter。判分错误
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

Description 的 grounded 表示遵循文字 context。Question-only 按 control 角色判定，
匹配 conflict reference 或无法确认的回答为 ambiguous，不产生 knowledge_trapped。
Judgment 保存 verdict、confidence、时间、Judge 模型、请求 ID 和适用的来源指纹。

报告分别统计 answer-level 和 video-level。每个 video/model/effort 取每题最新有效
记录；只有 grounded 而没有 trapped 的视频聚合为 grounded，只有 trapped 而没有
grounded 时聚合为 trapped，两者同时出现或两者均无则为 ambiguous。

```text
trapped_answer_rate = conflict trapped answers / all conflict answers
trapped_video_rate  = conflict trapped videos  / all conflict videos
```

分母均包括 ambiguous；无 conflict 样本时 rate 为 `null`。Control 的 grounded rate
也以全部对应样本为分母。Question-only 仅统计 answer-level control 指标，重复历史
按 `(timestamp, run_id)` 选择最新记录；不产生 video-level 指标。

## 数据结构

正式 case 位于 `dataset/cases/` 的可选 group 子目录，唯一受支持的 schema 为 4.0。
每个 case JSON 保存实验运行状态，视频文件独立存放；JSON 使用原子替换写回。

| 对象 | 主要内容 |
|---|---|
| case | `schema_version`、`case_id`、英文 `title`、`conflict_spec`、`questions`、`videos` |
| conflict_spec | `normal_fact_en`、`intended_video_fact_en` |
| question | `question_id`、`text_en`、两类 reference，可选 `question_only_results` |
| video | `video_id`、`role`、`seedance_prompt_en`、`task_id`、`status`、`local_path`、`human_review`、`qa_results` |
| description | `context_en`、可选 `context_prefix_en`、来源、来源 SHA-256、生成模型、时间和请求 ID |
| QA | `run_id`、时间、输入模式、问题 ID/正文、模型、effort、温度、`raw_answer`、`final_answer`、可选 usage/reasoning、`final_answer_retry_count: 1`、judgment |
| variant_context | 私有 facts/questions、可选标题、`matched_control_path` |
| 审核证据 | `video_observation`、`question_audit`、审核/资格状态和来源指纹 |

Description 仅属于 conflict 视频。Question-only 结果属于共享 question，不依附
视频，也不含 context 文本、作品名前缀或 based。共享 filter 直接使用 question-only
和 control 的权威回答；私有 filter 保存在私有题目的 `filter_results`。

Video/description 结果记录布尔 `based`。仅 Fairy video 额外记录布尔
`work_title_prefix`；description 不得保存此字段，其他组的视频忽略历史 prefix 值。
容器内去重键为：

```text
question_only: input + question_id + model + thinking_effort
video/description: input + question_id + model + thinking_effort + based
Fairy video: input + question_id + model + thinking_effort + based + work_title_prefix
```

旧 question ID、`video_grounded`、旧 baseline 字段及旧哈希字段兼容读取，不批量迁移。
`video_grounded` 解释为 grounded，缺失 based 解释为 false，Gemini medium effort
解释为 default。Filter 读取新字段优先，否则读取 baseline 别名；私有新旧容器共同
查找最新记录，续跑在原容器更新。命名变化不改变指纹算法或版本。

## 来源与过期规则

视频状态不能由文件存在推断为 ready。数学组的 QA 和汇总默认只选 qualified 范围，
还要求 ready、未被拒绝、无待重新审核资格；conflict 需 verified。历史 control
pending 审核状态保留为审计警告，不自动视为 verified。视频重新生成后必须重新
审核；需要审核观察时，没有有效 observation 不得把生成意图当作实际画面证据。

问题审核回执记录实际模型、时间、请求 ID、逐项检查和 scope 指纹；问题非空不
等于已通过独立审题。已入库变体的 `dataset/variant_cases` JSON 是历史来源快照，
`canonical_case_path` 指向正式数据，不能用于重新生成或删除正式视频。

QA 新鲜度绑定实际问题、视频文件 SHA-256 或 description 文本；Judgment 进一步
绑定最终答案、参考答案、事实、角色和 QA 来源。Filter 指纹绑定问题内容、参考
答案、事实、scope，以及 control 的路径、文件 SHA-256 和 prefix 条件。手工替换
同路径视频、修改题目/参考或文字 context 后，过期结果不会用于完成判断和统计。

无来源指纹的历史数学 QA 不能作为有效结果；旧 question-only 回答无 filter 来源
指纹时不能直接作为 filter 通过依据。旧 control QA 仅在问题、条件和来源检查均
一致时复用。旧 `context_sha256` / `video_sha256` 字段可读取，但不作为去重键或
独立统计条件；当前来源检查使用 input/filter 指纹。

Pipeline 重建问题时清理受影响的视频 QA，替换共享问题时清除其 question-only
历史；重建 description 只清理对应 description QA。显式重新生成 ready 视频会
清除其全部 QA、description 和审核观察，新任务提交也清空旧 description/观察。
删除或重建视频不影响独立 question-only 回答。旧 QA 没有 final_answer，或旧 Fairy
video 缺少 prefix 元数据时，须按 [pipeline.md](pipeline.md#历史数据兼容) 处理。

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

文字请求不包含视频或视频采样参数。主实验和两层 filter 使用相同 QA 模型配置，
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
| `result_rules.py` / `selection.py` / `filters.py` | 结果条件与去重、执行范围、逐题双层筛选 |
| `qa.py` / `qa_diagnostics.py` | 单次模型请求、回答解析、本次运行诊断 |
| `task_planning.py` / `task_execution.py` / `media_cache.py` | 任务身份与依赖规划、请求执行与结果合并、媒体准备与缓存 |
| `scheduler.py` / `runtime.py` | 调度、认领、额度准入、退避和进度；同机进程协调与锁 |
| `evaluation.py` / `reporting.py` | 执行预检、force 清理与完成计数；快照汇总与报告 |
| `evidence.py` / `integrity.py` / `audit.py` | 画面证据、来源新鲜度、离线结构审核 |
| `transport.py` | HTTP、凭据保护及其他阶段使用的限流重试 |

QA 单请求失败直接向调度器抛出异常，由调度器统一决定重试、限流和失败处理。
每条 QA 保存后即可判分，每层 filter 通过后释放下游。完整协调实现约定仅在
[concurrency.md](concurrency.md) 维护。独立对比解码实验见
[scripts/mcd_v1/README.md](scripts/mcd_v1/README.md)。
