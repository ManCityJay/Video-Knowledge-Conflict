# VCD 实验说明与用法

VCD 使用视频与纯问题两个分支进行对比解码，测量模型在视频证据与经典知识冲突时的回答。
实验读取主数据集 schema 4.0 case，只选择 conflict、ready 视频及其有效问题，
生成 QA 后通过共享 Judge 判分。结果写入独立目录，不写回源数据集。

入口：

- `scripts/vcd/run.py`：自选模型、样本和生成参数。
- `scripts/vcd/run_batch.py`：运行冻结的 small82 样本批次。

## 环境与模型

使用主实验的 vLLM 环境，依赖 `transformers==5.18.0`、`vllm==0.29.0`、PyTorch、
OpenCV 和 Pillow。模型从离线缓存加载，不下载权重、不执行 remote code。
需要判分时设置 `OPENROUTER_API_KEY`；`--qa-only` 和 `--summarize-only` 不请求 Judge。

```bash
conda activate vllm
export OPENROUTER_API_KEY=...
```

| 模型名称 | 模型 | 缓存 revision |
|---|---|---|
| qwen | Qwen/Qwen3.8-27B | main |
| cosmos | nvidia/Cosmos3-Nano | main |
| gemma | google/gemma-4-31B-it | 842da3794eaa0b77d5f08bae87a17459d91ff475 |

缓存根目录依次取 `HF_HUB_CACHE`、`$HF_HOME/hub`、`/cache/huggingface/hub`。
只解析所选模型；缓存缺失时报错。

两个入口统一使用以下参数：

| 参数 | 用法 |
|---|---|
| `--models qwen cosmos gemma` | 选择 1–3 个不同模型，按输入顺序排队；`run.py` 必填，批次默认选择全部三个 |
| `--gpus 0\|1\|all` | 选择物理 GPU，默认 `all`，表示 GPU 0、1 |
| `--disable-thinking` | 关闭 thinking，默认开启 |
| `--dry-run` | 只读展示模型顺序、首轮分卡、等待状态和实际配置，不创建输出 |

单模型在 `--gpus all` 时使用 GPU 0；显式选择 `--gpus 1` 时使用 GPU 1。
多模型按顺序分配空闲卡，每卡同时运行一个模型，同时空闲时优先 GPU 0。
单卡时串行；双卡时先启动两个，哪个先结束就在哪张卡启动下一个。
每个模型完成全部 QA/Judge 并退出后释放卡，普通失败继续运行剩余模型。
worker 按 GPU UUID 隔离设备，进程内固定使用 `cuda:0`。

## 单次运行

以下示例运行一个视频的一道题，并生成原生 greedy baseline 供比较：

```bash
python scripts/vcd/run.py \
  --models qwen --gpus 0 \
  --group classic_fairy_tale_film_conflicts \
  --case-id aladdin_lamp_rubbing_draws_genie_back_inside \
  --video-id v001 --question-id q001 \
  --output results/vcd/example --compare-baseline
```

`--dataset-dir` 默认 `dataset/cases`。`--group`、`--case-id`、`--video-id`、
`--question-id` 均可重复。不传 group 时选择主实验四组；不传其他筛选参数时纳入
所选组的全部可用任务。支持私有 `variant_context` 和 `question_ids` 关联，
显式指定不存在或未 ready 的视频会报错。

| 参数 | 默认值与说明 |
|---|---|
| `--output` | `results/vcd`，模型结果写入其下的 `<family>/` |
| `--alpha` | `0.5`，有限且不小于 0；设为 0 时跳过对比和 beta 过滤 |
| `--beta` | `0.05`，有限且在 `(0, 1]` 内 |
| `--based` | 默认关闭；开启后加入依据视频回答的指令 |
| `--compare-baseline` | 默认关闭；开启后独立生成和判分原生 greedy baseline |
| `--max-new-tokens` | `8192`，总输出预算，必须为正 |
| `--thinking-token-budget` | `6144`；开启 thinking 时必须为正且严格小于总输出预算 |
| `--dtype` | `bfloat16`；可选 `float16`、`float32` |
| `--qa-only` | 只生成本地 QA，后续可补 Judge |
| `--summarize-only` | 从已有结果重建报告，不加载模型、不检查 GPU、不请求 Judge |
| `--force-qa` | 重做当前条件匹配的 QA 和后续判分 |
| `--force-judge` | 保留已有 QA，重新判分；与 `--force-qa` 互斥 |

