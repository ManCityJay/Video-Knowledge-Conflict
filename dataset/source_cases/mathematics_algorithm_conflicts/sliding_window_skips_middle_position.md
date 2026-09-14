### Sliding Window: Middle Position Skipped

**Case label**: M52
**Candidate number**: 23
**中文名称**: 滑动窗口：跳过一个应检查的位置
**Status**: User-approved source design; Luna prompt authoring and verification, video generation, and human qualification are pending.

- **正常知识与冲突：** 宽度为二、步长为一的窗口应逐位置扫描；冲突版一次移动两格，漏掉中间窗口。
- **画面：** 四张固定卡 A、B、C、D，标题 SLIDING WINDOW，并固定标注 STRIDE 1。窗口先包住 AB 并完成扫描，随后直接跳到 CD 扫描并结束。
- **正常对照：** 窗口依次在 AB、BC、CD 停稳并完成扫描，然后结束。
- **重点：** 窗口宽度固定为二。扫描只在停稳后发生，移动途中经过 BC 不算扫描；必须用一致的短暂停顿或扫描脉冲区分经过和处理。两版最终窗口均位于 CD。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: A width-two sliding window with stride one over A, B, C, D processes AB, BC, and CD in order.
**Intended video fact (EN)**: The stride-one sliding-window run processes AB and then CD, skipping BC before finishing.

**Prompt authoring**: 当前保存的是已批准的源案例设计，不是正式 Seedance 提示词。后续由 OpenRouter 上配置的 Luna 编写并核验一份冲突提示词和一份匹配的正常 control 提示词，保留本文件指定的过程、约束和完成标记。默认先仅生成冲突版 v001；control 保留供后续按需生成。

**Human review**: 窗口宽度固定为二。扫描只在停稳后发生，移动途中经过 BC 不算扫描；必须用一致的短暂停顿或扫描脉冲区分经过和处理。两版最终窗口均位于 CD。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。
