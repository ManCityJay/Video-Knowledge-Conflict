# Video Knowledge Conflict 实验框架

2026-09-28 更新：video 和 description QA 现在默认逐 question 执行
question-only → 匹配 control video 两层 filter，均答对后才运行该 question 的
conflict video 或 description QA。按模型、thinking effort、题目作用域和 video
prefix 隔离，不按 case 或 video 整体筛掉。
私有数学变体使用自己的题目和 `matched_control_path`。
已有 QA 可用 `qa-judge --input video --filter-only` 补齐 filter，随后
`summarize --filter passed` 生成独立的筛选报告，原始数据和全量报告保留。
`--based` 仅改变目标 video/description QA；两层 filter 始终使用未加该提示的回答，
`--filter-only` 与 `--based` 不可组合。
完整命令、来源指纹和 force 规则见 `pipeline.md` 的「Question 级双 filter 筛选」。

2026-10-02 更新：筛选统一命名为 filter，CLI 使用 `--filter-only` 和
`summarize --filter all|passed`，不再接受旧 baseline 参数。旧 JSON 字段兼容读取，
已有数据和报告不迁移；新筛选记录使用 `filter_stage`、`filter_fingerprint`，
私有题目新增记录写入 `filter_results`，指纹算法保持不变。
`qa-judge --input video --based` 仅执行 conflict 目标；control 仍以未加 based 的
条件参与筛选。已有 based control 的回答和判分保留，后续 QA/Judge 和 force
均跳过它们，历史汇总规则不变。Fairy control filter 的作品名前缀仍与目标 video
条件一致；description 的 control filter 不额外添加作品名前缀。

## 目标

实验用于测量视频问答模型在“画面事实与经典知识冲突”时，是否忽略当前输入
证据并退回经典答案。每个 case 包含 1–5 个 conflict 视频和 1 个匹配的正常
control 视频，并为每个独立语义目标生成一个中性问题。

Luna Pro 负责 case authoring、问题生成、文字 context 生成和答案判定；
Seedance 负责生成视频；Gemini、Qwen、Kimi 或本地 Cosmos3-Nano、Gemma 4 负责视频、
文字 context 或 question-only QA。

## 数据结构

正式 case 默认位于 `dataset/cases/<case_id>.json`；使用 `--group` 时位于
`dataset/cases/<group>/<case_id>.json`。只支持 schema `4.0`。

```json
{
  "schema_version": "4.0",
  "case_id": "alice_eat_cake_makes_her_shrink",
  "title": "Alice in Wonderland: The Cake Makes Alice Shrink",
  "conflict_spec": {
    "normal_fact_en": "The cake makes Alice grow.",
    "intended_video_fact_en": "The cake makes Alice shrink."
  },
  "questions": [
    {
      "question_id": "q001",
      "text_en": "In Alice in Wonderland, what happens to Alice after she eats the cake?",
      "conflict_video_reference_en": "She shrinks.",
      "normal_control_reference_en": "She grows.",
      "question_only_results": []
    }
  ],
  "videos": [
    {
      "video_id": "v001",
      "role": "conflict",
      "seedance_prompt_en": "...",
      "task_id": null,
      "status": "pending",
      "local_path": "videos/seedance/alice_eat_cake_makes_her_shrink/v001.mp4",
      "human_review": "pending",
      "description": {
        "context_en": "In Alice in Wonderland, Alice eats the cake and her body shrinks.",
        "context_prefix_en": "In Alice in Wonderland,",
        "source": "seedance_prompt_en",
        "source_sha256": "...",
        "generator_model": "openai/gpt-5.6-luna-pro",
        "generated_at": "...",
        "generator_request_id": "..."
      },
      "qa_results": []
    },
    {
      "video_id": "control",
      "role": "control",
      "seedance_prompt_en": "...",
      "task_id": null,
      "status": "pending",
      "local_path": "videos/seedance/alice_eat_cake_makes_her_shrink/control.mp4",
      "human_review": "pending",
      "qa_results": []
    }
  ]
}
```

