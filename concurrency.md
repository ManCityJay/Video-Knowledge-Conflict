# QA/Judge 并发与同机多命令运行

`qa-judge` 以一次模型请求为调度单位。每条回答落盘后立即判分，每层 filter
通过后立即释放该题的下游，不等待其他 case、视频或题目。独立 question-only
执行 QA → Judge；`--filter-only` 不运行目标 QA。

```text
question-only filter QA → Judge → control filter QA → Judge → 目标 QA → Judge
                          通过                        通过
```

## 参数

| 参数 | 默认 | 范围 |
|---|---|---|
| `--qa-concurrency` | 云端 24，Cosmos 8，Gemma 4 | 当前命令，filter 和主 QA 合计 |
| `--judge-concurrency` | 24 | 当前命令，filter 和主 Judge 合计 |
| `--qa-service-concurrency` | 云端 24，Cosmos 8，Gemma 4 | 同一 QA 服务，跨命令共享 |
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
复用其结果。共享 filter 按 case/question scope、题目、模型、effort、prefix
及来源隔离；私有变体不能跨 scope 复用。

新执行的独立 question-only 回答也写入已有的 `filter_stage` / `filter_fingerprint`
元数据，使其与相同输入的共享 filter 可以复用同一次请求和判断。没有这些来源
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

普通 video/description `--force-qa` 只清理选中且通过 filter 的目标 QA/Judge；
`--force-judge` 只清空相同范围的 judgment。两者均不清理 control 或 question-only
filter，也不清理未通过题目的历史。

执行顺序是先准备 filter，再预检和统一清理主实验结果。Filter 缺失、过期或
未判分时可能先调用模型；禁止在全部清理写回成功前开始的是**主实验请求**。
清理不是跨文件事务，失败后可能已有部分 case 清理完成，但不会混入新主实验结果。

独立 `--input question_only` force 清理所选 question-only 结果。
`--filter-only` force 单独强制重跑/重判 filter，保留历史，第二层仍取决于第一层新判定。

## 调度、媒体与报告

每个进程有 QA、Judge 两个请求池及最多两个媒体准备线程。池内 filter/主实验
按 3:1 加权轮转，按 case 公平取任务；QA/Judge 竞争 OpenRouter 时交替准入。
主 Judge 积压预算为 `max(64, 4 × judge_concurrency)`，主 QA 预留预算后才派发，
filter 链仍可推进。已有有效结果直接满足依赖，不计入本次实际请求数。

只有满足所有额度的任务才进入网络线程。每次重试重新计入 RPM，退避保存在
协调器的时间队列，不占请求线程。保持原有重试分类、次数和退避策略；429 会
更新对应服务的共享冷却时间。格式错误、截断、缺少 final answer 不增加语义重试。

进程内相同视频内容只准备一份可复用编码。闲置 Base64 缓存采用 512 MiB LRU，
在途请求持有的对象可以超过该缓存容量，因此它不是进程内存上限。不改变 Qwen
上传、本地视频 URI、采样或 SHA-256 新鲜度检查。

`summarize` 共享登记以阻止 force，然后按路径顺序锁定选中 case、并行读取完整
快照并释放锁。期间网络请求仍可继续，写回短暂等待。各 effort JSON 和 Markdown
复用同一快照及来源/gate 校验。与 QA 同时运行时，报告反映快照时刻，可能尚未完成；
不自动等待整批 QA，也不自动串联 summarize。

每 10 秒打印本进程待处理、在途、等待其他进程、重试、实际请求和完成速率，
并显示共享服务占用与等待时间。保留原有三组 QA 诊断、最终完成统计和非零退出规则。
