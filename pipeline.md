# Pipeline 使用说明

唯一主入口是：

```bash
python scripts/pipeline.py <stage> [参数]
```

正式数据、结果和视频分别位于 `dataset/cases/`、`results/` 和 `videos/seedance/`。

## 按数据组运行

当 source cases 位于单层子目录时，可以用 `--group` 让所有阶段只处理该组：

```bash
python scripts/pipeline.py all \
  --group classic_physics_chemistry_experiments \
  --qa-model qwen3.8-max \
  --thinking-effort all
```

目录会自动映射为：

```text
dataset/source_cases/classic_fairy_tale_film_conflicts/
dataset/cases/classic_fairy_tale_film_conflicts/
videos/seedance/classic_fairy_tale_film_conflicts/<case_id>/
results/classic_fairy_tale_film_conflicts/
```

`--group` 可用于 `split-source`、`author`、`questions`、`generate`、
`review`、`qa`、`judge`、`summary`、`report` 和 `all`。它也可以和
`--case-id` 一起使用，只运行组内指定 case：

```bash
python scripts/pipeline.py all \
  --group classic_fairy_tale_film_conflicts \
  --case-id alice_drink_makes_her_grow
```

`--source-dir`、`--output-dir` 和 `--dataset-dir` 在 group 模式下仍表示根目录，
group 名会自动追加到这些目录。summary/report 的显式 `--output` 不受影响。
不传 `--group` 时保持原有平铺行为，已有数据不会迁移。

## 环境变量

Qwen 本地视频上传需要 DashScope Python SDK 1.24.6 或更新版本。请在运行 pipeline 的同一个 Python/Conda 环境中自行安装：

```powershell
python -m pip install -U "dashscope>=1.24.6"
```

代码不会自动安装或修改环境；缺少 SDK 或版本过旧时会显示上述安装命令。

PowerShell 示例：

```powershell
$env:OPENROUTER_API_KEY = "<openrouter-api-key>"
$env:ARK_API_KEY = "<ark-api-key>"
$env:DASHSCOPE_API_KEY = "<dashscope-api-key>"
$env:MOONSHOT_API_KEY = "<moonshot-api-key>"
```

可选覆盖：

```powershell
$env:ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
$env:DASHSCOPE_BASE_HTTP_API_URL = "https://dashscope.aliyuncs.com/api/v1"
$env:MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"
```

历史环境变量 `QWEN_BASE_URL` 仍可使用。若其值以 `/compatible-mode/v1` 结尾，Qwen QA 会自动转换成原生 SDK 所需的 `/api/v1`；同时设置两个变量时，`DASHSCOPE_BASE_HTTP_API_URL` 优先。

## 各阶段

从一个包含三级标题的 Markdown 拆分 source cases：

```bash
python scripts/pipeline.py split-source --source-md SOURCE.md
```

Author 创建 schema 4.0 case：

```bash
python scripts/pipeline.py author \
  --group classic_fairy_tale_film_conflicts \
  --source-dir dataset/source_cases \
  --case-workers 2 \
  --openrouter-workers 2 \
  --openrouter-rpm 20
```

生成带经典作品名的单一 implicit questions：

```bash
python scripts/pipeline.py questions \
  --group classic_fairy_tale_film_conflicts
```

每个语义目标只生成一个问题，不再生成 normally/usually/should 版本。`questions --force` 会替换选中 case 的问题并清空其全部 QA/judgment，因为旧结果不再对应新问题。

生成或续跑 Seedance 视频：

```bash
python scripts/pipeline.py generate \
  --group classic_fairy_tale_film_conflicts \
  --seedance-workers 3 \
  --seedance-total-workers 6
```

失败任务用 `--retry-failed` 重新创建；已提交任务会沿用 `task_id` 继续轮询。可重复传 `--video-id` 缩小范围。

记录人工审核：

```bash
python scripts/pipeline.py review \
  --case-id milk_carton_pours_orange_juice \
  --video-id v001 \
  --decision verified
```

运行 Gemini QA（默认 effort 为 `medium`）：

```bash
python scripts/pipeline.py qa \
  --qa-model google/gemini-3.1-pro-preview \
  --case-workers 2 \
  --qa-workers 3
```

运行 Qwen，可关闭或开启 thinking：

```bash
python scripts/pipeline.py qa \
  --group classic_fairy_tale_film_conflicts \
  --qa-model qwen3.8-max \
  --thinking-effort all
  --group classic_physics_chemistry_experiments \

python scripts/pipeline.py qa \
  --qa-model qwen3.8-max \
  --thinking-effort default
```

Qwen 不再把视频编码为 Base64，而是将本地绝对路径转换为 `file:///...` URI 后交给 DashScope SDK 上传。请求使用 `fps=2`，本地视频上限为 100 MiB；更大的视频应先放到 OSS 或可公开访问的 URL。

运行 Kimi K3：

```bash
python scripts/pipeline.py qa \
  --qa-model kimi-k3 \
  --case-workers 2 \
  --qa-workers 3
```

Kimi 不支持 `none`；省略 effort 或使用 `default`。`all` 对 Kimi 也只运行一次默认模式，实际 reasoning effort 是服务默认 `max`。

QA 可重复传 `--case-id`、`--video-id`、`--question-id` 和 `--thinking-effort`。请求并发上限由 `--openrouter-workers` 控制，启动速率由 `--openrouter-rpm` 控制；这两个历史参数名对 Gemini、Qwen、Kimi 都生效。

Judge 可按模型和 effort 筛选：

```bash
python scripts/pipeline.py judge \
  --group classic_fairy_tale_film_conflicts \
  --qa-model qwen3.8-max \
  --thinking-effort all
```

生成 JSON summary 和 Markdown report：

```bash
python scripts/pipeline.py summary
python scripts/pipeline.py report
```

按模型筛选：

```bash
python scripts/pipeline.py summary \
  --group classic_fairy_tale_film_conflicts \
  --qa-model qwen3.8-max \
  --thinking-effort all \
  --output results/classic_fairy_tale_film_conflicts/qwen_fairy_summary.json

python scripts/pipeline.py summary \
  --group classic_physics_chemistry_experiments \
  --qa-model qwen3.8-max \
  --thinking-effort default \
  --output results/classic_physics_chemistry_experiments/qwen_exp_default_summary.json

python scripts/pipeline.py report \
  --group classic_fairy_tale_film_conflicts \
  --qa-model qwen3.8-max \
  --output results/classic_fairy_tale_film_conflicts/qwen_fairy_report.md
```

只筛选 Gemini 且没有显式指定输出时，文件名分别为：

- `results/gemini_knowledge_conflict_summary.json`
- `results/gemini_case_results.md`

其他筛选或混合模型使用：

- `results/knowledge_conflict_summary.json`
- `results/case_results.md`

## 完整流程

```bash
python scripts/pipeline.py all --qa-model kimi-k3
```

`all` 顺序执行 author、questions、generate、qa、judge，任一阶段失败就停止。它不会执行 review、summary 或 report。