例如，依次运行三个模型并关闭 thinking：

```bash
python scripts/vcd/run.py \
  --models cosmos qwen gemma --gpus all \
  --disable-thinking --output results/vcd/no_thinking
```

## 解码与回答规则

CD 的视频和纯问题分支使用相同文字、模板参数及生成历史，仅视频输入不同。
两分支 logits 转为 FP32 后计算：

```text
scores = (1 + alpha) * video_logits - alpha * question_logits
cutoff = max(allowed_video_logits) + log(beta)
scores[allowed_video_logits < cutoff] = -inf
next_token = argmax(softmax(scores))
```

`allowed_video_logits` 排除禁止生成的 token。开启 thinking 时，达到 reasoning 预算后
强制关闭 reasoning，再继续生成答案。Baseline 使用相同输入、thinking 设置和回答恢复规则。

Prompt 复用主实验协议，要求最后一个非空行包含 `Final answer:` 和非空答案。
Fairy 使用当前有效标题第一个冒号前的作品名作为前缀，其他组不添加作品名前缀。
Cosmos/Gemma 保留 helpful-assistant system，Qwen 使用 user-only messages。

关闭 thinking 时，Cosmos 去掉推理格式指令，并动态解析 tokenizer 的 `<think>`、
`</think>` token ID，在 CD 和 baseline 生成中屏蔽；Gemma/Qwen 使用
`enable_thinking=false`，Qwen 不传 `reasoning_effort=xhigh`。
此时忽略 thinking 预算参数，有效预算记录为 `null`，总输出预算仍须为正。
开关同时作用于 CD 两分支、baseline、首次生成、答案解析和一次续写。

视频预处理沿用主实验：Cosmos/Qwen 由 processor 分别按 4 FPS / 1 FPS 采样；
Gemma 在 loader 按 1 FPS 采样，逐帧处理，每帧最多 70 个视觉 token。

首次截断或最终答案格式失败时，保留完整首次回答，追加 assistant 预填
`\nFinal answer:`，最多续写 256 tokens，不再设置 thinking 预算。
再次截断、格式失败或上下文不足即记录失败，不裁剪输入。
Judge 只读取提取的最终答案，不从 reasoning 推断答案。

## 结果、报告与续跑

单模型和多模型统一使用以下目录结构：

```text
results/vcd/example/
  queue_status.json
  qwen/
    config.json
    cases/<group>/<case_id>.json
    report.json
    report.md
    logs/<queue_run_id>_<phase>.log
  cosmos/ ...
  gemma/ ...
```

各模型独立保存配置、case、报告和日志，父目录记录模型顺序、排队状态、GPU、PID 和退出码。
旧单模型直接写入根目录的结果不自动搬迁或覆盖，应选择新的输出根目录。

普通续跑使用相同参数和输出目录，只补缺失、失败或过期的 QA/Judge。
问题、视频路径、prompt 条件、模型路径或生成参数变化时新增 QA，保留历史结果；
仅参考答案或事实变化时复用 QA、重做 Judge。设备、排队顺序和并发不影响 QA 缓存。
修改同路径权重后需使用 `--force-qa`。

开启 thinking 时记录 `thinking_effort=default`，关闭时为 `null`；两种模式不复用 QA。
改变 alpha/beta 只影响 CD 缓存，baseline 可复用。源视频按固定输入处理，不计算视频哈希。

