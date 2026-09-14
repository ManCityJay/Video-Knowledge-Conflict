### Insertion Sort: Saved Key Never Written Back

**Case label**: M53
**Candidate number**: 25
**中文名称**: 插入排序：移动完成后忘记放回暂存元素
**Status**: User-approved source design; Luna prompt authoring and verification, video generation, and human qualification are pending.

- **正常知识与冲突：** 插入排序将较大元素右移后，必须把暂存键放入空位；冲突版省略最后写回。
- **画面：** 标题 INSERTION SORT。三个柱子初始为中、高、矮。最右矮柱移至可见暂存区，高柱和中柱依次右移，最左槽空出；矮柱仍在暂存区，系统却显示 DONE。
- **正常对照：** 在相同右移过程后，把矮柱放入最左空槽，暂存区清空，再显示 DONE。
- **重点：** 矮柱全程可见，不能凭空消失或复制。初始前两柱已按升序排列；只演示插入第三柱的这一步。DONE 后不再补写，排除尚未完成的解释。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: When inserting the held smallest key into the sorted prefix, insertion sort must write the saved key into the opened first slot after shifting larger elements right.
**Intended video fact (EN)**: The insertion-sort step shifts the larger bars right but declares DONE with the first slot empty and the smallest bar still in the temporary area.

**Prompt authoring**: 当前保存的是已批准的源案例设计，不是正式 Seedance 提示词。后续由 OpenRouter 上配置的 Luna 编写并核验一份冲突提示词和一份匹配的正常 control 提示词，保留本文件指定的过程、约束和完成标记。默认先仅生成冲突版 v001；control 保留供后续按需生成。

**Human review**: 矮柱全程可见，不能凭空消失或复制。初始前两柱已按升序排列；只演示插入第三柱的这一步。DONE 后不再补写，排除尚未完成的解释。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。
