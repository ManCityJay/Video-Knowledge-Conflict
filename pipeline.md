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

可用阶段：`author`、`questions`、`description`、`generate`、`review`、
`delete`、`qa-judge`、`summarize`、`audit`。各阶段显式执行，没有自动串联入口。
参数用法统一查询本文，并发协调与恢复细节见 `concurrency.md`。

常用视频实验顺序：

```bash
python scripts/pipeline.py author --group classic_fairy_tale_film_conflicts
python scripts/pipeline.py questions --group classic_fairy_tale_film_conflicts
python scripts/pipeline.py generate --group classic_fairy_tale_film_conflicts
# 查看生成的视频，再按下文 review 命令逐个登记审核。
python scripts/pipeline.py qa-judge --group classic_fairy_tale_film_conflicts \
  --input video --qa-model qwen3.8-max --thinking-effort all
python scripts/pipeline.py summarize --group classic_fairy_tale_film_conflicts \
  --input video --qa-model qwen3.8-max --thinking-effort all
```

Control 视频以 `--input control` 独立执行 QA 和汇总；`--input video` 只执行
conflict。文字实验先运行 `description`，再以 `--input description` 执行 QA 和汇总。
其过滤与目标 QA 都只用文本，不依赖 control 视频。独立 question-only 实验有问题后即可执行，
不依赖视频文件、视频状态、description 或人工审核。

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
- `review` 一次选择一个 case 和一个视频；删除视频或问题时也只选择一个 case，
  `delete --all` 则可选择同组多个完整 case。

## 数据准备、生成、审核与删除

源 case 需预先按每个 case 一份 Markdown 准备，文件名为合法 case ID，首行使用
`### 标题`。Author 默认跳过已有 JSON；`--force` 可覆盖，但不能覆盖已有 verified
视频的数学 case。新增数学变体使用独立 `--output-dir`，审核后再入库。

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
新提交的生成任务也会清空旧 description 和观察；成功下载后标为 ready，并要求
重新审核。数学 unqualified 视频已备份并移出正式数据；不能凭旧文件或旧目录
恢复资格。视频重建不影响独立 question-only 结果。

```bash
python scripts/pipeline.py review --group classic_fairy_tale_film_conflicts \
  --case-id alice_drink_makes_her_grow --video-id v001 --decision verified
```

也可用 `--decision rejected`。只有 ready 且文件存在的视频能登记审核；需要
视频观察的数学视频须先补齐实际审核观察，`review` 本身不生成这些证据。
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
| `gemma4` | `none`、`default` | 4 / 4 | `--gemma-max-tokens 2048` |
| `qwen3.8-27b` | `none`、`default` | 1 / 1 | `--qwen38-max-tokens 32768` |

