# 方法 v1：视频 / 纯文本对比解码

独立实验入口，支持单题对比和小规模配对批量试跑。命令从仓库根目录执行。
GPU 推理使用 Chenmd 的独立环境；单元测试可在安装了 PyTorch 的 CPU 环境运行。

## 方法

每一步使用同一个 Cosmos 模型计算：

```text
score(token) = log p(token | 视频, 问题, 已生成文字)
             - lambda * log p(token | 问题, 已生成文字)
```

选出最高分 token 后，下一步两路都使用这个相同的生成历史。
使用的是对数概率，不是直接相减概率，也不是对两段完整回答做处理。
本版严格使用上面的 lambda 公式，不使用 (1 + gamma) log p_video - gamma log p_text。

- 默认 --lambda 0.5；设为 0 就是普通 greedy 视频解码。
- 默认 --beta 0.1：只允许视频概率不低于最高视频概率十分之一的 token。
  设为 --beta 0 可关闭这个限制，单独试原公式。
- 关闭 thinking：复用已有的“不要使用 think 标签”提示词；这不是对内部推理的保证。
- 两路使用完全一样的文字提示，只移除视频。不会向模型传入答案或人工描述。
- 视频分支使用原生 generate 和缓存；纯文本分支每步重算完整文本前缀，暂不加缓存。
  因此比普通推理慢，适合先试短回答。两路轮流执行时会隔离 Cosmos 的 RoPE 位置状态。

## 在 Chenmd 准备环境

在服务器项目根目录执行。使用独立 Python 环境，先安装适合服务器 CUDA 的
PyTorch/torchvision，再安装其余依赖；无需启动 vLLM HTTP 服务。

```bash
python -m pip install -r scripts/mcd_v1/requirements.txt
python scripts/mcd_v1/test_mcd_v1.py
```

依赖目标为 Transformers 5.11.0 的 Cosmos Reasoner 实现。已有服务器单题与批量结果，
但后续代码修改仍需重新验收。
服务器首次运行应先用短视频、小输出预算。模型默认是 nvidia/Cosmos3-Nano，
也可用 --model /path/to/local/checkpoint 指定已下载的权重。
--revision <commit> 可固定远端模型和 processor 版本。

## 直接试一个视频

```bash
python scripts/mcd_v1/run_mcd_v1.py \
  --video /absolute/path/to/video.mp4 \
  --question "What happens to the object in the video?" \
  --lambda 0.5 \
  --beta 0.1 \
  --compare-baseline
```

--compare-baseline 会用同一模型、同一视频输入分别运行普通解码和 v1，
直接打印两份回答。默认单 GPU cuda:0、BF16、4 fps、最多 256 个新 token。
可用 --device cuda:1、--dtype float16、--max-new-tokens 128 调整。
GPU 必须有足够空闲显存，脚本不会停止服务器上的其他服务。

## 使用当前项目的一道题

```bash
python scripts/mcd_v1/run_mcd_v1.py \
  --case dataset/cases/classic_physics_chemistry_experiments/acid_indicator_turns_blue.json \
  --video-id v001 \
  --question-id q001_implicit \
  --lambda 0.5 \
  --compare-baseline
```

这个例子只是选择已有素材，不代表该素材已经通过人工审核。
脚本仅读取对应题目和视频路径；有私有变体题目时，使用该变体自己的题目。
--work-title "..." 可选，用于给两路同时加作品标题前缀。

先将上述命令的 --lambda 改为 0，并保留 --compare-baseline：
输出 JSON 的 lambda_zero_matches 应为 true。
随后分别试 0.1、0.3、0.5，先看哪些题改善、哪些题变差。

## 结果在哪里

默认生成独立文件 results/mcd_v1/<时间和随机编号>.json，也可以
用 --output results/mcd_v1/my_trial.json 指定一个尚不存在的文件。

结果包含普通 / v1 回答、lambda/beta、问题和提示词、模型版本、token 序列、
耗时、截断和解析状态。输出达到长度上限或缺少项目要求的 Final answer: 行时，
仍保留原始回答，但标明异常并返回非零退出码；不会把异常静默算成成功。

原 case JSON 和历史 QA 结果不会被修改。此版本不做双 baseline 筛选、不调用
在线裁判、不汇总准确率；先供人工试效果。旧 vLLM 回答不能直接用来证明 CD 改善，
请优先比较本脚本同一次运行中的普通解码与 v1。

模型加载 / 视频预处理错误直接显示 traceback；生成阶段错误会写入结果 JSON。
基础检查通过也不代表真实 GPU 和视频推理已验证，服务器上的首次试跑仍是必要检查。


## 答案解析修复

末尾的 Final answer: 即使没有单独换行也可以提取，结果保留 format_warning。
缺失、空答案、未闭合 think 标签及无法唯一识别的行内标记仍报解析错误。
截断回答继续标为 truncated；原始输出和 token 不修改。结果记录 answer_parser_version。
此兼容逻辑仅用于 MCD v1，不改变主评测流水线的严格解析器。

## Small paired batch pilot (server)

