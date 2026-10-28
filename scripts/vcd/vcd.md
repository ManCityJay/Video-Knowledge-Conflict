# VCD：主实验协议的独立 QA / Judge

入口为 `scripts/vcd/run.py`。读取正式 schema 4.0 case，只选择 conflict、ready
视频及其有效问题，串行运行本地对比解码，再通过共享 Judge 队列判分。
结果写到独立目录，不写回数据集。默认不启动全量验收。

```bash
conda activate vllm  # transformers==5.18.0
export OPENROUTER_API_KEY=...
python scripts/vcd/run.py \
  --model-family qwen \
  --group classic_fairy_tale_film_conflicts \
  --case-id aladdin_lamp_rubbing_draws_genie_back_inside \
  --video-id v001 --question-id q001 \
  --output results/vcd/qwen --compare-baseline
```

## 模型与选择范围

`--model` 可省略，按 `--model-family` 离线解析本地 Hugging Face 缓存：

| family | 默认模型 | revision |
|---|---|---|
| qwen | Qwen/Qwen3.8-27B | 本地缓存的 main |
| cosmos | nvidia/Cosmos3-Nano | 本地缓存的 main |
| gemma | google/gemma-4-31B-it | 842da3794eaa0b77d5f08bae87a17459d91ff475 |

缓存根目录依次取 `HF_HUB_CACHE`、`$HF_HOME/hub`、`/cache/huggingface/hub`。
使用 `huggingface_hub.try_to_load_from_cache` 解析 revision，不下载、不按目录时间
选择版本；缓存缺失时，在写入输出前报错。可用 `--model /absolute/path/to/model`
覆盖默认路径，支持任意包含 `config.json` 的本地模型目录。
默认解析和显式路径都转成真实模型目录，用同一路径即可复用结果。
解析不导入 GPU 运行库，不加载模型，不遍历或哈希权重文件。

始终离线加载，不执行 remote code。默认 BF16、SDPA、`cuda:0`；可用 `--dtype`、
`--device` 覆盖。视频加载与 reasoning parser 复用同环境的主实验 vLLM 实现，
因此还需要 vLLM、OpenCV、Pillow。单设备加载不要求 accelerate；CPU 上加载权重
后转移到指定设备，需留出主机内存。

`--dataset-dir` 默认 `dataset/cases`。`--group`、`--case-id`、`--video-id`、
`--question-id` 均可重复。不传 group 时选择主实验四组；小样本应显式指定 group / case。
Conflict/ready 选择与主实验保持一致；问题关联直接复用 pipeline，包含私有
`variant_context`、question scope 和 `question_ids`。保留必要的审核记录存在性检查，
不计算主实验的审核来源哈希。不存在的关联或未 ready 的显式视频会报错，
不支持独立视频或 JSONL。

## 生成协议

- `--based` 默认关闭；开启时使用 pipeline 的依据视频回答指令。Fairy 自动使用当前
  有效标题第一个冒号前的作品名，其他组不加作品名前缀。
- 复用主实验 user prompt、`Final answer:` 要求和 Cosmos 推理格式提示。
  Cosmos/Gemma 使用 helpful-assistant system；Qwen 使用其原生模板。
  Gemma/Qwen 传 `enable_thinking=true`，Qwen 另传 `reasoning_effort=xhigh`。
- `--max-new-tokens` 默认 8192，`--thinking-token-budget` 默认 6144，后者须为正整数
  且严格小于前者。控制器按 token 序列识别 reasoning 边界，达到预算时强制关闭
  reasoning，随后继续生成答案，不强制 EOS。
- 视频使用主实验 `VideoBackend` 的 OpenCV 路径。Cosmos/Qwen 加载原帧，由 HF
  processor 按 4 FPS / 1 FPS 采样，保留原有帧数边界、空间预算、插值和网格。
  Gemma 在 loader 以 1 FPS 采样一次，无固定帧数上限；逐帧调用 image processor，
  每帧最多 70 视觉 token，使用主实验时间戳和视频占位 token。
  Gemma 保留逐帧图像处理路径，以匹配主实验的归一化。

CD 使用视频和内部纯问题两个分支：文字、模板参数和生成历史相同，仅移除视频。
每个分支独立保存 KV cache、position 状态和 RoPE deltas，均按最终选中 token 推进。
两分支 logits 先转为 FP32，按以下顺序执行原始 logits 对比及视频候选过滤：

