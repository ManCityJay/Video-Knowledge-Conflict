### Recursion: Parent Finishes Before a Required Child Returns

**Case label**: M40
**Candidate number**: 04
**中文名称**: 递归任务：子调用未返回，父调用已经结束
**Status**: User-approved source design; Luna prompt authoring and verification, video generation, and human qualification are pending.

- **正常知识与冲突：** 对于同步等待两个必要子调用结果的递归任务，父调用不能提前完成；冲突版在一个子调用仍运行时宣布完成。
- **画面：** 上方一个父任务，下方两个子任务。左侧先完成并向父任务返回结果；右侧进度条仍在运行，上方父任务已显示 DONE，右侧随后才完成。
- **正常对照：** 父任务保持等待，直到两个子任务都完成并返回结果，才显示 DONE。
- **重点：** 明确是等待两个返回值的同步递归调用，不是异步启动后立即返回。父任务提前显示 DONE 是唯一冲突；此处任务级 DONE 有意早于整体演示结束，不得把它自动推迟修正。整体演示用 FINISHED 表示最终静止阶段。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 父任务的 DONE 是被观察的任务状态：冲突版有意在右子调用返回前出现，对照版等两个子调用返回后出现。两版均在第 4 秒显示独立的整体 FINISHED，之后保持所有最终状态至第 5 秒；整体结束标记不代表正确性。

**Normal fact (EN)**: A synchronous recursive parent that requires both child results can finish only after both child calls return.
**Intended video fact (EN)**: The parent displays DONE after the left child returns while the required right child is still running; the right child returns later.

**Prompt authoring**: 当前保存的是已批准的源案例设计，不是正式 Seedance 提示词。后续由 OpenRouter 上配置的 Luna 编写并核验一份冲突提示词和一份匹配的正常 control 提示词，保留本文件指定的过程、约束和完成标记。默认先仅生成冲突版 v001；control 保留供后续按需生成。

**Human review**: 明确是等待两个返回值的同步递归调用，不是异步启动后立即返回。父任务提前显示 DONE 是唯一冲突；此处任务级 DONE 有意早于整体演示结束，不得把它自动推迟修正。整体演示用 FINISHED 表示最终静止阶段。 父任务的 DONE 是被观察的任务状态：冲突版有意在右子调用返回前出现，对照版等两个子调用返回后出现。两版均在第 4 秒显示独立的整体 FINISHED，之后保持所有最终状态至第 5 秒；整体结束标记不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。
