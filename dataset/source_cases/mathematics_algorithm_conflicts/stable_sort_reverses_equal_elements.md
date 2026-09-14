### Stable Sort: Equal Elements Reverse Relative Order

**Case label**: M38
**Candidate number**: 02
**中文名称**: 稳定排序：相等元素颠倒先后
**Status**: User-approved source design; Luna prompt authoring and verification, video generation, and human qualification are pending.

- **正常知识与冲突：** 稳定排序保持相等键值元素的原始相对顺序；冲突版排序后颠倒两个等高柱的先后。
- **画面：** 标题 STABLE SORT。初始为红色高柱、绿色矮柱、蓝色高柱，红蓝严格等高。排序后成为绿色、蓝色、红色。
- **正常对照：** 绿色矮柱移到最左，红色高柱仍在蓝色高柱之前，最终为绿色、红色、蓝色。
- **重点：** 柱高和颜色全程不变。错误来自红蓝元素的身份次序，不得通过改变柱高制造普通排序错误。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: A stable ascending sort preserves the original relative order of the equal-height red and blue bars.
**Intended video fact (EN)**: The stable-sort run places the blue bar before the equal-height red bar although red originally preceded blue; the final heights are still sorted.

**Prompt authoring**: 当前保存的是已批准的源案例设计，不是正式 Seedance 提示词。后续由 OpenRouter 上配置的 Luna 编写并核验一份冲突提示词和一份匹配的正常 control 提示词，保留本文件指定的过程、约束和完成标记。默认先仅生成冲突版 v001；control 保留供后续按需生成。

**Human review**: 柱高和颜色全程不变。错误来自红蓝元素的身份次序，不得通过改变柱高制造普通排序错误。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。
