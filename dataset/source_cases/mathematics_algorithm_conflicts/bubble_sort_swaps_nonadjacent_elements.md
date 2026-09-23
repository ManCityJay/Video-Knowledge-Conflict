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


<!-- math-expansion-20260923-start -->
#### 2026-09-23 新增 conflict 变体：数字与序列长度拓展

**批次范围**：math_expansion_20260923。本批次共 25 个新 conflict，分属 13 个现有 case；基线为 78 个 qualified conflict，全部新增视频审核合格后目标为 103 个。
**当前状态**：已按用户要求写入源案例描述；尚未为本批次生成视频或登记新 video 对象，不能计为 qualified。
**与原文的关系**：上文保留原有设计与历史记录；本节是追加的新变体。本节输入、对象数量、正常结果及冲突结果专属于以下变体，不沿用上文旧版本的具体数字、三/四槽限制或版本总数。
**编号说明**：以下 M 编号仅是本次 25 条方案的索引，不是上文历史 Case label，也不是正式 video_id；跨文件以 `math_expansion_20260923/Mxx` 唯一标识。落地时另行检查现有记录、归档与输出路径后分配 video_id。

##### 新增变体 M05

**拓展方式**：换数字。
**初始状态、动作与冲突终态**：输入 `[8,5,2]`，标题 BUBBLE SORT；8 和 2 直接跨过静止的 5 交换，一步得到 `[2,5,8]`。完整展示交换路径。
**正常规则及结果**：冒泡排序只能交换相邻元素；即使最终有序，直接交换首尾也违反规则。

##### 新增变体 M06

**拓展方式**：原始数列增加两个元素。
**初始状态、动作与冲突终态**：输入 `[9,3,5,7,1]`；9 与 1 跨过三个静止中间元素直接交换，得到 `[1,3,5,7,9]`。
**正常规则及结果**：只能进行相邻交换，不能直接交换第 1、5 位。

**本批次共用画面要求**：使用固定镜头的简洁二维教学图，完整展示初始输入、操作名和必要的有序动作；数字、卡片身份及非目标元素始终保持不变。最后显示中性 DONE 并保持冲突结果，不在画面中展示正常答案或对错判定。
**可见证据**：数组从左到右、栈从底到顶、堆按层序描述；队列 FRONT/REAR、栈 TOP、BST 左右与树的边必须清楚。冒泡排序完整展示非相邻交换；滑动窗口保留处理记录且不登记被跳过窗口；插入排序保留 TEMP 与空槽；栈和队列不自动压缩空槽。
**形式规则**：归并案例展示完整归并排序中的子列排序被跳过，随后头元素比较与输出顺序保持一致；稳定排序只按数字键比较，身份标签不参与比较；循环为无条件每次画一点，不含 break、擦除或重叠绘点；FIFO 命中是读取，不是删除后重插。
**后续数据接入**：每条新增视频保存自己的 variant_context.conflict_spec 与 questions，并据新输入生成匹配首帧；不得继承旧数字的参考答案。正常结果用于事实核对与正常参考答案，本批次仅新增 conflict 视频。每条视频生成后仍需单独审核，合格后才计入目标。
<!-- math-expansion-20260923-end -->
