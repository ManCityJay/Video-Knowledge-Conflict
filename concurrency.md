# QA/Judge 并发与同机多命令运行

`qa-judge` 以一次模型请求为调度单位。每条回答落盘后立即判分，不等待其他
case、视频或题目。Video、control、description 和 question-only 四种输入独立
执行 QA → Judge，目标实验没有 question-only 或 control filter 前置依赖。
`--filter-only` 已删除；需要 question-only 时显式选择 `--input question_only`。

```text
所选输入 QA → Judge
```

## 参数

| 参数 | 默认 | 范围 |
|---|---|---|
| `--qa-concurrency` | 云端 24，Cosmos 8，Gemma 4，Qwen27B 1 | 当前命令的所选输入 QA |
| `--judge-concurrency` | 24 | 当前命令的所选输入 Judge |
| `--qa-service-concurrency` | 云端 24，Cosmos 8，Gemma 4，Qwen27B 1 | 同一 QA 服务，跨命令共享 |
| `--qa-rpm` | 云端 20，本地 0 | 同一 QA 模型，跨命令共享 |
| `--judge-rpm` | 20 | Judge 模型，跨命令共享 |
| `--openrouter-concurrency` | 24 | 所有 OpenRouter 请求，跨命令共享 |
| `--openrouter-rpm` | 20 | 所有 OpenRouter 请求，跨命令共享 |
| `--summary-workers` | 4 | 仅 summarize，并行读取 case |

RPM 为 0 表示不增加该项速率限制，仍受其他适用限制约束。并发必须为正整数。
Gemini QA 与 Judge 共同占用 OpenRouter 总额度，不能把两个池的并发直接相加。
Qwen、Kimi、本地 QA 不占用 OpenRouter 额度。本地并发是客户端在途上限，
不是 vLLM `max-num-seqs`，不会自动增加 GPU 的推理容量。

`qa-judge` 不再接受 `--case-workers`、`--qa-workers`、`--cosmos-workers`、
`--gemma-workers`、`--openrouter-workers`，错误信息会提示替代参数。
此前的 author/questions/description 等 stage 保留原来的 workers 参数。

```bash
python scripts/pipeline.py qa-judge --group classic_fairy_tale_film_conflicts \
  --input video --qa-model gemini \
  --qa-concurrency 24 --judge-concurrency 24 \
  --qa-service-concurrency 24 --openrouter-concurrency 24 \
  --qa-rpm 20 --judge-rpm 20 --openrouter-rpm 20

python scripts/pipeline.py summarize --group classic_fairy_tale_film_conflicts \
  --input video --qa-model gemini --summary-workers 4
```

提高并发不会绕过 RPM。如果 20 RPM 已经饱和，更多线程不能提高启动速率。
服务额度需要按实际配额设置，本实现不会自动提高并发或 RPM。

## 多命令、结果合并与恢复

同一机器、同一工作区内，多个普通命令可以同时处理同一 case，包括不同模型、
effort 和 video/description 条件。同一任务只有一个认领者，其他命令等待并
复用其结果。任务按 case/question scope、题目、模型、effort、输入及来源隔离，
目标 QA 还区分 based/prefix 条件；question-only 不含这两种条件。
共享题目按 case scope 去重，私有变体不能跨视频 scope 复用；question-only
只遍历 conflict 视频的有效问题并遵循 `question_ids`，不要求 ready 或媒体文件。

新执行的独立 question-only 回答也写入已有的 `filter_stage` / `filter_fingerprint`
元数据，供独立续跑和可选报告筛选复用同一次请求和判断。没有这些来源
字段的历史回答不迁移；原有兼容和过期检查仍然适用。

协调状态保存在 `artifacts/pipeline_runtime/coordination.sqlite3`，使用 SQLite
WAL 和操作系统文件锁。数据库只保存认领、运行登记、服务额度和状态，不保存
答案副本；case JSON 始终是实验结果的权威来源。写回过程为：

1. 短暂取得 case 文件锁，重新读取最新 JSON。
2. 校验任务归属、输入来源及被判分回答的身份。
3. 仅合并当前回答或 judgment，原子替换文件。
4. 确认协调状态，释放锁并唤醒下游。

模型请求、退避和媒体准备都不持有 case 锁或 SQLite 写事务。旧的整 case
内存快照不会覆盖其他命令的结果。

运行每 5 秒更新心跳，但心跳超时不会单独触发抢占；只有原进程生命周期锁
释放后才回收任务。原进程崩溃后，先检查 JSON 是否已有结果，再决定是否重做。
故障发生在远端成功而结果尚未落盘之间时，仍可能重复调用模型，不能保证远端
请求恰好执行一次。崩溃进程的请求额度保守保留到该 attempt 的超时截止。
失败状态由当前订阅该任务的命令共享，防止等待者依次重新尝试；全部订阅者
退出后，后续运行可以再次尝试。

