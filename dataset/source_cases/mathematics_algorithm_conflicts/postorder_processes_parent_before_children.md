### Postorder Traversal: Parent Processed Before Children

**Case label**: M46
**Candidate number**: 14
**中文名称**: 后序遍历：父节点先于子节点被处理
**Status**: User-approved source design; Luna prompt authoring and verification, video generation, and human qualification are pending.

- **正常知识与冲突：** 二叉树后序遍历应先处理左右子树，再处理根节点；冲突版先输出根节点。
- **画面：** 标题 POSTORDER。固定树包含根 A、左叶 B、右叶 C。处理标记先落在 A，输出区随后依次追加 A、B、C。
- **正常对照：** 处理和输出顺序为 B、C、A。
- **重点：** 明确区分进入节点与处理并输出节点。递归开始时经过根节点并非错误，提前输出根节点才是；原树保持可见，输出字符是明确允许生成的记录。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: Left-right-root postorder traversal of root A with leaf children B and C outputs B, C, A.
**Intended video fact (EN)**: The run labeled POSTORDER processes and outputs root A before either child, producing A, B, C.

**Prompt authoring**: 当前保存的是已批准的源案例设计，不是正式 Seedance 提示词。后续由 OpenRouter 上配置的 Luna 编写并核验一份冲突提示词和一份匹配的正常 control 提示词，保留本文件指定的过程、约束和完成标记。默认先仅生成冲突版 v001；control 保留供后续按需生成。

**Human review**: 明确区分进入节点与处理并输出节点。递归开始时经过根节点并非错误，提前输出根节点才是；原树保持可见，输出字符是明确允许生成的记录。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。