case JSON 是运行状态的唯一持久化单元。视频状态、任务 ID、description、QA
完整回答 `raw_answer`、明确末行 `final_answer`、usage 与 judgment 均直接写回，
写入使用临时文件替换。
`description` 是仅用于 conflict 视频的可选扩展。
`question_only_results` 是 case 顶层 question 的可选扩展；结果不依附任何视频，
不包含 `context_text_en`、`work_title_prefix` 或 `based`。现有 case 无需迁移。

新 QA 记录不再包含 `context_sha256` 或 `video_sha256`。旧记录中的这些字段
继续兼容读取，但不参与去重或统计。

## 环境变量

```powershell
$env:OPENROUTER_API_KEY = "<openrouter-api-key>"
$env:ARK_API_KEY = "<ark-api-key>"
$env:DASHSCOPE_API_KEY = "<dashscope-api-key>"
$env:MOONSHOT_API_KEY = "<moonshot-api-key>"
```

可选 endpoint 覆盖：

```powershell
$env:ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
$env:DASHSCOPE_BASE_HTTP_API_URL = "https://dashscope.aliyuncs.com/api/v1"
$env:MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"
$env:COSMOS_BASE_URL = "http://127.0.0.1:8000/v1"
$env:GEMMA_BASE_URL = "http://127.0.0.1:8001/v1"
```

历史 `QWEN_BASE_URL` 仍兼容；`/compatible-mode/v1` 后缀会自动转换为
`/api/v1`。

## 模型配置

- Author / Questions / Judge：`openai/gpt-5.6-luna-pro`，通过 OpenRouter。
- Gemini QA：`google/gemini-3.1-pro-preview`，`temperature=0`。
- Qwen QA：`qwen3.8-max`，通过 DashScope SDK 上传本地视频，固定 `fps=2`、
  `temperature=0`。
- Kimi QA：`kimi-k3`，有效温度为 `1.0`。
- Cosmos3-Nano QA：`nvidia/Cosmos3-Nano`，本地 vLLM 服务，固定
  `temperature=0`、`seed=0`；请求使用 `/v1/models` 返回的模型 ID。
- Gemma 4 QA：CLI 使用 `--qa-model gemma4`，结果记录
  `google/gemma-4-31B-it`；本地 vLLM 默认端口 8001，固定
  `temperature=0`、`seed=0`，请求使用 `/v1/models` 返回的模型 ID。

Gemini 和 Kimi 把本地视频编码为 Base64 Data URL。Qwen 使用中国大陆
DashScope endpoint，并把本地绝对路径转换为 `file:///...` URI 交给 SDK。
Qwen 本地视频最大 100 MiB；Kimi 请求体最大 100 MB。
Cosmos 视频使用服务端可读的绝对 `file://` MP4 路径；文字 QA 不发送视频或采样参数。
服务地址由 `COSMOS_BASE_URL` 配置，默认 `http://127.0.0.1:8000/v1`。

单卡 Cosmos3-Nano 服务在仓库根目录运行：

```bash
./scripts/start_cosmos_vllm.sh
```

脚本自动激活 `vllm` 环境，使用 `HF_HOME=/cache/huggingface`，只使用第 0 张
GPU（TP=1），监听 `127.0.0.1:8000`，默认允许读取仓库的 `videos/`。
若视频存放在其他目录，运行
`VIDEO_ROOT=/绝对路径/视频目录 ./scripts/start_cosmos_vllm.sh`；该目录必须覆盖
case 中的视频路径。脚本等价于在交互式 Bash 中运行以下命令：

```bash
conda activate vllm
export HF_HOME=/cache/huggingface
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"
export VLLM_USE_FLASHINFER_SAMPLER=0
VIDEO_ROOT="$(pwd -P)/videos"
CUDA_VISIBLE_DEVICES=0 vllm serve nvidia/Cosmos3-Nano \
  --tensor-parallel-size 1 \
  --mm-encoder-tp-mode data \
  --async-scheduling \
  --allowed-local-media-path "$VIDEO_ROOT" \
  --media-io-kwargs '{"video": {"video_backend": "opencv", "num_frames": -1, "fps": -1}}' \
  --max-num-seqs 4 \
  --host 127.0.0.1 --port 8000
```

