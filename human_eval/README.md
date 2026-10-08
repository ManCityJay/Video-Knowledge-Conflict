# 人工评测

两项任务分开，人工都只提交一个 answer：

- /qa：播放 conflict 视频，阅读 question 和提示词，填写回答。
- /judge：只查看原 LLM Judge 的文本输入（question、final_answer、video_role、正常事实、预期视频事实、两类参考答案、system 判定规则及输出格式），选择一个判定答案。

两项任务互不依赖，没有登录步骤、解锁要求、理由、时间戳、问题类型、二次人工归类或复核表单。页面自动保存草稿；提交后进入下一条。页面顶部显示“当前评测者”。填写姓名或编号，点击“使用此编号”切换并恢复该编号的进度；换浏览器也可以输入同一编号。首次把旧随机编号改为姓名，点击“将当前进度改名”，草稿、提交和评分一起迁移。目标编号已有记录时禁止覆盖或合并。姓名/编号是进度标识，不是身份认证，请勿多人共用。保留旧版本已有 ID 和答案，不清空数据库。

## 启动

在项目根目录运行：

    python -m human_eval.app --run human_eval/runs/audit_20260929_four_groups

分别打开：

- http://127.0.0.1:8765/qa
- http://127.0.0.1:8765/judge

输入信息完整保留，长的提示词和上下文可展开查看。QA 的参考答案不显示。Judge 不展示视频、raw_answer、答题模型的输入或模型名称，也不在提交后展示 LLM 结论；完整原始文本输入可展开查看。新提交标记 llm_judge_text_only，历史 full_materials 记录保留原口径。已有80条Judge是在旧口径下完成，不会自动变为同输入实验结果；如需重测，请用新评测者编号保留独立进度。

## 抽样

只有四个正式 group：童话影视、物理化学、数学算法、日常常识。fairy_based_on_video 不纳入默认范围。两项任务各抽每组 20 条 QA，共各 80 条。

    python -m human_eval.prepare --run human_eval/runs/new_audit

QA 单位为 group/case/video/question；视频私有问题优先使用 variant_context。固定种子、无放回、两项任务独立抽样。Judge 从已有模型回答的 QA 并集中抽样，每条 QA 固定选择一个已有模型回答，每组 20 项，四组共 80 项。固定种子在材料可用的模型条件中选择，不根据答案或 verdict 挑选；同条件使用最新结果，不回退旧结果。可通过 config.json 中 judge_models / judge_efforts 等限制需要检查的模型。

同条件取最新模型结果，不根据答案或 verdict 挑选。缺失记录仍保留在样本清单和报告，页面不要求给缺失材料填答案。默认 scope 与现有 pipeline 相同。已有 run 禁止覆盖。

旧批次使用以下命令启用每 QA 一个回答（原始任务、视频和所有人工记录保留，报告也采用新口径）：

    python -m human_eval.select_judge --run human_eval/runs/audit_20260929_four_groups

选择清单保存在 judge_selection.json，重复执行不重新抽取。旧版其他模型回答的记录留在数据库中，不计入新的 80 项报告。

## 后台统计

人工只填 answer，统计在页面外进行。Judge 直接与已有 LLM 标签比较：

    python -m human_eval.report --run human_eval/runs/audit_20260929_four_groups

输出分开的 qa_report.md、judge_report.md，以及 qa_answers.jsonl、judge_answers.jsonl、CSV、混淆矩阵和分歧清单。所有结果位于 run 的 reports/all 中。多人按各自 ID 分开报告。

QA 回答与参考答案规范化后完全相同时，可离线自动评分；其余开放回答保留为待评分，不冒充正确。需要语义评分时，单独执行：

    python -m human_eval.score --run human_eval/runs/audit_20260929_four_groups --backend llm
    python -m human_eval.report --run human_eval/runs/audit_20260929_four_groups

该命令复用已有 judge rubric 和项目默认 judge 模型，需要 OPENROUTER_API_KEY，会调用模型 API 并产生成本；网页、prepare 和 report 本身不调用模型。后台评分与人类原始答案分开保存，报告明确是自动评分，不是人工标签。默认 score 的 references 模式不会调用网络。每组 20 条抽查不证明总体错误概率为零。

## 数据和代码

全部代码在 human_eval/，不接入或修改 pipeline。case、视频和模型结果只读。SQLite 保留答案，冻结包含视频字节、问题、完整输入、参考、模型结果、源码快照及 SHA-256。

历史记录没有原始 HTTP 请求体和模型实际采样后的帧，所以消息按源码和元数据重建；页面展示发送的视频、完整提示词及已知采样参数，不能声称精确还原供应商内部的帧。过期 fingerprint 会报错，旧记录没有 fingerprint 时保留提示。

## 检查

    python -m unittest human_eval.test_human_eval -v
    python -m human_eval.browser_check --run human_eval/runs/audit_20260929_four_groups

浏览器检查额外需要本机已有 Playwright 和 Microsoft Edge，模拟答案仅写入自动清理的临时副本。
