### Bubble Sort: Nonadjacent Elements Swapped

**Case label**: M37
**Candidate number**: 01
**中文名称**: 冒泡排序：直接交换不相邻元素
**Status**: User-approved source design; Luna prompt authoring and verification, video generation, and human qualification are pending.

- **正常知识与冲突：** 冒泡排序通过相邻元素的比较和交换推进排序；冲突版直接交换隔着一个元素的最高柱与最矮柱。
- **画面：** 标题 BUBBLE SORT，三个柱子按高、中、矮排列。启动后，两端柱子直接越过中间柱交换，变成矮、中、高，随后结束。
- **正常对照：** 采用从左向右比较的升序冒泡排序，依次交换第一、二位置，再交换第二、三位置，下一轮交换第一、二位置，得到同样的升序结果。
- **重点：** 两版最终排列相同。冲突必须是一次非相邻交换，不能生成成若干次相邻交换；柱高和身份不变。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: Standard ascending bubble sort exchanges adjacent elements only.
**Intended video fact (EN)**: The run labeled BUBBLE SORT directly swaps the nonadjacent tallest and shortest bars across the middle bar, then finishes with the bars in ascending order.

**Prompt authoring**: 当前保存的是已批准的源案例设计，不是正式 Seedance 提示词。后续由 OpenRouter 上配置的 Luna 编写并核验一份冲突提示词和一份匹配的正常 control 提示词，保留本文件指定的过程、约束和完成标记。默认先仅生成冲突版 v001；control 保留供后续按需生成。

**Human review**: 两版最终排列相同。冲突必须是一次非相邻交换，不能生成成若干次相邻交换；柱高和身份不变。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。
