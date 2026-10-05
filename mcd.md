# Video Knowledge Conflict

视频知识冲突实验框架，用于分析视频问答模型如何处理画面事实与已有知识的冲突。
主评测流水线的命令和运行规则见 [pipeline.md](pipeline.md)，实验设计与数据结构见
[plan.md](plan.md)。

## Contrastive decoding（MCD v1）

Cosmos 视频／纯文本对比解码实验入口、测试和依赖位于 `scripts/mcd_v1/`，
使用独立 Transformers 环境，支持单题对比和小规模配对批量试跑。

方法公式、环境准备、运行命令、断点续跑和验收范围见
[MCD v1 README](scripts/mcd_v1/README.md)。

## 本次代码修改（2026-10-05）

### 目录整理

MCD 的单题入口、批量入口、解码实现、结果写入、测试、依赖与说明统一放到
`scripts/mcd_v1/`。原有文件迁移如下，运行命令使用新路径：

| 原路径 | 新路径 |
| --- | --- |
| `scripts/run_mcd_v1.py` | `scripts/mcd_v1/run_mcd_v1.py` |
| `scripts/test_mcd_v1.py` | `scripts/mcd_v1/test_mcd_v1.py` |
| `scripts/vconflict_pipeline/mcd_v1.py` | `scripts/mcd_v1/decoding.py` |
| `requirements-mcd-v1.txt` | `scripts/mcd_v1/requirements.txt` |
| `MCD_V1.md` | `scripts/mcd_v1/README.md` |

新增批量入口 `scripts/mcd_v1/run_mcd_v1_batch.py`、批量测试
`scripts/mcd_v1/test_mcd_v1_batch.py` 和结果写入模块 `scripts/mcd_v1/storage.py`。
共享题目提示词和 case 路径约束继续复用 `scripts/vconflict_pipeline/`；
解码公式与两路共享生成历史的逻辑保持原实现。

### MCD 功能与修复

- 视频预处理显式使用 PyAV，沿用模型处理器自己的抽帧回调；只修改处理器副本，
  避免影响复用的原处理器及其他调用。
- 答案解析支持末尾行内的 `Final answer:`，记录格式警告与解析器版本。
  当前解析器还将 EOS 结束、非空且缺少答案标记的完整响应保留为
  `evaluation_answer`，标记 `format_fallback` 和人工审核要求；`final_answer`
  保持为空并保留解析错误。截断或不完整的 think 标签仍保留异常状态。
- 批量实验复用一个模型顺序执行，默认冻结两组各 5 个 conflict 问题，配对相同问题的
  control，并对相同视频路径和问题的 control 去重。排除变体、人工拒绝的视频，
  以及带 `based` 指令或作品名前缀的历史回答；待人工审核的视频会记录审核状态。
- 每个样本重新生成 baseline 与 MCD 回答，保存原始文本、token、耗时和状态；
  参考答案只用于报告，不进入模型提示词。
- 续跑检查模型参数、manifest 和代码指纹；指纹补充共享提示词、路径与写入代码。
  已有结果缺少 `config.json` 时拒绝混用；失败或截断结果也会保留。
- 结果 JSON 使用原子写入并禁止覆盖，派生报告使用原子替换，减少中断留下不完整文件的风险。
- `lambda=0` 的 token 一致性检查失败时，批量报告也标记失败；报告区分
  `ok`、`format_fallback`、`truncated`、`failed` 和 `pending`。
- 测试使用临时目录，不再依赖本地已有的 `videos/seedance/` 数据目录。

目录迁移与修复改变了代码指纹，原实验目录会拒绝续跑。重跑相同样本时，
创建新结果目录并只复制原 `manifest.json`。

### 服务脚本与本地文件

- Cosmos 启动脚本支持通过环境变量调整 GPU、TP、并发、显存预算、地址和端口，
  支持追加 vLLM 参数，并恢复脚本执行权限。
- 新增 `scripts/start_gemma4_vllm.sh`：默认双卡、BF16、32K 上下文、端口 8001，
  支持模型版本固定、命令预览和纯文本模式。Gemma QA 尚未接入主流水线。
- `.gitignore` 增加 `/vllm` 和 `/human_eval/`，忽略本地部署记录与人工评估文件。

### 验证情况

当前 24 个单元测试通过，覆盖解码公式、共享生成历史、RoPE 状态恢复、答案解析、
control 去重、模型复用、续跑保护和原子写入：

```bash
python -m unittest discover -s scripts/mcd_v1 -p 'test_mcd_v1*.py'
```

本次审查还通过真实 case 抽样、真实视频 PyAV 预处理及启动脚本参数检查；
视频提示词 token 数和网格尺寸与已有 GPU 结果一致。
整批新版 GPU 推理、视频人工审核与方法效果评估仍需完成。
