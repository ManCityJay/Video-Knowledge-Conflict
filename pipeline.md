# Pipeline 使用说明

本文说明当前 CLI 的运行方法；实验条件、来源规则和指标定义见
[plan.md](plan.md)，并发协调和故障恢复见 [concurrency.md](concurrency.md)。

## 环境与凭据

从仓库根目录使用 Python 3.10 或更新版本运行。按所用服务安装依赖：

```bash
# 云端 Qwen QA（qwen3.8-max）
python -m pip install -U "dashscope>=1.24.6"
# Seedance 视频生成
python -m pip install volcengine-python-sdk[ark]
# 数学变体 authoring 的参考帧处理
python -m pip install av Pillow
```

Author、questions、生成式 description 和 Judge 使用 `OPENROUTER_API_KEY`；
Seedance 使用 `ARK_API_KEY`；云端 Qwen QA 使用 `DASHSCOPE_API_KEY`；Kimi QA 使用
`MOONSHOT_API_KEY`。本地 QA 不需要模型 API key，但 Judge 仍需 OpenRouter 凭据。
PowerShell 配置示例：

```powershell
$env:OPENROUTER_API_KEY = "<key>"
$env:ARK_API_KEY = "<key>"
$env:DASHSCOPE_API_KEY = "<key>"
$env:MOONSHOT_API_KEY = "<key>"
```

可选服务地址：

| 环境变量 | 默认值 |
|---|---|
| `ARK_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` |
| `DASHSCOPE_BASE_HTTP_API_URL` | `https://dashscope.aliyuncs.com/api/v1` |
| `MOONSHOT_BASE_URL` | `https://api.moonshot.cn/v1` |
| `COSMOS_BASE_URL` | `http://127.0.0.1:8000/v1` |
| `GEMMA_BASE_URL` | `http://127.0.0.1:8001/v1` |
| `QWEN38_BASE_URL` | `http://127.0.0.1:8002/v1` |

云端 Qwen 地址须使用 HTTPS。下文命令采用 Bash 换行语法；PowerShell 中可写成单行。

## 入口与执行顺序

```bash
python scripts/pipeline.py <stage> [参数]
```

可用阶段：`author`、`questions`、`description`、`generate`、
`delete`、`qa-judge`、`summarize`、`audit`。各阶段显式执行，没有自动串联入口。
参数用法统一查询本文，并发协调与恢复细节见 `concurrency.md`。

常用视频实验顺序：

```bash
python scripts/pipeline.py author --group classic_fairy_tale_film_conflicts
python scripts/pipeline.py questions --group classic_fairy_tale_film_conflicts
python scripts/pipeline.py generate --group classic_fairy_tale_film_conflicts
# 需要实际画面证据的视频须补齐与当前文件绑定的 video_observation。
python scripts/pipeline.py qa-judge --group classic_fairy_tale_film_conflicts \
  --input video --qa-model qwen3.8-max --thinking-effort all
python scripts/pipeline.py summarize --group classic_fairy_tale_film_conflicts \
  --input video --qa-model qwen3.8-max --thinking-effort all
```

Control 视频以 `--input control` 独立执行 QA 和汇总；`--input video` 只执行
conflict。文字实验先运行 `description`，再以 `--input description` 执行 QA 和汇总。
文字实验只用文本，不依赖 control 视频。四种输入独立执行 QA → Judge，目标实验
不自动运行 question-only，也不要求其通过。独立 question-only 实验有有效问题后即可执行，
不依赖视频文件、视频状态或 description。

## 数据组、目录与范围

| 内容 | 使用 `--group <group>` 时的默认目录 |
|---|---|
| 源 Markdown | `dataset/source_cases/<group>/` |
| 正式 case JSON | `dataset/cases/<group>/` |
| Seedance 视频 | `videos/seedance/<group>/<case_id>/` |
| 汇总和报告 | `results/<group>/<model>/` |

省略 group 时省去该层目录，结果仍位于 `results/<model>/`。数学组与其他组统一使用
`videos/seedance/<group>/<case_id>/`；qualified/unqualified 目录已退役。

- `author --source-dir`、`--output-dir` 指定源和目标根目录，group 会追加在根目录下。
- 其他阶段的 `--dataset-dir` 指定 case 根目录，也会追加 group。
- `--case-id` 可重复传入；支持视频或问题选择的阶段可用 `--video-id`、
  `--question-id` 缩小范围。`summarize` 只支持 case 范围，不支持这两个选项。
- `qa-judge` / `summarize`：所有组默认 `--video-scope all`。旧命令中的
  `--video-scope qualified` 应删除或改为 `all`；`all` 仅保留入口兼容，内部按
  `--input` 选择角色。所选角色不存在时为零目标；显式选择其他角色或未就绪
  的视频时报错。Description 只检查 conflict 文本及其来源是否有效。
- 删除视频或问题时只选择一个 case，
  `delete --all` 则可选择同组多个完整 case。

## 数据准备、生成、画面证据与删除

源 case 需预先按每个 case 一份 Markdown 准备，文件名为合法 case ID，首行使用
`### 标题`。Author 默认跳过已有 JSON；`--force` 可覆盖可写 case，仍禁止覆盖
带 `canonical_case_path` 的历史来源快照。新增数学变体可使用独立 `--output-dir`。
数学参考视频要求 conflict、ready、文件存在，继续校验实际画面证据及原有排序。