```text
scores = (1 + alpha) * video_logits - alpha * question_logits
cutoff = max(video_logits) + log(beta)
scores[video_logits < cutoff] = -inf
scores = ReasoningControl(history, scores)
probabilities = softmax(scores)
next_token = argmax(probabilities)
```

公式和候选约束参考[官方 VCD 实现](https://github.com/DAMO-NLP-SG/VCD/blob/master/vcd_utils/vcd_sample.py)；
本实验在 softmax 后使用 greedy。ReasoningControl 在过滤后应用，预算触发时强制
生成结束标记，即使标记原先被候选约束排除。达到阈值的候选保留。

`--alpha` 默认 0.5，须有限且 >=0；`--beta` 默认 0.1，须有限且在 (0, 1] 内。
alpha=0 跳过对比和 beta 过滤，使用 FP32 视频 logits，再应用相同的控制、softmax
和 greedy。对比时要求两分支形状一致；拒绝非有限 logits、FP32 转换或计算溢出、
无有效候选和无效概率，不静默选出 token。alpha=0 不使用纯问题 logits。
新旧公式在精确数学下产生相同分布，浮点舍入可能不同，不要求答案必须变化。
`--compare-baseline` 默认关闭，开启后独立生成、保存和判分原生 greedy baseline。
Baseline 使用相同输入、thinking 控制和恢复协议。

## 最终答案和一次恢复

Gemma/Qwen 使用主实验 vLLM parser 分离 reasoning / 正文，Cosmos 沿用主实验
正文处理。最终答案直接复用 pipeline 解析：最后一个非空行最后一次大小写匹配的
`Final answer:` 之后必须有非空文本，不能用无标记的整段回答替代。

首次截断或格式失败共享一次恢复机会。完整首次回答（含独立 reasoning）追加为
assistant 预填，再加 `\nFinal answer:`；以 `continue_final_message=true`、
`add_generation_prompt=false`、`echo=false` 最多续写 256 tokens，移除 thinking budget。
CD 两分支追加相同 assistant 内容，重建各自状态，保留 alpha/beta；baseline 继续
使用原生 greedy。再次截断、格式失败或上下文不足即失败，不裁剪输入。
恢复上下文只在内存构造；产物保存合并文本及每阶段的预算、token 数、结束原因、
耗时和诊断，不再复制首次响应、预填和续写响应。

## 产物与增量执行

```text
results/vcd/qwen-compact/
  config.json
  cases/<group>/<case_id>.json
  report.json
  report.md
```

存储 schema 为 **3**。旧格式目录在任何写入前拒绝，必须使用新输出目录，不迁移、
不清理旧结果。生成协议版本独立于存储 schema：CD 使用 `vcd-main-experiment-3`，
原生 baseline 保持 `vcd-main-experiment-2`，已有 baseline 缓存键不变。
schema 3 目录中的旧 CD 记录保留，但不作为新协议结果复用或汇总。
配置的 `generation_protocols` 及报告各方法的 `protocol_version` 明确记录此对应关系。

`config.json` 的 `runs[]` 只追加运行 ID、时间、简短参数、选择范围、执行计数和
完成状态。每个 case 保留来源、标题、事实、问题和相关视频。
`videos[].qa_results[]` 保存成功 QA 的必要参数、一份 `raw_answer`、可选独立
`reasoning_content`、`final_answer` 和内嵌 `judgment`。续写成功的 reasoning 已在合并
文本中，不再独立保存。`phases[]` 保存阶段摘要；失败/中断保存在 `qa_attempts[]`。
Judge 失败仅在成功 QA 上保存简短 `judge_error`，下次可以只补 Judge。
不保存 token IDs、张量审计、processor 配置、渲染 prompt、完整 messages、重复响应、
模型目录清单、代码哈希或视频哈希。源数据已有结果不复制。

续跑只使用两个小型文本指纹：

- `qa_key`：数据源和任务身份、问题文本、视频路径、有效 prompt 条件、模型及其真实
  路径、dtype、输出/thinking 预算、method 和显式生成协议版本。仅 CD 包含 alpha/beta。
- `judge_key`：最终答案、问题、参考答案、事实、角色、Judge 模型和判分协议。

QA 命中还要求成功、正常结束和有效末行最终答案。参考答案/事实变化只使 Judge
失效；设备、并发、选择范围不使 QA 失效。视频视为固定，不计算视频哈希或检测
文件属性变化，也不在运行中重复校验来源。同路径权重原地修改后需 `--force-qa`；
生成行为变化需更新显式生成协议版本。不同 alpha/beta 组合及历史范围可以共存。

| 当前状态或变化 | 普通续跑行为 |
|---|---|
| QA / Judge 均有效 | 全部跳过，不加载 GPU 模型、不发 Judge 请求 |
| QA 有效，Judge 缺失 / 失败 / 过期 | 只补 Judge |
| 仅参考答案 / 判分事实变化 | 复用 QA，重新 Judge |
| 问题 / 视频路径 / prompt 条件 / 模型路径 / 生成条件变化 | 新增 QA，保留历史 |
| 改变 alpha/beta | 新增 CD，复用 baseline；改回旧值可复用旧组合 |
| CD 协议从 v2 升为 v3 | 保留旧 CD，重新生成当前 CD；复用条件匹配的 v2 baseline |
| 新开启 baseline 或扩展选题 | 只补缺失任务 |
| QA 失败 / 中断 | 重做未完成 QA |

任务开始、需要恢复、最终成功/失败和 Judge 完成时原子保存；并发 Judge 使用文件锁、
重读、合并后替换。同一输出目录只允许一个活动运行，锁随进程退出释放。
`--force-qa` 与 `--force-judge` 互斥，仅作用于当前条件：前者标记匹配 QA 失效后重做，
后者保留 QA 并清除当前判分；缺失 QA 保持未完成。

```bash
# 只生成本地 QA，留待后续判分（缺 Judge 时退出码为 1）
python scripts/vcd/run.py ... --qa-only
# 使用相同参数省略 --qa-only，自动补 Judge
python scripts/vcd/run.py ...
# 从精简 case 记录重建报告，不加载 GPU、不请求网络
python scripts/vcd/run.py ... --summarize-only
```

## Judge、日志和报告

Judge 复用 `vconflict_pipeline.judging` 的模型、prompt、schema 和判分校验，仅发送
最终答案。默认 Judge 并发 24 / RPM 20，OpenRouter 并发 24 / RPM 20，超时 600 秒，
网络最多重试 4 次。共享限流、SQLite 协调、429 cooldown 和退避保持主实验协议；
Judge 在独立队列执行，可与后续本地 QA 同时运行。

终端保留 QA/Judge 完成或失败、最终统计和报告位置，不显示逐 token 进度。
`--max-token-log /path/truncation.jsonl` 只在真实截断时创建并追加任务、阶段、预算、
回答文本和结束原因，立即 flush；不保存张量/token 审计。

报告覆盖为最近一次运行的参数和范围，按方法、group、总体汇总 answer-level /
video-level grounded 与 trapped，并列出状态、当次诊断计数和未完成任务简表。
不复制完整 config、回答正文或成功任务明细。ambiguous 计入分母，比例保留六位小数，
空分母为 null。视频聚合复用 pipeline；每题选择当前条件匹配的最新成功记录。
报告可删除后从 case 结果重建。全部选中 QA / Judge 有效返回 0，未完成返回 1，
预检错误返回 2，中断返回 130；QA-only 尚缺判分也返回 1。

## 验收

不新增或生成测试代码。使用静态检查、现有入口和独立小样本目录验证，不默认运行
全量实验，不额外发送外部 Judge 请求。小预算（如 256 / 64）属于独立生成条件，
不能作为默认 8192 / 6144 的结果复用。

检查三种默认路径、显式覆盖、环境变量、缺缓存预检、缓存复用、alpha/beta 共存、
参考变化、强制选项、恢复/失败、精简产物和报告重建。历史生成与判分验收证据保留在
`ACCEPTANCE.md`，其 schema 2 产物不会自动转换为本格式。
精简验收记录见 `COMPACT_ACCEPTANCE.md`，其中 v2 生成结果同样保留为历史证据。
本次原始 logits / softmax / greedy 变更的验收见 `LOGITS_ACCEPTANCE.md`。
