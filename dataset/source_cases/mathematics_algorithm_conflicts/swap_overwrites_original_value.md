### Swap: Original Value Overwritten

**Case label**: M51
**Candidate number**: 20
**中文名称**: 交换算法：旧值被覆盖，两个位置变成一样
**Status**: User-approved source design; Luna prompt authoring and verification, video generation, and human qualification are pending.

- **正常知识与冲突：** 交换两个变量应保留两个原始值并对调；冲突版直接顺序赋值，丢失一个旧值。
- **画面：** 标题 SWAP。左右两个固定变量槽，初始分别为红、蓝，另有一个空暂存槽。左槽先复制右槽变蓝，接着右槽读取已变蓝的左槽，最后两槽都是蓝，暂存槽未使用。
- **正常对照：** 在相同画面内用暂存槽保存原左值，再将右值写入左槽，将暂存值写入右槽；最终左蓝、右红，暂存区清空。
- **重点：** 色块代表可复制的数据值，不是实体球；目标变量颜色的改变是预定覆盖错误。必须看清写入顺序，不能无原因变色。对照只修复缺少保存旧值的错误。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: Swapping variables initially holding red and blue must leave the left variable blue and the right variable red.
**Intended video fact (EN)**: The swap run copies right into left and then the overwritten left into right, leaving both variables blue.

**Prompt authoring**: 当前保存的是已批准的源案例设计，不是正式 Seedance 提示词。后续由 OpenRouter 上配置的 Luna 编写并核验一份冲突提示词和一份匹配的正常 control 提示词，保留本文件指定的过程、约束和完成标记。默认先仅生成冲突版 v001；control 保留供后续按需生成。

**Human review**: 色块代表可复制的数据值，不是实体球；目标变量颜色的改变是预定覆盖错误。必须看清写入顺序，不能无原因变色。对照只修复缺少保存旧值的错误。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。