省略 effort 使用 `default`；`all` 执行模型支持的全部 effort，也可重复指定该选项。
模型 ID、温度和视频采样协议见 [plan.md](plan.md#模型配置与采样协议)。

本地服务启动脚本在 Linux/Bash、Conda 和兼容的 vLLM 环境中运行：

```bash
bash scripts/start_cosmos_vllm.sh
bash scripts/start_gemma4_vllm.sh
bash scripts/start_qwen38_vllm.sh
# Gemma 仅查看启动命令
DRY_RUN=1 bash scripts/start_gemma4_vllm.sh
# Qwen27B dry-run 无需激活 Conda 或安装 vLLM
DRY_RUN=1 bash scripts/start_qwen38_vllm.sh
```

Cosmos 默认激活 `vllm` 环境、GPU 0 单卡、BF16、端口 8000、`MAX_NUM_SEQS=4`。
`VIDEO_ROOT` 默认仓库 `videos/`，`TENSOR_PARALLEL_SIZE`、`CUDA_VISIBLE_DEVICES`、
`MAX_NUM_SEQS`、`GPU_MEMORY_UTILIZATION`、`VLLM_HOST`、`VLLM_PORT` 可覆盖。
无需添加模型架构覆盖参数。

Gemma 默认 `vllm` 环境、GPU 0/1 双卡、BF16、32K 上下文、`MAX_NUM_SEQS=2`、
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
Description 与 question-only 过滤都只用文本，`TEXT_ONLY=1` 同时适用于二者。

```bash
python scripts/pipeline.py qa-judge --group classic_fairy_tale_film_conflicts \
  --input video --qa-model gemma4 --thinking-effort all
python scripts/pipeline.py qa-judge --group classic_fairy_tale_film_conflicts \
  --input description --qa-model qwen3.8-max --thinking-effort all
python scripts/pipeline.py qa-judge --group real_world_commonsense_conflicts \
  --input question_only --qa-model qwen3.8-max --thinking-effort all
```

`--input` 默认 `video`，执行与汇总使用相同的角色选择：

| `--input` | 目标 |
|---|---|
| `video` | conflict 视频及其有效问题 |
| `control` | control 视频及其有效问题 |
| `description` | conflict 文本 context 及其有效问题 |
| `question_only` | case 顶层共享问题 |

视频的有效问题来自共享或私有上下文，并受可选 `question_ids` 约束。
独立 question-only 不要求视频文件存在或 ready，也不遍历私有问题；存在私有问题的
case 仍可执行顶层共享题目。共享结果写入 `question_only_results`，与主 QA 的共享
question-only filter 共用来源指纹。不能组合 `--video-id`、`--with-work-title-prefix`
或 `--based`。

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

### question-only filter、续跑与 force

Video、control 和 description 默认逐题执行 question-only 过滤：目标视频自己的
有效问题必须答对（Judge 判 `context_grounded`）才执行目标 QA。失败题目不阻止其他
题目。共享问题的 gate 跨输入条件复用；私有问题按所属视频 scope 隔离。Filter 不加
based 指令或作品名前缀，gate 身份不含这些条件；`variant_context.matched_control_path`
不参与 gate。各组视频请求只按角色和 ready 状态选择，并检查文件和观察是否过期；
不另加数学组的人工审核资格门槛。

只补 filter、不重跑目标 QA：

```bash
python scripts/pipeline.py qa-judge --group classic_fairy_tale_film_conflicts \
  --input video --qa-model qwen3.8-max --thinking-effort all --filter-only
python scripts/pipeline.py qa-judge --group classic_fairy_tale_film_conflicts \
  --input control --qa-model qwen3.8-max --thinking-effort all --filter-only
```

可保留原有 case、video、question 和 scope 选择。`--filter-only` 只跑 question-only，
接受 video/control 输入，不能组合 `--based`；作品名前缀不会传给 filter。正常重复
运行复用有效结果；请求中断后可用相同命令续跑，已判错的 filter 不会自动反复
尝试到答对。

- `--force-qa` 清理选中且通过 filter 的目标 QA/Judge，再执行。
- `--force-judge` 保留目标回答，只清理匹配 judgment 并重判。
- 两者互斥，普通 video/control/description force 保留 question-only filter、未通过题目的
  历史及另一 based/prefix 条件。
- 强制重跑 filter 用 `--filter-only --force-qa`；只重判用
  `--filter-only --force-judge`。保留历史，主实验依赖 question-only 的新判定；
  共享题目新判定也影响复用该 gate 的其他角色和输入条件。
- 独立 question-only force 只清理选中顶层共享问题的对应模型和 effort 结果。

Force 先独占全部所选 case；冲突时报错。Video/control/description 先准备 filter，再预检和
统一清理主实验结果，全部清理成功后才开始主实验请求。清理中断可能已有部分文件
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
旧 `QWEN_BASE_URL` 仍可读取，`/compatible-mode/v1` 后缀会转换为 `/api/v1`。

缺少 `final_answer` 的旧 QA 需 `--force-qa` 重跑。缺少 prefix 元数据的旧 Fairy
video/control QA 需按真实条件补成 true/false，或 `--force-qa` 替换选中范围的未分类结果。
数学结果缺少来源指纹时也需重跑。已入库变体的历史 JSON 不能作为正式 case 的写入
别名，应操作正式 case 的 `variant_context`。不对已有数据或报告执行批量迁移。

## 汇总、输出与排错

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
answer/video 指标结构，未选角色计数为零。`--filter all` 默认统计所选角色全部有效
结果；`--filter passed` 逐题筛选 question-only 通过的结果，再重新聚合 video 标签，
没有剩余题目的视频不计入分母，生成独立报告。Gate 标识不含作品名前缀。`--based` 和 prefix 选项应与目标实验条件相同。不同模型和
effort 通过的题目集合可能不同。汇总只读取快照，不发模型请求；同时有 QA 运行时，
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
终端比例仅统计所选角色中通过 filter 的有效目标，复用结果也计为完成；独立
question-only 按顶层共享问题 × effort 统计。缺少目标角色时不发模型请求，返回零目标。
另打印 `main`、`question_only filter` 两组输出诊断：本地模型显示
`max_tokens_truncated` 和 `missing_final_answer`，云端只显示后者。只统计本次实际
请求，缓存复用不计入。另显示安排格式重试的任务数 `final_answer_retries`、
成功落盘数 `final_answer_retry_recovered`、最终失败数 `final_answer_retry_failed`。
部分 QA 失败时继续判定其他成功回答，最终返回非零状态。

| 问题 | 处理方法 |
|---|---|
| 缺少凭据、服务不可达或模型 ID 不明确 | 检查对应 key、地址、`/v1/models` 和模型服务日志 |
| 视频未就绪、文件缺失或观察过期 | 完成生成和实际视频审核，再运行 review；不靠文件存在自动修复状态 |
| description 过期 | 完成视频观察后重跑 description，再运行 QA |
| 本地回答达到 token 上限 | 增大对应 max-tokens 参数；替换已有 QA 时使用 `--force-qa` |
| 空正文、只有 reasoning 或缺少有效末行答案 | 检查模型输出；最终非空行须包含大小写匹配的 `Final answer:` 和非空答案 |
| Filter 未通过 | 查看逐题 gate 原因；需要主动重跑时使用 filter-only force |
| 共享服务配额冲突或 force 占用冲突 | 对齐活跃命令配置，等待占用命令结束；恢复机制见 concurrency.md |

全部 QA 模型、输入和 effort（含 question-only filter）正常结束但缺少有效最终答案时，
调度器完整重试原请求一次，输入、提示词、生成参数完全一致，不传回首次回答或
增加纠错提示。解析允许最后一个非空行在标记前有解释，取该行最后一次标记后的
非空答案；标记缺失、答案为空、标记只在更早行、正常结束但正文为空均触发此规则。
第二次有效才保存该回答并进入 Judge，结果增加 `final_answer_retry_count: 1`；
第二次仍格式失败则终止任务，不保存成功 QA，也不执行下游。截断和判分错误不触发
格式重试，已有有效结果不自动重跑。这取代此前缺少 final answer 直接失败的约定。

每次重试重新申请并发和 RPM 额度，沿用同一任务认领。网络请求默认最多重试
4 次，与一次格式重试分别计数，不因格式重试重置额度。QA/Judge 超时默认
600 秒，其他模型阶段默认 900 秒。用 `--max-retries` 和 `--timeout` 调整。
