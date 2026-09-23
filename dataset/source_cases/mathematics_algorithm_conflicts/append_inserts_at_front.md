### APPEND: New Item Added at the Front

**Case label**: M16
**Status**: Selected design; prompts prepared for user-run generation. Video generation and human qualification are pending.

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: Appending 8 to the list [2, 5] produces [2, 5, 8].
**Intended video fact (EN)**: The completed APPEND 8 operation produces [8, 2, 5].

**Video prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. The title reads "APPEND 8". In the center, two equal-size number cards form a horizontal row reading 2, 5 from left to right. One separate card labeled 8 is above that row. There are exactly three cards in the whole frame. Hold the initial state during seconds 0-1. During seconds 1-2.8 move cards 2 and 5 together to the right, preserving their order and spacing, while card 8 moves smoothly into the newly opened LEFTMOST position. The completed row reads 8, 2, 5 with equal spacing. Every card and its digit move as one rigid object. Keep the title unchanged, preserve the relative order of 2 and 5, and never duplicate, remove, rotate, or change a card. No further reordering after placement. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Control prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. The title reads "APPEND 8". In the center, two equal-size number cards form a horizontal row reading 2, 5 from left to right. One separate card labeled 8 is above that row. There are exactly three cards in the whole frame. Hold the initial state during seconds 0-1. During seconds 1-2.8 keep cards 2 and 5 in their original order and move card 8 smoothly from above to the position immediately RIGHT of card 5. The completed row reads 2, 5, 8 with equal spacing. Every card and its digit move as one rigid object. Keep the title unchanged, preserve the relative order of 2 and 5, and never duplicate, remove, rotate, or change a card. No further reordering after placement. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Human review**：列表初始为 2、5，新卡片为 8；2 和 5 的相对顺序不变，卡片不复制、不消失，DONE 后停止。


<!-- math-expansion-20260923-start -->
#### 2026-09-23 新增 conflict 变体：数字与序列长度拓展

**批次范围**：math_expansion_20260923。本批次共 25 个新 conflict，分属 13 个现有 case；基线为 78 个 qualified conflict，全部新增视频审核合格后目标为 103 个。
**当前状态**：已按用户要求写入源案例描述；尚未为本批次生成视频或登记新 video 对象，不能计为 qualified。
**与原文的关系**：上文保留原有设计与历史记录；本节是追加的新变体。本节输入、对象数量、正常结果及冲突结果专属于以下变体，不沿用上文旧版本的具体数字、三/四槽限制或版本总数。
**编号说明**：以下 M 编号仅是本次 25 条方案的索引，不是上文历史 Case label，也不是正式 video_id；跨文件以 `math_expansion_20260923/Mxx` 唯一标识。落地时另行检查现有记录、归档与输出路径后分配 video_id。

##### 新增变体 M01

**拓展方式**：换数字。
**初始状态、动作与冲突终态**：数列 `[3,6]`，执行 `APPEND 9`；新卡片 9 插到最前面，结束于 `[9,3,6]`。
**正常规则及结果**：APPEND 应加到末尾，得到 `[3,6,9]`。

##### 新增变体 M02

**拓展方式**：原始数列增加两个元素。
**初始状态、动作与冲突终态**：数列 `[1,3,5,7]`，执行 `APPEND 8`；8 插到最前面，结束于 `[8,1,3,5,7]`。
**正常规则及结果**：应得到 `[1,3,5,7,8]`。

**本批次共用画面要求**：使用固定镜头的简洁二维教学图，完整展示初始输入、操作名和必要的有序动作；数字、卡片身份及非目标元素始终保持不变。最后显示中性 DONE 并保持冲突结果，不在画面中展示正常答案或对错判定。
**可见证据**：数组从左到右、栈从底到顶、堆按层序描述；队列 FRONT/REAR、栈 TOP、BST 左右与树的边必须清楚。冒泡排序完整展示非相邻交换；滑动窗口保留处理记录且不登记被跳过窗口；插入排序保留 TEMP 与空槽；栈和队列不自动压缩空槽。
**形式规则**：归并案例展示完整归并排序中的子列排序被跳过，随后头元素比较与输出顺序保持一致；稳定排序只按数字键比较，身份标签不参与比较；循环为无条件每次画一点，不含 break、擦除或重叠绘点；FIFO 命中是读取，不是删除后重插。
**后续数据接入**：每条新增视频保存自己的 variant_context.conflict_spec 与 questions，并据新输入生成匹配首帧；不得继承旧数字的参考答案。正常结果用于事实核对与正常参考答案，本批次仅新增 conflict 视频。每条视频生成后仍需单独审核，合格后才计入目标。
<!-- math-expansion-20260923-end -->