```bash
python scripts/pipeline.py author --group classic_fairy_tale_film_conflicts \
  --case-workers 2 --openrouter-workers 2 --openrouter-rpm 20
python scripts/pipeline.py questions --group classic_fairy_tale_film_conflicts
python scripts/pipeline.py description --group classic_fairy_tale_film_conflicts
```

`questions` 默认补齐空的问题上下文；`--video-id` 选择视频实际使用的共享或私有
上下文。`--force` 重新生成选中上下文，问题发生变化时清除对应视频 QA 和被替换
共享问题的 question-only 历史。`description` 默认跳过来源仍有效的 context，
`--force` 重写选中的 conflict context 并清理其 description QA。有审核观察时直接
使用观察中的事实文本。

数学题只审不改或保留 ID 修复：

```bash
python scripts/pipeline.py questions --group mathematics_algorithm_conflicts \
  --case-id queue_removes_newest_item_first --video-id v008 --audit-only
python scripts/pipeline.py questions --group mathematics_algorithm_conflicts \
  --case-id queue_removes_newest_item_first --video-id v008 --repair-variant-context
```

`--audit-only` 调用 Luna 并保存审题回执，不与 `--force` 或
`--repair-variant-context` 组合。修复模式仅支持数学组，也不与 `--force` 组合。
两种模式都会保存操作前备份到 `backups/math_question_context_<时间>/`。

生成或续跑视频：

```bash
python scripts/pipeline.py generate --group classic_fairy_tale_film_conflicts \
  --seedance-workers 3 --seedance-total-workers 6
python scripts/pipeline.py generate --group classic_fairy_tale_film_conflicts \
  --case-id alice_drink_makes_her_grow --video-id v001 --regenerate
```

默认 5 秒、720p、`--ratio adaptive`；可用 `--duration`、`--resolution`、`--ratio`
覆盖。`--model` 默认取 `SEEDANCE_MODEL` 环境变量或仓库配置，`--base-url` 可覆盖
Ark 地址。每 30 秒轮询，最多 120 次；用 `--poll-interval` 和 `--max-polls` 调整。
失败任务须加 `--retry-failed`；submitted 任务保留 task ID，重复命令可继续轮询或下载。

`--regenerate` 重置 ready 视频，清除其 description、审核观察和全部 QA。
新提交的生成任务也会清空旧 description 和观察；成功下载后标为 ready。
需要画面证据的视频（包括新生成的数学 conflict 视频）须补齐与当前文件 SHA-256
绑定的 `video_observation`。保留 `require_video_observation`、独立模型
`question_audit` 和来源新鲜度检查；人工状态登记及 `review` 子命令已移除。
视频文件存在不会自动将状态升级为 ready；默认跳过未就绪视频，显式选择时报错。
ready 视频文件缺失时，在 QA 模型请求前报错。

删除内容示例：

```bash
python scripts/pipeline.py delete --group classic_fairy_tale_film_conflicts \
  --case-id alice_drink_makes_her_grow --video-id v001 --question-id q001
python scripts/pipeline.py delete --group classic_fairy_tale_film_conflicts \
  --case-id aladdin_lamp_rubbing_draws_genie_back_inside --video-id control
python scripts/pipeline.py delete --group classic_fairy_tale_film_conflicts \
  --case-id alice_drink_makes_her_grow --case-id alice_eat_cake_makes_her_shrink --all
```

视频和问题 ID 可重复。可单独删除指定的 control 或 conflict，且至少保留一个
conflict；删除后可没有 control，并允许仅剩一个 conflict，无须新增筛选标记。
删除视频会移除其整个 JSON 条目，包括 prompt、description、全部 video/description
QA 及其中的 Judge 历史；保留其他视频的历史、共享问题及其 question-only 结果。
删除问题会清除该 ID 的共享/私有题目和 QA/Judge、question-only/filter 历史，
并同步清理视频 `question_ids` 关联。带人工裁剪备份的 case 保留 schema 例外。
任一指定 ID 不存在时
不会执行删除。`--all` 不与视频/问题选择混用：先预检全部选中 case 的 JSON 和视频
路径，再删除 JSON 及其中记录的视频文件，仅移除空父目录，保留目录内其他资产。
本地视频缺失不阻止删除 JSON。源 Markdown、远端任务和结果报告均保留；删除后
重新运行 `summarize`。

## 模型服务与 QA/Judge

| `--qa-model` | `--thinking-effort` | QA / 共享 QA 服务默认并发 | 输出上限 |
|---|---|---|---|
| `gemini` | `default` | 24 / 24 | 服务配置 |
| `qwen3.8-max` | `none`、`default` | 24 / 24 | 服务配置 |
| `kimi-k3` | `default` | 24 / 24 | 服务配置 |
| `cosmos3-nano` | `none`、`default` | 8 / 8 | `--cosmos-max-tokens 8192` |
| `gemma4` | `none`、`default` | 4 / 4 | `--gemma-max-tokens 8192` |
| `qwen3.8-27b` | `none`、`default` | 1 / 1 | `--qwen38-max-tokens 8192` |