Entry: `scripts/mcd_v1/run_mcd_v1_batch.py`. It reuses one loaded model and runs sequentially.
The frozen `manifest.json` contains 5 historical Cosmos/no-thinking knowledge-trapped
conflict questions and 5 context-grounded conflict questions (seed 42), plus matched
normal controls using exactly the same question. The unit is video + question.
Controls with the same path and question are deduplicated. This first pilot excludes
variant contexts and requires one usable original-case control. Rejected videos are
excluded; pending human review is allowed and recorded. Historical runs with a
`based` instruction or work-title prefix are excluded. Historical judgments only
select the sample; they are not the new baseline. References never enter model prompts.

Prepare without loading a model:
```bash
python scripts/mcd_v1/run_mcd_v1_batch.py --prepare-only --output-dir results/mcd_v1/pilot_10_v2
```

Run the new frozen list:
```bash
python -u scripts/mcd_v1/run_mcd_v1_batch.py \
  --output-dir results/mcd_v1/pilot_10_v2 \
  --model /cache/huggingface/hub/models--nvidia--Cosmos3-Nano/snapshots/e59a53c25979a090fa8706c9acc0c254a6e89b92 \
  --lambda 0.5 --beta 0.1 --fps 4 --max-new-tokens 256 --device cuda:0
```

Each item writes its own JSON containing fresh baseline and CD answers, raw text,
token IDs, timings, parse status and generation settings. `report.md` and
`report.json` refresh after every item. `ok` means generation and answer extraction
worked, not correctness. Review answers against the actual videos; this balanced,
small sample cannot estimate overall dataset accuracy.

Repeat the identical command after interruption to skip existing result files.
Existing failed/truncated results are also preserved and reported as failures, not
silently retried. To retry a failed item after investigating it, move that item's
JSON outside the output directory, then repeat the command. A model, parameter,
code or manifest change requires a new output directory. The code fingerprint includes
shared prompt and path helpers. Existing item results without `config.json` are refused.
To keep the same sample
in a new experiment, copy only `manifest.json` into the new directory before running.
Do not run two processes against the same output directory. JSON results are published
atomically without overwriting; interruption before publication leaves only a temporary
file, which is ignored on resume. A failed `lambda_zero_matches` check is reported as failure.

Validation:
```bash
python -m unittest discover -s scripts/mcd_v1 -p 'test_mcd_v1*.py'
```

## 目录与验收范围

```text
scripts/mcd_v1/
├── run_mcd_v1.py        # 单题入口
├── run_mcd_v1_batch.py  # 冻结样本、配对与续跑
├── decoding.py         # 对比解码与 RoPE 状态隔离
├── storage.py          # 原子写入，禁止覆盖结果
├── test_mcd_v1.py
├── test_mcd_v1_batch.py
├── requirements.txt
└── README.md
```

共享题目提示词、case 路径约束仍复用 `scripts/vconflict_pipeline/`。
vLLM 服务脚本 `scripts/start_cosmos_vllm.sh`、`scripts/start_gemma4_vllm.sh`
继续供服务部署使用；MCD 入口直接调用 Transformers，不经过这些服务。
Gemma 启动脚本并不代表主流水线已接入 Gemma QA。

已有 `pilot_10_v1` 记录包含 10 个 conflict 和 10 个 control：baseline 20/20
生成和解析成功，MCD 17/20 成功、2 个缺少答案标记、1 个截断。
另有单题 `lambda=0` token 一致性结果。所有入选视频均待人工审核，
这些结果只证明旧版本的推理流程跑通，不能证明方法有效或得出准确率。
本次目录整理及修复改变了代码指纹；原实验目录会拒绝续跑。
如需重跑相同样本，创建新目录并只复制原 `manifest.json`。

### Missing-marker recovery
Parser v2 preserves a nonempty, EOS-terminated response without a Final answer
marker as evaluation_answer, with status format_fallback and manual review required.
final_answer stays null and the original parse error is retained. Unclosed think
blocks, malformed markers and truncation are not recovered this way.
Recovery reports distinguish format_fallback from ok; neither implies correctness.
Original pilot results remain immutable. The pilot_10_v1_recovered directory is a
derived recovery report, not a resumable homogeneous batch: control_04 is rerun at
512 tokens on GPU 1, while other items retain their original generation.

### Fixed-pilot lambda sweep
Run from the repository root:
```bash
bash scripts/mcd_v1/run_lambda_sweep.sh
```
This uses the mcd-v1 environment directly, GPU 1, the original 20-item manifest,
lambda 0/0.1/0.2/0.3/0.5, beta 0.1, 4 fps, 512 tokens, thinking off.
Lambda 0 is greedy (negative branch skipped) and is shared across comparisons.
The model is loaded once; results are sequential. There are 100 generations.
Output: results/mcd_v1/lambda_sweep_20_v1, with report.md, report.json,
summary.json, frozen manifest/config and lambda_*/item.json raw results.
Raw single-run JSON uses the existing runs.mcd_v1 key even for lambda=0.
No correctness score is inferred from formatting status. Evaluate final answers,
explanations and normal-video regressions separately.

Repeat the same command to resume. Existing files, including failures/truncations,
are preserved. Inspect a failed file before moving it out of its lambda directory
to retry. Configuration/code changes require a new output directory. The output
directory is locked against concurrent runs. Prepare-only loads no model.
The prepared configuration binds GPU 1; to change GPU use a new output directory.
