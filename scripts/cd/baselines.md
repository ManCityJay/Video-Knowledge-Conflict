# TCD / SEASON 用法

TCD 用相同文字提示的正负视频分支进行对比解码；SEASON 从同一份原始输入构造
空间噪声和时间干预分支，通过最后四层 full attention 的帧注意力分歧加权。
各方法独立实现输入准备、分支初始化、打分和状态推进，共享贪心选 token、停止、
thinking 控制、计时、batch 调度与结果保存。

## 环境与采样

使用主实验的离线环境：`transformers==5.18.0`、`vllm==0.29.0`、PyTorch、
torchvision、OpenCV 和 Pillow。模型标识与缓存解析方式见 [VCD](vcd/vcd.md#环境与模型)。
需要 Judge 时设置 `OPENROUTER_API_KEY`。

| 模型 | VCD 视频 / TCD 正分支 / SEASON 原视频 | TCD 负分支 |
|---|---:|---:|
| qwen | 1 fps | 0.5 fps |
| gemma | 1 fps | 0.5 fps |
| cosmos | 4 fps | 1 fps |

采样值集中定义于 `contrastive_common/sampling.py`，预处理、配置预览与指纹读取同一份
配置。`--positive-fps` 已移除，不能再统一覆盖所有模型。
保留 Qwen/Cosmos 原生 processor 的帧数上下限，以及 Gemma loader 的原生索引算法。
TCD/SEASON 从完整解码的源帧采样一次，后续处理器关闭重复采样。
VCD 的 Qwen/Cosmos 则将完整帧和原始 metadata 交给 processor 内部采样，
续写复用完整帧并重新经过同一路径，详见 [VCD](vcd/vcd.md#解码与回答规则)。
TCD 正负分支使用相同空间分辨率；
SEASON 的干预均从已采样的原始输入构造，不重新采样。答案续写复用首次采样缓存。
QA 的 `sampling` 审计记录各分支请求 FPS、源 FPS、原始帧索引、时间戳和采样帧数，
适用时另含处理器帧数边界与 `video_grid_thw`。

## 独立入口

```bash
python scripts/cd/tcd/run.py --models qwen cosmos gemma --gpus all --based
python scripts/cd/season/run.py --models qwen cosmos gemma --gpus all --based
```

每个入口固定对应方法，不接受切换方法。`--models` 选择 1–3 个不同模型。
默认 `batch-size=auto`、`max-batch-size=32`、based 关闭、执行 QA → Judge。
输出分别为 `results/tcd/<model>/` 和 `results/season/<model>/`；`--output` 覆盖方法结果根目录。
数据筛选、Judge 参数及生成预算与 [VCD](vcd/vcd.md#单次运行) 相同。

## 统一 baseline 入口

```bash
# 默认：三个模型、两种方法、batch 4、上限 4、based、QA-only
python scripts/cd/run_baselines.py --dry-run
python scripts/cd/run_baselines.py

# 显式选择模型、方法和参数
python scripts/cd/run_baselines.py --models cosmos --methods tcd --gpus 1 --no-based

# 运行 QA 与 Judge；或单独补 Judge / 重建报告
python scripts/cd/run_baselines.py --qa-judge
python scripts/cd/run_baselines.py --judge-only
python scripts/cd/run_baselines.py --summarize-only

# 启用 auto batch 与在线 autotune
python scripts/cd/run_baselines.py --batch-size auto --max-batch-size 32 --autotune-batch
```

统一入口直接构造 worker 配置，使用与独立入口相同的参数解析、校验和 FIFO GPU 队列，
不拼接 shell 命令。默认输出为 `results/baselines/<method>/<model>/`；
`--output` 覆盖包含方法目录的父目录。模型顺序优先，再按方法顺序排队。
默认 GPU 0、1，每卡同时一个 worker；其他任务等待空闲卡。单卡参数为 `--gpus 0` 或 `1`。

| 参数 | 默认值 / 行为 |
|---|---|
| `--models` | baseline 默认 `qwen cosmos gemma`；独立入口必填 |
| `--methods` | 仅 baseline 支持，默认 `tcd season` |
| `--batch-size` / `--max-batch-size` | baseline 为 `4` / `4`；独立入口为 `auto` / `32` |
| `--based` / `--no-based` | baseline 默认开启；独立入口默认关闭 |
| `--qa-only` / `--qa-judge` / `--judge-only` / `--summarize-only` | 互斥；baseline 默认 QA-only，独立入口默认 QA → Judge |
| `--max-new-tokens` / `--thinking-token-budget` | `8192` / `6144`；续写固定最多 256 tokens，移除 thinking 预算 |
| `--alpha` / `--beta` | `1.0` / `0.1`；beta 仅用于 VCD/TCD 的 plausibility mask |
| `--season-beta` / `--noise-step` / `--noise-seed` | `0.33` / `10` / `42` |
| `--disable-thinking` | 忽略 thinking 预算；各分支使用相同开关 |
| `--dry-run` | 只读展示实际 FPS、batch、GPU 分配与输出路径，不创建输出 |

`--force-qa` 重做当前匹配的 QA；`--force-judge` 保留 QA 并重新判分。
baseline 默认 QA-only，使用 `--force-judge` 时须显式指定 `--qa-judge`。

## 解码、batch 与计时

TCD 沿用 `(1 + alpha) * positive_logits - alpha * negative_logits` 和 beta plausibility mask；
SEASON 沿用原始三分支加权公式和空间噪声 / 时间同质化参数。
`alpha=0` 跳过负分支和干预、对比及 beta mask，保留单原始视频分支。
VCD 使用独立串行解码，batch 注册表与入口仅接受 TCD/SEASON。
TCD/SEASON 按视觉几何分桶、左 padding 后组成真正的 tensor batch。
OOM 或显存余量不足时拆分 batch，保留相同输入和预算；单条仍 OOM 则保存失败。
`--autotune-batch` 仅支持 `--batch-size auto`，复用既有的在线吞吐与显存观测逻辑。

首次截断或缺少合法末行 `Final answer:` 时，保留完整首次回答，追加 assistant 预填，
只续写一次；再次失败或上下文不足则记录失败。Greedy、thinking 预算和各方法原有公式不变。
Judge 仅使用提取的最终答案，报告统计方式见 [VCD](vcd/vcd.md#结果报告与续跑)。

每条 QA 记录准备和生成的服务延迟；batch 审计写入 `batches/<run_id>.jsonl`，
记录 wall time、有效 token、活跃比例和峰值显存。OOM 重试时间单独计入，
共享前向耗时不作为可相加的逐条 GPU 时间。`decode_live.json` 每 64 步更新进度，
在线 autotune 写入 `batch_tuning.json`，可用 `batch_control.json` 的 `batch_size` 调整边界处上限。

## 结果兼容与旧目录续跑

结果继续使用 schema 3、方法标识 `cd/tcd/season` 和原协议版本。
目录重构不改变 QA 指纹。TCD/SEASON 的实际正负 FPS 仍参与指纹；
采样配置相同的历史结果可以续用，配置不同的结果会新增 QA，不会误复用。
VCD 保留原有绑定字段与指纹；恢复串行解码和处理器内部采样不使历史结果失效，
新 VCD QA 不再写入显式采样审计。验证恢复后的生成路径时须使用独立输出目录。
历史数据不移动、不重写；`--output` 可指向已有结果的父目录：

```bash
# 旧结构：results/vcd/tcd_season_main_aligned/tcd/qwen/...
# 独立方法入口使用该方法目录作为根
python scripts/cd/tcd/run.py --models qwen --based \
  --output results/vcd/tcd_season_main_aligned/tcd --dry-run

# 统一入口使用包含 tcd/season 的父目录作为根
python scripts/cd/run_baselines.py \
  --output results/vcd/tcd_season_main_aligned --dry-run
```

原全模型 4 fps 结果中，Qwen/Gemma 与新配置不同，Cosmos 的 TCD 负分支也不同，
均按实际指纹决定复用。设备、batch、队列顺序和纯目录变化不影响 QA 复用。
QA-only 全部 QA 有效即可成功，Judge 缺失单独报告；完整模式需 QA/Judge 全部有效。
不完整返回 1，预检错误返回 2，SIGINT / SIGTERM 返回 130 / 143。
