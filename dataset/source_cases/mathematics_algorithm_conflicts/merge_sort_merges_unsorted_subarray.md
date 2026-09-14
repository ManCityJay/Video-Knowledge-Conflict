### Merge Sort: Merge Starts Before a Subarray Is Sorted

**Case label**: M39
**Candidate number**: 03
**中文名称**: 归并排序：子段尚未有序，就开始归并
**Status**: User-approved source design; Luna prompt authoring and verification, video generation, and human qualification are pending.

- **正常知识与冲突：** 标准归并步骤要求输入子段已经有序；冲突版跳过左子段排序，提前执行归并。
- **画面：** 左段为 [3,1]，右段为 [2,4]，下方为空输出区。标题 MERGE SORT。冲突版保持左段乱序，直接从两段头部选较小值，依次输出 2、3、1、4。
- **正常对照：** 先将左段排成 [1,3]，再按相同的头部比较归并规则输出 1、2、3、4。
- **重点：** 只改变是否先完成子段排序，归并阶段本身不再加入第二种错误。输出元素应从来源位置移出，保持四个数据元素可追踪。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: The standard merge step of merge sort combines already-sorted subarrays; sorting [3,1] before merging with [2,4] yields [1,2,3,4].
**Intended video fact (EN)**: The merge-sort run skips sorting [3,1], merges it with [2,4] by head comparison, and finishes with [2,3,1,4].

**Prompt authoring**: 当前保存的是已批准的源案例设计，不是正式 Seedance 提示词。后续由 OpenRouter 上配置的 Luna 编写并核验一份冲突提示词和一份匹配的正常 control 提示词，保留本文件指定的过程、约束和完成标记。默认先仅生成冲突版 v001；control 保留供后续按需生成。

**Human review**: 只改变是否先完成子段排序，归并阶段本身不再加入第二种错误。输出元素应从来源位置移出，保持四个数据元素可追踪。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。
