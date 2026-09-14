### Preemptive Priority: High-Priority Arrival Does Not Preempt

**Case label**: M43
**Candidate number**: 10
**中文名称**: 抢占式优先级调度：高优先级到达，却不抢占
**Status**: User-approved source design; Luna prompt authoring and verification, video generation, and human qualification are pending.

- **正常知识与冲突：** 在指定的抢占式优先级规则下，就绪的高优先级任务应抢占低优先级任务；冲突版继续执行低优先级任务。
- **画面：** 标题 PREEMPTIVE PRIORITY。LOW 任务正在唯一处理器内执行，HIGH 任务随后进入就绪区。LOW 仍继续运行到完成，HIGH 一直等待，之后才运行 HIGH。
- **正常对照：** HIGH 到达并就绪后，LOW 暂停并离开处理器，HIGH 进入执行；HIGH 完成后 LOW 恢复并完成。
- **重点：** 没有不可抢占区、锁依赖、阻塞条件或足以解释整段等待的调度延迟。HIGH 必须已就绪；两版可最终均完成，只改变调度顺序。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: Under preemptive priority scheduling, a ready higher-priority task preempts a running lower-priority task when no nonpreemptible section or blocking condition applies.
**Intended video fact (EN)**: HIGH becomes ready, but LOW continues running to completion before HIGH is allowed to execute.

**Prompt authoring**: 当前保存的是已批准的源案例设计，不是正式 Seedance 提示词。后续由 OpenRouter 上配置的 Luna 编写并核验一份冲突提示词和一份匹配的正常 control 提示词，保留本文件指定的过程、约束和完成标记。默认先仅生成冲突版 v001；control 保留供后续按需生成。

**Human review**: 没有不可抢占区、锁依赖、阻塞条件或足以解释整段等待的调度延迟。HIGH 必须已就绪；两版可最终均完成，只改变调度顺序。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。
