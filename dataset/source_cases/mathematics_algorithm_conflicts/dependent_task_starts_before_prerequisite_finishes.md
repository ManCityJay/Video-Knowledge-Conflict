### Dependency Scheduling: Successor Starts Before Prerequisite Finishes

**Case label**: M42
**Candidate number**: 07
**中文名称**: 拓扑调度：前置任务未完成，后继已经启动
**Status**: User-approved source design; Luna prompt authoring and verification, video generation, and human qualification are pending.

- **正常知识与冲突：** 在完成依赖 A → B 下，B 必须等待 A 完成；冲突版提前启动 B。
- **画面：** 两张任务卡以固定箭头 A → B 连接。A 的进度条正在增长，尚未到终点时 B 的进度条也开始增长。最后两者都完成。
- **正常对照：** A 进度条走完并显示任务完成后，B 才开始执行。
- **重点：** 箭头明确表示完成后才能启动的依赖，不是数据流的部分可用关系。结尾可以相同，必须保留中途重叠执行的证据。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: With a finish-to-start dependency A -> B, task B can start only after A has finished.
**Intended video fact (EN)**: Task B starts executing while its prerequisite A is still running; both tasks eventually finish.

**Prompt authoring**: 当前保存的是已批准的源案例设计，不是正式 Seedance 提示词。后续由 OpenRouter 上配置的 Luna 编写并核验一份冲突提示词和一份匹配的正常 control 提示词，保留本文件指定的过程、约束和完成标记。默认先仅生成冲突版 v001；control 保留供后续按需生成。

**Human review**: 箭头明确表示完成后才能启动的依赖，不是数据流的部分可用关系。结尾可以相同，必须保留中途重叠执行的证据。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。