省略 effort 使用 `default`；`all` 执行模型支持的全部 effort，也可重复指定该选项。
模型 ID、温度和视频采样协议见 [plan.md](plan.md#模型配置与采样协议)。

Cosmos `none` 在四种输入的请求顶层发送
`"bad_words": ["<think>", "</think>"]`，由服务端在生成阶段屏蔽标签；提示词仅保留
原问题、适用的输入条件和 `Final answer:` 格式要求，移除原有不使用 think 标签的
提示句。屏蔽标签不保证没有推理文字。`default` 保持原推理提示且不发送 `bad_words`。
历史结果仍可复用；需要采用新协议重新实验时，使用现有 `--force-qa`。

三个本地模型默认总输出预算为 8192（含推理和正文），默认
`--thinking-token-budget 6144`。该正整数参数仅在本地实际 effort 为 `default` 时作为
顶层 `thinking_token_budget` 发送，并须严格小于所选模型的 `--*-max-tokens`；
`none` 不发送，`all` 按每个任务的 effort 处理，云端模型忽略该预算。
6144 是本实验的工程预算，不是官方推荐值。Gemma 客户端默认从 2048 调整到 8192，
Qwen27B 从 32768 调整到 8192，与默认服务端输出上限一致。

本地服务启动脚本在 Linux/Bash、Conda 和兼容的 vLLM 环境中运行：

```bash
bash scripts/start_cosmos_vllm.sh
bash scripts/start_gemma4_vllm.sh
bash scripts/start_qwen38_vllm.sh
# Gemma 仅查看启动命令
DRY_RUN=1 bash scripts/start_gemma4_vllm.sh
# Qwen27B dry-run 无需激活 Conda 或安装 vLLM
DRY_RUN=1 bash scripts/start_qwen38_vllm.sh
# 提高客户端总预算时，同步提高对应服务的上限并重启
MAX_OUTPUT_TOKENS=16384 bash scripts/start_qwen38_vllm.sh
```

三个启动脚本均接受 `MAX_OUTPUT_TOKENS` 正整数，默认 8192，通过
`--override-generation-config` 设置服务端输出上限。提高客户端 `--*-max-tokens` 时，
也需提高此上限，并保证输入 token（含视频）与输出能放入服务端上下文。
本次更新增加 `--reasoning-config`，必须用更新后的脚本重启已有服务。
Cosmos 和 Qwen 使用 `<think>` / `</think>`，Gemma 使用
`<|channel>thought\n` / `<channel|>`（`\n` 是实际换行）；达到推理预算时只注入结束
标记，继续自然生成正文。Cosmos 保留无 parser 模式，Gemma/Qwen 分别保留
`gemma4` / `qwen3` parser；具体配置和 vLLM 0.29.0 实现依据见
[plan.md](plan.md#模型配置与采样协议)。

Cosmos 默认激活 `vllm` 环境、GPU 0 单卡、BF16、端口 8000、`MAX_NUM_SEQS=4`。
`VIDEO_ROOT` 默认仓库 `videos/`，`TENSOR_PARALLEL_SIZE`、`CUDA_VISIBLE_DEVICES`、
`MAX_NUM_SEQS`、`GPU_MEMORY_UTILIZATION`、`VLLM_HOST`、`VLLM_PORT` 可覆盖。
无需添加模型架构覆盖参数。

Gemma 默认 `vllm` 环境、GPU 1 单卡（`CUDA_VISIBLE_DEVICES=1`、`TENSOR_PARALLEL_SIZE=1`）、
BF16、32K 上下文、`MAX_NUM_SEQS=2`、
端口 8001。`GEMMA_MODEL`、`GEMMA_REVISION`、`GEMMA_CONDA_ENV` 可覆盖模型和环境；
其余部署参数与 Cosmos 同名，另支持 `MAX_MODEL_LEN`、`MEDIA_ROOT` 和 `TEXT_ONLY=1`。

Qwen27B 默认 `vllm` 环境、GPU 0 单卡、BF16、65536 上下文、`MAX_NUM_SEQS=1`、
端口 8002，加载视觉模块并启用 `qwen3` reasoning parser。`QWEN_MODEL` 可指定已下载
模型目录，`QWEN_CONDA_ENV` 覆盖 Conda 环境；`TENSOR_PARALLEL_SIZE`、
`CUDA_VISIBLE_DEVICES`、`MAX_MODEL_LEN`、`MAX_NUM_SEQS`、`GPU_MEMORY_UTILIZATION`、
`VLLM_HOST`、`VLLM_PORT`、`MEDIA_ROOT`、`ENFORCE_EAGER` 均可覆盖。
默认 `HF_HUB_OFFLINE=1`，也可覆盖 `HF_HOME` / `HF_HUB_CACHE`；默认只从已有缓存
加载。所有脚本默认 `HF_HOME=/cache/huggingface`，接受追加的 vLLM 参数。

视频必须是服务端可读且位于允许媒体目录内的 MP4。服务端口改变后同步配置
`COSMOS_BASE_URL` / `GEMMA_BASE_URL` / `QWEN38_BASE_URL`；Qwen27B 默认
`http://127.0.0.1:8002/v1`。预检从 `/v1/models` 获取实际模型 ID，持久化实验 ID
始终为 `Qwen/Qwen3.8-27B`。整条 pipeline 与 vLLM 在同一服务器运行。
Description 与独立 question-only 实验都只用文本，`TEXT_ONLY=1` 同时适用于二者。

Gemma、本地 Qwen27B 和云端 Qwen Max 的 video/control 均按 1 FPS 采样。
Gemma 客户端与启动脚本设置 `media_io_kwargs.video.fps=1`、`num_frames=-1`，
由加载器采样一次，取消固定 32 帧上限；本地 Qwen27B 加载器保留原始帧，
客户端与启动脚本设置 `mm_processor_kwargs.fps=1`，由模型处理器采样一次，
保留原有帧数边界；Qwen Max 视频内容项设置 `fps=1`。
Description 和 question-only 请求不携带视频采样参数。完整参数见
[plan.md](plan.md#模型配置与采样协议)。更新服务端采样默认值需要重启对应服务；
已有历史结果仍可复用，需要统一采样协议时使用 `--force-qa` 重跑所选范围。

```bash
python scripts/pipeline.py qa-judge --group classic_fairy_tale_film_conflicts \
  --input video --qa-model gemma4 --thinking-effort all
python scripts/pipeline.py qa-judge --group classic_fairy_tale_film_conflicts \
  --input description --qa-model qwen3.8-max --thinking-effort all
python scripts/pipeline.py qa-judge --group real_world_commonsense_conflicts \
  --input question_only --qa-model qwen3.8-max --thinking-effort all
# 本地模型显式预算示例；也适用于 control、description、question_only
python scripts/pipeline.py qa-judge --group real_world_commonsense_conflicts \
  --input video --qa-model qwen3.8-27b --thinking-effort all \
  --qwen38-max-tokens 8192 --thinking-token-budget 6144
```

`--input` 默认 `video`，执行与汇总使用相同的角色选择：

| `--input` | 目标 |
|---|---|
| `video` | conflict 视频及其有效问题 |
| `control` | control 视频及其有效问题 |
| `description` | conflict 文本 context 及其有效问题 |
| `question_only` | conflict 视频的有效问题，共享题按 scope 去重，私有题按视频隔离 |

视频的有效问题来自共享或私有上下文，并受可选 `question_ids` 约束。
独立 question-only 遍历 conflict 视频关联的有效问题，不要求视频文件存在或 ready。
共享题按 `(case scope, question_id)` 去重，私有题按 `(video ID, question_id)` 隔离，
两者均遵循 `question_ids`。共享结果写入 `question_only_results`，私有结果保留在
私有题目的 `filter_results`；存储位置、来源指纹和旧字段兼容规则不变。可用
`--question-id` 缩小范围，不能组合 `--video-id`、`--with-work-title-prefix` 或 `--based`。

Fairy video/control 可加 `--with-work-title-prefix`，作品名取标题第一个冒号前的部分。
Video/control/description 可加 `--based`，为目标 QA 加入中性的依据输入回答指令。
Based、prefix 条件分别续跑和汇总。Control 复用视频请求流程，结果仍记录为
`input_mode: video`，角色由所属视频区分；Judge 使用正常参考答案，不输出
`knowledge_trapped`。历史 control QA 可直接复用其有效结果。

```bash
python scripts/pipeline.py qa-judge --group classic_fairy_tale_film_conflicts \
  --input control --qa-model qwen3.8-max --thinking-effort all
python scripts/pipeline.py qa-judge --group classic_fairy_tale_film_conflicts \
  --input control --qa-model qwen3.8-max --thinking-effort all \
  --based --with-work-title-prefix
```

### 独立输入、续跑与 force

Video、control 和 description 直接执行目标 QA → Judge。Question-only 缺失、过期、
未判分、通过或判错均不影响目标执行。各组视频请求只按角色和 ready 状态选择，
并检查文件和观察是否过期；不另加数学组的人工审核资格门槛。

需要 question-only 指标或筛选报告时，显式执行独立实验：

```bash
python scripts/pipeline.py qa-judge --group classic_fairy_tale_film_conflicts \
  --input question_only --qa-model qwen3.8-max --thinking-effort all
python scripts/pipeline.py summarize --group classic_fairy_tale_film_conflicts \
  --input question_only --qa-model qwen3.8-max --thinking-effort all
```

`qa-judge --filter-only` 已删除，改用 `--input question_only`。正常重复运行复用
所选输入的有效结果，缺少判定时只补 Judge；请求中断后可用相同命令续跑。
已判错的 question-only 不会自动反复尝试到答对。

- `--force-qa` 清理所选输入、模型、effort 和 based/prefix 条件的 QA/Judge，再执行。
- `--force-judge` 保留目标回答，只清理匹配 judgment 并重判。
- 两者互斥，video/control/description force 不先运行或清理 question-only；
  所有选中题目均参与清理，不受 question-only 判定影响，其他输入和 based/prefix 条件保留。
- `--input question_only --force-qa` / `--force-judge` 只清理所选 conflict 有效共享/私有
  题目中对应模型和 effort 的结果/判定。新判定仅影响随后显式选择的筛选报告。

Force 先独占全部所选 case；冲突时报错。对所选输入预检并统一清理，
全部清理成功后才开始 QA/Judge 请求。清理中断可能已有部分文件
写回。完整协调和恢复说明见 [concurrency.md](concurrency.md#force)。

使用 `--qa-concurrency`、`--judge-concurrency` 调整当前命令并发，
`--qa-service-concurrency` 调整共享 QA 服务上限。云端 QA、Judge 以及 OpenRouter
默认 20 RPM，本地 QA 默认 0 RPM；用 `--qa-rpm`、`--judge-rpm`、
`--openrouter-concurrency` 和 `--openrouter-rpm` 配置实际配额。0 RPM 表示关闭该项
速率限制，增加并发不能突破 RPM。具体适用范围见 [concurrency.md](concurrency.md#参数)。
Author/questions/description 使用 `--case-workers`、`--openrouter-workers` 和
`--openrouter-rpm`；generate 使用 `--case-workers`、每 case 的 `--seedance-workers`
及全命令的 `--seedance-total-workers`。

### 历史数据兼容

Schema 只接受 4.0。旧 question ID、`video_grounded`、baseline filter 字段及平铺
报告可保留；旧 `based` 缺失按 false，Gemini `medium` effort 按 default。
历史 `human_review`、`qualification_pending` 字段忽略，不校验、不批量改写，
新建或生成视频不再写入这些状态。
旧 `QWEN_BASE_URL` 仍可读取，`/compatible-mode/v1` 后缀会转换为 `/api/v1`。

新保存的本地 QA 记录增加实际请求的 `max_tokens` 和 `thinking_token_budget`，未启用
thinking 或执行答案续写时后者为 `null`。本地续写成功的记录可包含
`final_answer_continuation` 审计对象，顶层预算、usage 和请求 ID 对应第二次请求。
历史记录不补写预算或续写审计；去重、任务身份、来源指纹和复用规则不变，因此
旧、新协议结果可能同时被复用和汇总，修改预算或续写协议本身不会触发重跑。
要统一重跑，显式使用对应输入、模型和 effort 的 `--force-qa`；四种输入仍须独立执行。
不按输出长度推断是否发生强制收尾。

缺少 `final_answer` 的旧 QA 需 `--force-qa` 重跑。缺少 prefix 元数据的旧 Fairy
video/control QA 需按真实条件补成 true/false，或 `--force-qa` 替换选中范围的未分类结果。
数学结果缺少来源指纹时也需重跑。已入库变体的历史 JSON 不能作为正式 case 的写入
别名，应操作正式 case 的 `variant_context`。不对已有数据或报告执行批量迁移。

## 汇总、输出与排错

### 批量 QA/Judge

```bash
python scripts/run_all/run_qa_judge.py --dry-run
python scripts/run_all/run_qa_judge.py
python scripts/run_all/run_qa_judge.py --model gemini
```

常规批量运行使用 `run_qa_judge.py`，省略 `--model` 等同于 `--model all`。
默认三个云端模型依次运行四个 group（含 math），每组执行 `video`、`video-based`、
`description`、`description-based`，共 48 条命令；不包含 control 或 question_only。
保留模型、effort 和 Fairy video 的作品名前缀设置：Qwen Max 使用 all effort，
Gemini/Kimi 使用 default。也可用 `--model` 选择单个云端或本地模型；本地模型使用
all effort。`--group`、`--condition` 可重复指定，`--config` 覆盖并发、RPM 等配置。
默认配置文件为脚本同目录下的 `run_all_qa_judge_config.json`。

每次运行在 `results/run_all/<UTC时间戳>_<模型>_<随机ID>/` 下生成 `summary.txt`，
`--log-dir` 可覆盖其父目录。子进程完整输出实时显示在终端；每条命令结束立即追加并
flush 任务序号、模型、组、条件、完整命令、状态、退出码及实际输出的命令级统计，
包括 QA/Judge、This run、输出诊断，以及实际出现的 Question filter gates。
Summary 不保存逐 case 进度、回答、判定、逐命令日志、配置快照或状态 JSON；
本地模型的截断回答另存为下述 JSONL，日志路径和写入错误也会记入 summary。
零目标、提前失败和 Ctrl+C 中断分别记录，缺少的统计明确标为未报告，不推算完成数。
普通失败继续其余命令；中断停止后续命令并保留已收集统计，最后记录成功、失败、
中断及未启动数量。`--dry-run` 不创建文件或发起模型请求。

#### 保存本地模型的截断回答

选择 `--model cosmos3-nano`、`gemma4` 或 `qwen3.8-27b` 时，每次批量运行指定
`results/run_all/max_token/<本次运行ID>.jsonl`，运行 ID 与该次 summary 的目录名
相同。指定 `--log-dir` 时使用其下的 `max_token/`。同次运行的全部 group、condition
和 effort 共用这一绝对路径，下一次运行使用新文件；启动时在终端和 summary 中
打印路径。首次实际截断时才创建目录和文件并写入记录；没有截断、零目标或预检
失败时不创建该次运行的截断日志，也不新建 `max_token/` 目录。写入失败须结合
summary 判断；历史空日志文件不清理。云端批量运行保持原有输出方式。

直接运行 `qa-judge` 默认关闭保存，可显式启用，同样在首次实际截断时才创建目录
和文件；重复指定同一文件会继续追加：

```bash
python scripts/pipeline.py qa-judge --group real_world_commonsense_conflicts \
  --input description --qa-model gemma4 --thinking-effort all \
  --max-token-log results/truncated_gemma.jsonl
```

文件使用 UTF-8 JSONL，每次实际截断在任务执行线程中立即追加一条并 flush，以线程锁
保护并发写入。每条包含 `timestamp`、`case_path` / `case_id`、`group`、`video_id`、
`video_role`、`question_id` / `question`、`model`、`input` / `input_mode`、
`thinking_effort`、`based`、`work_title_prefix`、`max_tokens`、`thinking_token_budget`、
`generation_parameters`、`finish_reason`、`request_id`、`usage`、`reasoning_text`、
`answer_text`、`reasoning_source` 和未经修改的完整 `raw_response`，另含任务标识与
答案恢复次数 `final_answer_retry_count`（首次为 0，续写为 1）。续写截断记录另含
`final_answer_continuation`：首次完整响应及生成参数、追加的 assistant 消息和第二次
响应及参数，便于还原续写上下文；顶层 `raw_response` 为第二次响应，实际
`max_tokens=256`、`thinking_token_budget=null`。`input` 保留 control 条件，
`input_mode` 沿用 QA 中的 video 表示。
“完整”指截至截断时服务已经返回的全部响应，不包含服务未返回的 token。

Gemma/Qwen 优先用 `message.reasoning`，其次用 `message.reasoning_content` 分离推理
和正文，优先选择非空字段，`reasoning_source` 记录所用字段；两个字段同时存在时，
`raw_response` 保留两者。
Cosmos 从正文中的 `<think>…</think>` 提取推理，来源标为 `content.think_tags`；
未闭合的 `<think>` 后所有内容保留为推理，来源标为 `content.think_tags_unclosed`。
没有独立字段或可识别标签时，`reasoning_source=unavailable`、`reasoning_text=null`，
原文完整保留在 `answer_text` 和原始响应中，不猜测其语义。分离文本不裁剪空白，
不额外请求原始 token，也不更改提示、生成预算或服务端 parser。

本地首次 QA 返回 `length` 或 `max_tokens` 时，先写截断日志，只计入
`max_tokens_truncated`，不计 `missing_final_answer`，再进入一次 assistant 续写；
恢复过程复用现有重试、成功和失败计数。第二次 assistant 续写截断
只计入 `final_answer_continuation_max_tokens_truncated`，并计入任务级
`final_answer_retry_failed`，不额外计入 `missing_final_answer`。同一响应不进入两项
截断计数。首次截断响应本身不写为成功 QA、不进入 Judge；只有续写提取有效答案
后才保存并判分。续写截断终止任务，不再恢复。正常回答和缓存复用保持现有规则。
写入失败会报告完整路径和原因，
保留截断计数，summary 同时收录该错误。启用日志前已经丢弃的截断回答无法补回。

### 批量汇总已运行的实验

```bash
python scripts/run_all/run_all_summarize.py
python scripts/run_all/run_all_summarize.py --dry-run
```

该脚本扫描四个 group（含 math）中 conflict 视频已保存的目标 QA，覆盖 video、
video + based、description、description + based；Fairy video 只选择有作品名前缀的
记录。未产生目标 QA 的组合跳过，支持部分完成的实验。`--model all` 为默认值，
在此汇总入口中包含 Gemini、Qwen Max、Kimi、Cosmos、Gemma、Qwen27B 全部六个
模型。Qwen Max 和三个本地模型分别发现 none/default，Gemini 的历史 medium
归一化为 default；每个组合仅将实际保存过 QA 的 effort 显式传给原生 summarize。

支持 `--model`（含 `cosmos` / `gemma` 别名）、可重复的 `--group` / `--condition`、
`--dataset-dir` 和 `--summary-workers`（默认 4）。相对数据路径以仓库根目录为基准。
`--dry-run` 只展示发现的组合及命令，不写报告、不调用模型。实际汇总也只处理已有
记录，不执行 QA/Judge 请求。使用自定义数据目录时，输出仍写入仓库的 results 目录。

每个模型/组/条件调用一次原生 `summarize`，不传 `--filter passed`，采用默认
`filter=all`。新鲜度、有效判定和指标计算均沿用原生逻辑，各 effort JSON 和合并
Markdown 继续保存在 `results/<group>/<model>/`。已有目标 QA 但没有有效已判定答案的实验也
保留，计数为零、rate 为 null。

批量汇总统计全部有效已判定目标（含 ambiguous），不依赖 question-only 是否存在
或通过，也不会补跑模型。需要筛选报告时手动使用原生 `summarize --filter passed`。

额外原子写入并替换 `results/run_all/summary.json` 和 `results/run_all/report.md`。
前者每个实验/effort 一条记录，将本次原生 JSON 的 `answers.conflict` 原样保存为
`conflict`，附带模型、组、输入、based、prefix、effort、filter 和原生报告路径；
后者以表格展示 total、三类 label 数量、grounded_answer_rate、trapped_answer_rate，
并链接原生 JSON/Markdown；实验身份、JSON 元数据和报告标题均标记 `filter=all`。
不同实验之间不合并计数或平均比例。

只读取本次成功调用明确生成的报告。单个实验失败后继续其余实验，汇总列出失败
信息并最终非零退出，失败任务不会拿旧报告替代。未发现任何实验时生成明确的空
结果。每次运行替换总汇总，因此指定子集时总汇总仅包含本次选择的范围。

### 单个实验汇总

```bash
python scripts/pipeline.py summarize --group classic_fairy_tale_film_conflicts \
  --input video --qa-model qwen3.8-max --thinking-effort all
python scripts/pipeline.py summarize --group classic_fairy_tale_film_conflicts \
  --input video --qa-model qwen3.8-max --thinking-effort all \
  --with-work-title-prefix --based --filter passed
python scripts/pipeline.py summarize --group classic_fairy_tale_film_conflicts \
  --input control --qa-model qwen3.8-max --thinking-effort all \
  --with-work-title-prefix --based --filter passed
```

必须指定模型。Video 只汇总 conflict，control 只汇总 control；JSON 保留原有
answer/video 指标结构，新增 grounded/trapped 两种比例，未选角色计数为零、rate 为 null。
两种比例均以对应角色全部有效已判定样本（含 ambiguous）为分母，沿用六位小数；
control/question-only 有样本时 trapped 比例为 0。原生 Markdown 按 effort、角色展示
answer/video 两种比例，question-only 只有 answer 比例。`--filter all` 默认统计所选角色全部有效
结果；`--filter passed` 逐题筛选 question-only 通过的结果，再重新聚合 video 标签，
没有剩余题目的视频不计入分母，生成独立报告。Gate 标识不含作品名前缀。`--based` 和 prefix 选项应与目标实验条件相同。不同模型和
effort 通过的题目集合可能不同。缺失、过期、未判分或判错的 question-only 均不能视为
筛选通过；`--filter passed` 与 `--input question_only` 组合时报参数错误。
汇总只读取快照，不发模型请求；同时有 QA 运行时，
报告可能尚不完整。`--summary-workers` 默认 4，输出位置由程序确定。

省略 effort 或使用 `all` 时，只汇总已有判定中实际存在的 effort；没有结果则生成
默认 effort 的空 summary。每个 effort 一份 JSON，不同 effort 合并到一份 Markdown。
模型目录名为 `gemini`、`qwen`、`kimi`、`cosmos`、`gemma`、`qwen38_27b`。例如：

```text
results/<group>/qwen/qwen_description_none_summary.json
results/<group>/qwen/qwen_description_default_summary.json
results/<group>/qwen/qwen_description_report.md
results/<group>/qwen/qwen_control_<effort>_summary.json
results/<group>/qwen/qwen_control_report.md
results/<group>/qwen/qwen_question_only_<effort>_summary.json
results/<group>/qwen/qwen_question_only_report.md
results/classic_fairy_tale_film_conflicts/qwen/qwen_video_no_prefix_<effort>_summary.json
results/classic_fairy_tale_film_conflicts/qwen/qwen_video_with_prefix_report.md
results/classic_fairy_tale_film_conflicts/qwen/qwen_video_based_with_prefix_filter_passed_<effort>_summary.json
results/classic_fairy_tale_film_conflicts/qwen/qwen_video_based_with_prefix_filter_passed_report.md
results/classic_fairy_tale_film_conflicts/qwen/qwen_control_based_with_prefix_filter_passed_<effort>_summary.json
results/classic_fairy_tale_film_conflicts/qwen/qwen_control_based_with_prefix_filter_passed_report.md
```

文件名按模型、input、可选 based、Fairy prefix、可选 filter_passed、effort、summary
拼接；report 不含 effort。无 group 时位于 `results/<model>/`。报告展示完整回答与
实际判分答案；question-only 仅有 answer-level control 指标和逐题明细。

命令结束显示 `QA: 完成/总数`、`Judge: 完成/总数`。Video/control/description 的
终端比例统计所选角色的全部有效目标，复用结果也计为完成；独立 question-only 按
去重后的 conflict 有效 question scope × 问题 × effort 统计。缺少目标角色时不发模型
请求，返回零目标。另打印 `main`、`question_only` 两组输出诊断：本地模型显示
`max_tokens_truncated`、`final_answer_continuation_max_tokens_truncated` 和
`missing_final_answer`，两项截断计数即使为零也显示；云端只显示后者。只统计本次实际
请求，缓存复用不计入。另显示安排答案恢复的任务数 `final_answer_retries`、
成功落盘数 `final_answer_retry_recovered`、最终失败数 `final_answer_retry_failed`。
部分 QA 失败时继续判定其他成功回答，最终返回非零状态。

```text
QA output diagnostics (main, this run): max_tokens_truncated=3, final_answer_continuation_max_tokens_truncated=2, missing_final_answer=5, final_answer_retries=8, final_answer_retry_recovered=6, final_answer_retry_failed=2
```

此例为首次截断 3 次、缺失答案 5 次，共 8 个任务进入续写，其中恢复 6 个、续写截断
2 个；两种截断分开计数。批量运行的 `summary.txt` 保留完整诊断行。

| 问题 | 处理方法 |
|---|---|
| 缺少凭据、服务不可达或模型 ID 不明确 | 检查对应 key、地址、`/v1/models` 和模型服务日志 |
| 视频未就绪、文件缺失或观察过期 | 完成生成并补齐与当前文件绑定的 video_observation；文件存在不会自动修复状态 |
| description 过期 | 完成视频观察后重跑 description，再运行 QA |
| 本地回答达到 token 上限 | 首次截断自动尝试一次 256-token 续写；恢复失败时在 run_all 的 max_token 日志或显式指定的 `--max-token-log` 中核对响应，检查服务端预算与上下文容量；替换已有 QA 时使用 `--force-qa` |
| `thinking_token_budget` 不支持、服务拒绝或疑似被忽略 | 检查 vLLM 版本和 `--reasoning-config`，用更新后的脚本重启，再按下节验收；保留预算字段并报告错误，不删除参数静默重试，HTTP 成功本身不能证明生效 |
| 空正文、只有 reasoning 或缺少有效末行答案 | 检查模型输出；最终非空行须包含大小写匹配的 `Final answer:` 和非空答案 |
| 筛选报告为空或题目被排除 | 查看逐题 gate 原因，显式运行对应模型的 `--input question_only`；重跑/重判可加 force，不影响目标实验执行 |
| 共享服务配额冲突或 force 占用冲突 | 对齐活跃命令配置，等待占用命令结束；恢复机制见 concurrency.md |

全部 QA 模型、输入和 effort（含独立 question-only）正常结束但缺少有效最终答案时，
调度器恢复一次。解析允许最后一个非空行在标记前有解释，取该行最后一次标记后的
非空答案；标记缺失、答案为空、标记只在更早行、正常结束但正文为空或只有 reasoning
均触发此规则。云端仍完整重试原请求，输入、提示词和生成参数完全一致，不传回
首次回答或增加纠错提示。

Cosmos、Gemma 和本地 Qwen 对缺失答案及首次截断（`length` 或 `max_tokens`）使用
同一 assistant 续写流程，覆盖全部输入和 effort。截断先保存日志和计数，再安排恢复，
不误计为缺失答案。原始 system/user 和媒体输入不变，
追加 assistant 消息，其正文为首次完整回答再加 `\nFinal answer:`。独立返回的
reasoning 按 `reasoning`、`reasoning_content` 顺序选择非空字段，原样放在首次正文前，
以换行分隔；不插入可能被模型模板移除的推理通道标签。首次正文为空时也使用答案
前缀。请求设置 `continue_final_message=true`、`add_generation_prompt=false`、
`echo=false`、`max_tokens=256`，保留原采样、thinking 开关及媒体参数，移除
`thinking_token_budget`。不裁剪输入或首次回答，上下文不足直接报告服务端错误。

将预填的 assistant 正文和实际返回后缀原样拼接，再按末行规则提取 `final_answer`。
只有第二次有效才保存 QA 并进入 Judge，结果增加 `final_answer_retry_count: 1`；
本地 `raw_answer` 为拼接正文，`final_answer_continuation` 保存 `first_response`、
`first_generation_parameters`、`assistant_message`、`continuation_response` 和
`continuation_generation_parameters`，顶层 usage、请求 ID、预算对应第二次请求。
续写为空、不合格式或截断均终止任务，不保存成功 QA、不执行下游、不再格式重试。
每个任务最多恢复一次，截断和缺失答案共享此额度；云端截断仍直接失败，
判分错误不触发 QA 重试，已有有效结果不自动重跑。

每次重试重新申请并发和 RPM 额度，沿用同一任务认领。网络请求默认最多重试
4 次，与一次答案恢复分别计数，不因答案恢复重置额度；续写网络重试重发同一续写
请求，每次都重新申请并发和 RPM。QA/Judge 超时默认
600 秒，其他模型阶段默认 900 秒。用 `--max-retries` 和 `--timeout` 调整。

### 本地推理预算验收

以下步骤须在部署环境逐模型完成。静态语法检查、CLI 校验和 HTTP 成功均不能代替
强制结束推理的实际验证；三个模型全部通过后才开始批量实验。

1. 用更新后的脚本重启 vLLM 0.29.0 服务。以小预算（例如
   `--thinking-token-budget 64`）、足够的总预算和能产生较长推理的问题触发强制结束。
   结合 tokenizer、原始输出或服务端日志，确认推理结束边界被强制注入且正文继续生成，
   最终仍满足 `Final answer:` 规则。Gemma/Qwen 的 parser 会分离 reasoning 与正文，
   仅看正文或 token 使用量不能证明强制注入。
2. 分别验证自然提前结束、默认 6144、`none` 和 `all`，覆盖纯文字与真实视频请求。
   `none` 请求应无预算字段，`all` 中仅 default 任务发送；保留原有采样、视频处理和
   Qwen `xhigh` 参数。服务拒绝预算时应报告失败，不应去掉预算继续请求。
3. 用少量现有样本分别运行 video、control、description、question_only，检查实际
   请求和新结果中的预算字段及 Judge 流程。本地缺失答案或首次截断按上述协议续写
   一次，固定 256-token 预算且不发送 thinking budget；
   Judge 只读取解析出的 `final_answer`。
4. 检查旧结果按原规则复用；选择明确的小范围加 `--force-qa` 重跑，确认新 QA
   记录预算。预算不参与去重或指纹，缺少预算字段的旧记录不会自动失效。

将 `existing-case-id` 替换为现有 case ID，并按所选模型替换 CLI 名称及对应
max-tokens 选项，在部署环境运行单个现有 case：

```bash
python scripts/pipeline.py qa-judge --case-id existing-case-id \
  --input question_only --qa-model qwen3.8-27b --thinking-effort default \
  --thinking-token-budget 64 --qwen38-max-tokens 8192 --force-qa
```

上述命令会替换所选范围的 QA/Judge；强制边界证据仍需从原始输出或服务端日志核对。

### 本地答案续写验收

仅使用少量现有样本，不启动全量实验、不新增测试代码。逐个模型核对实际聊天模板
在 `continue_final_message=true`、`add_generation_prompt=false` 下，最终 prompt 停在
开放的 assistant `Final answer:` 前缀，未追加结束 token 或新的 assistant turn。
分别覆盖空正文、独立 reasoning、正常恢复、再次格式失败、首次截断后恢复和续写截断；
包含 none/default effort 与 video/control/description/question_only 输入。

检查每次续写重新申请并发/RPM，网络错误重发同一请求且重试额度不重置，服务端
上下文不足时报告错误。核对成功结果的拼接正文、审计对象、第二次 usage/请求 ID
和预算；失败结果不保存成功 QA、不进入 Judge。首次截断只增加原截断计数并安排
一次恢复，不计为缺失答案；续写截断只能增加新截断计数和任务重试失败数。
核对 `main`、`question_only` 的终端、
批量 summary 和截断日志一致。确认有效历史记录无需新增审计字段即可复用。
服务不可用时，模板静态核对、语法/CLI 检查不代表实机验收通过，须明确记录未完成。