```bash
# 只生成 QA
python scripts/vcd/run.py --models qwen --output results/vcd/qa_only --qa-only
# 使用相同选择范围和生成参数，省略 --qa-only 后补 Judge
python scripts/vcd/run.py --models qwen --output results/vcd/qa_only
# 使用相同选择范围和生成参数重建报告
python scripts/vcd/run.py --models qwen --output results/vcd/qa_only --summarize-only
```

Judge 默认并发 24 / RPM 20，OpenRouter 并发 24 / RPM 20，超时 600 秒，网络最多重试 4 次。
可通过 `--judge-concurrency`、`--judge-rpm`、`--openrouter-concurrency`、`--openrouter-rpm`、
`--timeout`、`--max-retries` 调整。`--max-token-log /path/truncation.jsonl` 只在真实截断时
追加保存任务、阶段、有效预算、回答文本和结束原因。

报告按方法、group 和总体汇总 answer-level / video-level 的 grounded、trapped 比例，
ambiguous 计入分母，空分母为 `null`。未完成任务及原因见 `report.json` 的 `incomplete_tasks`。
全部所选 QA/Judge 有效时退出 0，未完成返回 1，预检错误返回 2；QA-only 尚缺判分也返回 1。
SIGINT / SIGTERM 会停止派发、通知活动进程并等待退出，分别返回 130 / 143，随后可普通续跑。

## small82 批次

`run_batch.py` 固定每组可用 case 按 `case_id` 升序的前 25 / 25 / 25 / 7 个，
纳入全部 ready conflict 视频和关联有效问题。当前为 82 个 case、149 个视频、
每模型 177 条 QA，四组分别为 54 / 46 / 43 / 34 条。

批次默认选择 `qwen cosmos gemma`，GPU 默认 `all`；固定 `alpha=1`、`based=true`、
BF16、greedy、8192 / 6144 预算，不生成 baseline。beta 默认 `0.05`，可用 `--beta` 调整。
`--disable-thinking` 时有效 thinking 预算为 `null`。

```bash
# 只读预览，不创建输出、不检查 GPU、不加载模型、不请求 Judge
python scripts/vcd/run_batch.py \
  --models cosmos qwen gemma --gpus 1 --disable-thinking \
  --output-root results/vcd/small82_no_thinking --dry-run

# 先按队列完成所有所选模型的同一道题，全部 QA/Judge 成功后再进入完整批次
python scripts/vcd/run_batch.py \
  --models cosmos qwen gemma --gpus all --disable-thinking \
  --output-root results/vcd/small82_no_thinking --smoke-first

# 单模型续跑，读取同一冻结清单
python scripts/vcd/run_batch.py \
  --models gemma --gpus 1 --disable-thinking \
  --output-root results/vcd/small82_no_thinking

# 从已有结果重建报告
python scripts/vcd/run_batch.py \
  --disable-thinking --output-root results/vcd/small82_no_thinking --summarize-only
```

`--output-root` 默认 `results/vcd/small82_alpha1_based`。首次运行写入 `selection.json`，
保存分组、case、视频、问题、模型路径和生成配置；续跑核对冻结任务，不重新抽样。
未选模型不解析缓存，兼容清单允许补充 Cosmos。`--smoke-first` 中任一模型失败时不进入正式批次。

更换 beta、thinking 模式或其他冻结配置时使用独立输出目录。
`--selection-from /path/to/selection.json` 可继承另一批次的相同样本，使用本批生成参数，
不复制旧 QA/Judge。旧清单缺少 `thinking_effort` 时按开启解释；旧 beta=0.1 批次续跑
须显式传 `--beta 0.1`。

各模型仍写入 `<输出根目录>/<family>/`，父目录使用 `batch_status.json` 记录队列状态。
成功完成的批次每模型应有 `qa_valid=177`、`judge_valid=177`、`incomplete=0`。