云端服务按 endpoint 和不泄露密钥的凭据指纹分组，本地服务按 endpoint 分组。
同一共享额度的配置必须一致；后启动的命令配置冲突时，在模型请求前报错。
进程内 QA/Judge 并发可以不同。没有活跃使用者及遗留请求预留后，可以重新配置。
同一服务的活跃命令轮转准入，空闲命令不保留份额。

不得在有命令运行时删除协调数据库或锁目录。此机制不协调旧版 pipeline、
其他修改输入的 stage、外部编辑器、不同工作区或跨机器/共享网络盘运行。

## Force

所有 force 命令在任何模型请求或清理之前，一次性独占登记全部所选 case。
只要与其他 QA、force 或 summarize 重叠，就明确报错，不部分登记或排队等待。

Video/control/description `--force-qa` 清理选中输入、模型、effort、based/prefix
条件的目标 QA/Judge；`--force-judge` 只清空相同范围的 judgment。两者均不先运行
question-only，其结果缺失、过期、未判分或判错均不缩小目标集合；其他输入、
question-only 及其他 based/prefix 条件保留。

执行顺序是对所选输入预检，再统一清理结果，全部清理写回成功后才开始
QA/Judge 请求。清理不是跨文件事务，失败后可能已有部分 case 清理完成，
但不会混入新实验结果。

独立 `--input question_only` force 清理所选 conflict 有效共享/私有题目的对应
模型和 effort 的 question-only 结果或 judgment，保留原有容器和指纹算法。

## 调度、媒体与报告

每个进程有 QA、Judge 两个请求池及最多两个媒体准备线程。所选输入的任务
在池内按 case 公平轮转；QA/Judge 竞争 OpenRouter 时交替准入。
主 Judge 积压预算为 `max(64, 4 × judge_concurrency)`，主 QA 预留预算后才派发，
独立 question-only 直接执行自身 QA/Judge。已有有效结果直接复用，不计入本次实际请求数。

只有满足所有额度的任务才进入网络线程。每次重试重新计入 RPM，退避保存在
协调器的时间队列，不占请求线程。保持原有重试分类、次数和退避策略；429 会
更新对应服务的共享冷却时间。正常结束但缺少有效末行 `Final answer:`（含空正文
或只有 reasoning）时，全部 QA 模型在所选四种输入中均恢复一次。云端完整重试
原请求，输入、提示词和生成参数不变，不增加纠错提示或历史回答。

Cosmos、Gemma 和本地 Qwen 使用 assistant 续写；首次返回 `length` 或 `max_tokens`
也在记录截断日志和计数后进入同一恢复流程。保留原 system/user、媒体、采样参数和
完整正文及独立 reasoning，追加 assistant 消息并以 `\nFinal answer:` 结尾。
续写设置 `continue_final_message=true`、`add_generation_prompt=false`、`echo=false`、
`max_tokens=256`，移除 `thinking_token_budget`，不裁剪输入或首次回答；上下文不足
直接报错。云端截断和全部模型的判分错误不触发答案恢复。

需要恢复时先释放本次 permit，保持原任务认领和下游依赖；原任务重新进入同一
调度队列，通过归属检查并重新申请全部共享并发及 RPM 额度后才能发起重试。
`final_answer_retry_count` 最多为 1；`network_retry_count` 独立遵循 `--max-retries`，
不会因答案恢复清零或耗用。截断与缺失答案共享一次恢复额度；续写网络重试重发
同一续写请求。第二次有效才写入 QA 并释放 Judge；续写为空、格式无效或再次截断
则共享该任务失败状态，不保存成功 QA，不执行下游。已有有效历史结果仍直接复用。

进程内相同视频内容只准备一份可复用编码。闲置 Base64 缓存采用 512 MiB LRU，
在途请求持有的对象可以超过该缓存容量，因此它不是进程内存上限。不改变 Qwen
上传、本地视频 URI、采样或 SHA-256 新鲜度检查。

`summarize` 共享登记以阻止 force，然后按路径顺序锁定选中 case、并行读取完整
快照并释放锁。期间网络请求仍可继续，写回短暂等待。各 effort JSON 和 Markdown
复用同一快照及来源校验；仅 `--filter passed` 启用 question-only gate 筛选，
只读取有效已有判定，不补跑模型。与 QA 同时运行时，报告反映快照时刻，可能尚未完成；
不自动等待整批 QA，也不自动串联 summarize。

运行时打印保存及重试信息，结束时统计所选输入的全部目标完成数、实际请求、
保存、缓存复用和跨进程复用数；不再打印执行准入 gate 统计。
`main`、`question_only` 两组 QA 诊断另显示 `final_answer_retries`、
`final_answer_retry_recovered`、`final_answer_retry_failed`，分别表示安排答案恢复的任务数、
重试后成功落盘数和最终失败数（包括重试后耗尽网络额度等失败）。保留最终完成统计
和非零退出规则。本地首次截断只计 `max_tokens_truncated`，不计 `missing_final_answer`；
续写截断只计 `final_answer_continuation_max_tokens_truncated`，同时计任务恢复失败。