不要使用 `--hf-overrides '{"architectures": ["Cosmos3ReasonerForConditionalGeneration"]}'`：
当前本机 vLLM 不支持这个架构名。由模型配置和 vLLM 选择其支持的
`Cosmos3ForConditionalGeneration` 实现；服务就绪后可用
`curl http://127.0.0.1:8000/v1/models` 查看实际对外模型 ID。

Cosmos 视频的实验采样协议是先保留原始视频帧，再由模型配套的视频处理器
从头到尾均匀抽取 4 fps，不固定为 8 帧。不能让 vLLM 加载器先按 fps 抽帧后
由处理器再次采样。每个视频请求显式传入
`media_io_kwargs={"video":{"video_backend":"opencv","num_frames":-1,"fps":-1}}`
和 `mm_processor_kwargs={"fps":4,"do_sample_frames":true}`。全帧解码会增加
CPU 内存占用。

Gemma 4 服务通过 `bash scripts/start_gemma4_vllm.sh` 启动，默认双卡 BF16、
32K 上下文。视频同样使用服务端可读的 MP4 `file://` 路径，须位于
`MEDIA_ROOT`（默认仓库 `videos/`）内。视频请求显式传入
`media_io_kwargs={"video":{"video_backend":"opencv","num_frames":32,"fps":-1}}`，
由加载器对整段视频均匀采样最多 32 帧（不足 32 帧时保留全部帧），Gemma 的
vLLM 视频处理路径使用每帧最多 70 个视觉 token，不再叠加处理器 fps 采样。
这是对齐官方 HF 处理器的 32 帧均匀采样默认；旧启动脚本额外设置的 `fps=1`
会减少短视频帧数，本次移除该限制及多余的全局视觉预算覆盖。
来源：[官方处理器配置](https://huggingface.co/google/gemma-4-31B-it/blob/main/processor_config.json)、
[vLLM Gemma 视频实现](https://github.com/vllm-project/vllm/blob/v0.29.0/vllm/model_executor/models/gemma4_mm.py)。

Gemma 支持 `--thinking-effort none|default|all`，省略时使用 `default`；
请求以 `chat_template_kwargs.enable_thinking` 显式关闭或开启推理，不依赖服务端
默认值。Gemma 的 `--qa-concurrency` 和 `--qa-service-concurrency` 均默认 4；
`--gemma-max-tokens` 默认 2048。文字请求不含视频或采样参数。
主 QA 和两层 filter 共用同一模型配置，本地 QA 不使用 OpenRouter RPM 限制。
`raw_answer` 保存回答正文，可选 `reasoning_content` 保存服务返回的推理文本；
`final_answer` 仅从正文提取，Judge 不读取推理内容。生成温度 0 是本实验选择，
区别于模型卡推荐的随机生成参数。完整命令见 `pipeline.md`。

## 判断与指标

实验保存完整 `raw_answer` 供核查，但仅根据明确的 `final_answer` 判定，
不从模型的其他表述中推断主答案。所有 QA 和 filter 均允许 `Final answer:` 位于
最后一个非空行的解释文字之后，取该行最后一次标记后的非空内容；标记缺失、
答案为空或标记仅出现在更早的行时仍拒绝。模型提示词和输入指纹保持不变。
Fairy 视频另设有无作品名前缀两种条件，
用于比较提示中是否出现作品名对回答的影响。

Judge 根据问题、`final_answer`、输入角色、冲突事实和两类 reference 分类：

- conflict 输入回答 conflict reference：`context_grounded`
- conflict 输入回答 normal reference：`knowledge_trapped`
- control 输入回答 normal reference：`context_grounded`
- 混合、矛盾、含糊、回避、无关或无法可靠归类：
  `ambiguous_or_unjudgeable`

Description 输入复用相同 verdict，其中 `context_grounded` 表示回答遵循所提供的
文字 context。

Question-only 输入只发送原始 question 和相同的 `Final answer:` 格式要求，不发送
视频、description 或作品名前缀。它按 control 角色判定：匹配 normal reference 为
`context_grounded`；匹配 conflict reference、混合或无法确认的回答均为
`ambiguous_or_unjudgeable`，不产生 `knowledge_trapped`。

报告分别统计 answer-level 和 video-level 指标。同一视频的多个问题同时出现
grounded 与 trapped 时，video-level verdict 为 ambiguous。
两级 `knowledge_trapped` rate 都使用全部 conflict 样本作为分母，即
`knowledge_trapped / (context_grounded + knowledge_trapped + ambiguous_or_unjudgeable)`；
没有 conflict 样本时为 `null`。

Pipeline 的运行命令、参数和结果文件路径见 `pipeline.md`。

## Math 数据一致性与审核记录（2026-09-24）

math 的 `qa-judge` 和 `summarize` 默认只选择 qualified 数据；
显式 `--video-scope all` 才扩大范围。重新生成后的文件必须重新审核，
不会仅因 qualified 路径或旧文件还存在而自动恢复资格。

QA 及判断结果会绑定实际题目、视频/description 和参考答案；
过期结果不会作为完成项或纳入统计。历史 math 结果没有新指纹时需要重跑，
原结果仍保留在 JSON 中。修改 description 的观察文本同样会使旧结果过期。

离线检查（不调用模型）：

```bash
python scripts/pipeline.py audit --group mathematics_algorithm_conflicts \
  --output artifacts/math_pipeline_audit.json
```

加 `--strict` 会在缺少审核回执等警告出现时也返回非零状态。
该检查验证结构、关联和证据新鲜度，不代替视频内容审核或问题语义审核。

对已有题目只审不改（会调用 OpenRouter/Luna）：

```bash
python scripts/pipeline.py questions --group mathematics_algorithm_conflicts \
  --case-id queue_removes_newest_item_first --video-id v008 --audit-only
```

审核结果保存到对应的 `question_audit`，包括模型、时间、请求 ID、
逐项检查和上下文指纹；不能把“questions 非空”等同于“独立审题已通过”。
`--audit-only` 不与 `--force` 或 `--repair-variant-context` 混用。

已入库变体的 `dataset/variant_cases` 文件是历史来源快照，
其 `canonical_case_path` 指向正式数据。应在正式 case 的 `variant_context`
上操作，不能通过历史副本重新生成或删除正式视频。
`author --force` 也不能覆盖已有 qualified 视频的 math case；
新增数字变体请使用独立 `--output-dir`，审核后再入库。

Question-only control 实验不依赖视频文件、状态、description 或人工审核：

```bash
python scripts/pipeline.py qa-judge --group <group> \
  --input question_only --qa-model qwen3.8-max --thinking-effort all
python scripts/pipeline.py summarize --group <group> \
  --input question_only --qa-model qwen3.8-max --thinking-effort all
```

首版只支持 `case.questions`，不支持含 `variant_context` 私有问题 scope 的 case；
选中这类 case 会在任何模型请求和 force 清理前报错。`question_only` 禁止与
`--video-id`、`--with-work-title-prefix` 或 `--based` 组合，Math group 暂不纳入该实验。

数据清理使用 `delete`。删除视频或问题时一次命令只操作一个 case，可同时指定
多个 `--video-id` 和 `--question-id`；`--all` 可同时删除同一 group 下多个完整
case 的 JSON 和视频目录。单独删除视频仅允许 conflict，并且必须至少保留一个
conflict。删除问题会同时清除其全部 QA/Judge 历史。

不提供 `split-source`、自动串联全部阶段的 `all` 命令，也不提供
video/description 配对 `compare`。Source cases 必须预先按每个 case 一个 Markdown
文件准备，各阶段显式执行。文字 context stage 名称为 `description`。

`qa-judge` 使用请求级流水线：两层 filter 和目标 QA 的每条回答保存后立即进入
对应 Judge；每层 filter 通过后立即释放下游。单 case 内的问题和 effort 可并行。
同一工作区多个普通命令可共享 case，通过 SQLite 协调任务认领、服务额度和重试；
写回时短暂加锁、重读最新 JSON 并仅合并当前结果。Force 独占所选 case。
完整参数、故障恢复及限制见 `concurrency.md`。Video 和 Description QA 新记录均保存布尔字段 `based`；旧记录缺少时
按 `false` 处理。Description QA 在当前 video 对象中按以下键去重：

```text
input + question_id + qa_model + thinking_effort + based
```

仅 `classic_fairy_tale_film_conflicts` 的 Video QA 额外记录布尔字段
`work_title_prefix`，并按以下键去重：

```json
"work_title_prefix": false
```

对照条件则为 `true`。Description QA 不得包含该字段。

```text
input + question_id + qa_model + thinking_effort + based + work_title_prefix
```

其他 group 的 Video QA 使用与 Description QA 相同的五字段去重键，新结果不保存
`work_title_prefix`；旧结果即使含有该字段也会忽略其值，不需要迁移或重跑。

Question-only 结果保存在所属顶层 question 的 `question_only_results`，同样使用
四字段键去重：

```text
input + question_id + qa_model + thinking_effort
```

`questions --force` 替换问题和 `delete --question-id` 删除问题时，会同步清除对应
question-only QA/Judge 历史；删除或重新生成视频不影响 question-only 结果。

仅 Fairy video 的旧 QA 若缺少该字段，普通 `qa-judge`、`--force-judge` 和
`summarize` 才会要求先按真实运行条件补为 `true` 或 `false`。也可以使用
`--force-qa` 删除当前筛选范围内的未分类旧结果并按当前 prefix 条件重跑；另一种
已明确标记的 prefix 结果和全部 description 结果不会被清除。

视频输入预检会检查选中视频的状态和本地 `local_path`。未标记为 `ready` 的视频
不会因文件存在而自动升级；已标记为 `ready` 但文件不存在时，在模型请求前报错。
视频 QA 的输入指纹包含文件 SHA-256；手工替换同路径视频会使旧 QA 过期。
通过 pipeline 重新生成视频、description 或 questions 时会清除相应 QA。

关闭 `--based` 时沿用旧 prompt 和输入指纹；开启后在 question 前加入中性的
video/context 依据指令并使用独立指纹，`Final answer:` 指令仍在最后。不为最终回答
协议增加版本。旧记录允许加载和被
`--force-qa` 清除，但不会猜测或迁移 `final_answer`；普通运行或
`--force-judge` 选中旧格式记录时，会在任何模型请求前要求先执行
`--force-qa`。

`--force-qa` 和 `--force-judge` 互斥。普通 video/description force 仅清理当前
选中且通过 filter 的主实验 QA/Judge，不清理 control、question-only filter
或未通过题目的历史。Force 在任何模型请求前独占登记全部所选 case；冲突则报错。
随后先准备 filter（可补充模型请求），再预检并统一清理主实验结果。全部清理
成功前禁止主实验模型请求；清理并非跨文件事务，中断时可能已有部分清理落盘。
独立 question-only force 清理所选 question-only 结果；`--filter-only` force
单独强制执行 filter，仍保留历史并按第一层新判定决定是否执行第二层。

命令结束打印 QA 和 Judge 各自的完成数/总数。Video/description 的终端完成比例
仅包含通过双层 filter 的 conflict 目标，不包含 control；QA 单位为 video ×
question × thinking effort，Judge 统计对应有效 QA 记录。独立运行
`--input question_only` 时仍统计 question × thinking effort。已有可复用结果计为
完成，summary/report 继续保留独立的 control 对照统计。执行调度、force 和退出码
的完成校验范围不因终端显示调整而改变。部分 QA 失败时仍判定其他已完成回答，
最终以非零状态退出。

每次运行还会按三个阶段分别打印 QA 输出诊断。本地 Cosmos/Gemma 的格式为：

```text
QA output diagnostics (main, this run): max_tokens_truncated=<数量>, missing_final_answer=<数量>
QA output diagnostics (question_only filter, this run): max_tokens_truncated=<数量>, missing_final_answer=<数量>
QA output diagnostics (control filter, this run): max_tokens_truncated=<数量>, missing_final_answer=<数量>
```

`main` 表示 conflict video/description QA，或独立运行的 question-only QA。
两层 filter 分别统计，不混入主实验。只有 Cosmos/Gemma 根据
`finish_reason == "length"` 统计截断；截断优先，同一回答不再重复计为缺少
final answer。Gemini/Qwen/Kimi 等闭源模型不检测截断，诊断行仅显示
`missing_final_answer`。

缺少有效 final answer 包括有效响应正文为空、仅有 reasoning，以及不满足现有
末行 `Final answer:` 规则的回答。网络错误或响应结构损坏不计入该类。计数仅覆盖
本次实际执行的 QA，缓存复用和历史失败不计入，不持久化失败明细。正常结束、
`--filter-only`、无目标或无问题通过 filter 等正常提前返回路径都输出三组诊断，
未执行或没有这两类问题时显示零值；其他请求失败仍按原逻辑报错。

`summarize` 为每个实际 effort 生成：

```text
results/<group>/<qwen|kimi|gemini|cosmos|gemma>_<video|description>_<none|default>_summary.json
```

Question-only 产物为：

```text
results/<group>/<model>_question_only_<effort>_summary.json
results/<group>/<model>_question_only_report.md
```

Question-only summary 只包含 answer-level control 指标，不包含 `videos`；其
`grounded_answer_rate` 以全部回答为分母，包括 ambiguous。重复历史记录按
`(timestamp, run_id)` 选择最新一条。Report 按 case/question 展示 raw answer、
final answer、verdict 和 confidence，不显示视频 ID、本地文件或 context。

Fairy video 使用显式条件名，分别生成：

```text
results/classic_fairy_tale_film_conflicts/<model>_video_no_prefix_<effort>_summary.json
results/classic_fairy_tale_film_conflicts/<model>_video_with_prefix_<effort>_summary.json
```

同一模型和 input 的不同 effort 合并到：

```text
results/<group>/<qwen|kimi|gemini|cosmos|gemma>_<video|description>_report.md
```

Fairy video report 同样分别使用 `_video_no_prefix_report.md` 和
`_video_with_prefix_report.md`；其他 group 和 description 的文件名保持不变。
开启 `--based` 的 summary/report 在 input 后、Fairy prefix 和 `filter_passed` 前
加 `_based`，关闭时文件名保持原样；JSON 标明 `based` 条件。

Report 同时展示 QA 的完整 `raw_answer`、Judge 实际使用的 `final_answer`、verdict
和 confidence。

## 运行时代码

```text
scripts/
├── pipeline.py
├── start_cosmos_vllm.sh
├── start_gemma4_vllm.sh
├── mcd_v1/              # 独立对比解码实验；见该目录 README.md
└── vconflict_pipeline/
    ├── cli.py
    ├── settings.py
    ├── core.py
    ├── transport.py
    ├── authoring.py
    ├── descriptions.py
    ├── generation.py
    ├── deletion.py
    ├── filters.py
    ├── selection.py
    ├── qa.py
    ├── scheduler.py       # 请求级依赖调度、重试与短锁合并
    ├── runtime.py         # 同机跨进程认领、锁及共享额度
    ├── evaluation.py
    ├── evidence.py
    ├── integrity.py
    ├── audit.py
    └── reporting.py
```

历史 control 的 `pending` 审核状态保留为审计警告，不自动视为 `verified`。
本次详细审查和备份见 `artifacts/math_pipeline_audit_20260924/README.md`。
