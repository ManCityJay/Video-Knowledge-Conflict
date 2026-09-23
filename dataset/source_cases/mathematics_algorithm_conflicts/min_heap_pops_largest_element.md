### Min Heap: POP MIN Removes the Largest Element

**Case label**: M03
**Status**: User-approved first-frame revision; replacement video generation and human qualification are pending.

**First frame**: `dataset/source_assets/mathematics_algorithm_conflicts/min_heap_pops_largest_element/first_frame.png` (shared by conflict and control).

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: POP MIN on the min heap with root 1 and children 3 and 5 returns 1, leaving a min heap rooted at 3 with left child 5.
**Intended video fact (EN)**: POP MIN returns 5 instead, leaving root 1 and left child 3 when DONE appears.

**Video prompt**：

> Use the supplied image as the exact first frame of a single continuous 5-second flat educational animation. Keep its white background, fixed camera, framing, typography, node sizes, colors, and layout. Do not redraw or expand the initial diagram. A node circle and its centered digit are one rigid object. Hold the supplied first frame unchanged during seconds 0-1. The image contains exactly three nodes: blue root 1, blue left child 3, and orange right child 5. Only the two parent-child edges 1-3 and 1-5 exist. Preserve the labels "MIN HEAP", "POP MIN", and "OUTPUT". The output box is empty, and its center is horizontally level with node 5. At second 1 erase only the diagonal edge between 1 and 5. During seconds 1-2.8 translate the original orange node 5 and its digit together horizontally RIGHT into the center of the OUTPUT box. Its old right-child position becomes completely empty and stays empty. Blue 1, blue 3, and their connecting edge remain fixed throughout. Do not draw a horizontal track or stretch a connecting line behind the moving node. The completed tree has exactly two nodes, root 1 and left child 3; OUTPUT contains exactly one node, the original orange 5. At exactly second 3, show the small neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the completed result still from seconds 3-5. DONE means the operation has ended, not that its result is correct. No camera movement, cuts, speech, new nodes, duplicated digits, motion trails, correctness symbols, further operations, or late corrections.

**Control prompt**：

> Use the supplied image as the exact first frame of a single continuous 5-second flat educational animation. Keep its white background, fixed camera, framing, typography, node sizes, colors, and layout. Do not redraw or expand the initial diagram. A node circle and its centered digit are one rigid object. Hold the supplied first frame unchanged during seconds 0-1. The image contains exactly three nodes: blue root 1, blue left child 3, and orange right child 5. Only the two parent-child edges 1-3 and 1-5 exist. Preserve the labels "MIN HEAP", "POP MIN", and "OUTPUT". The output box is empty, and its center is horizontally level with node 5. At second 1 erase the two original parent-child edges. During seconds 1-1.8 move the original blue root 1 and its digit together into the center of OUTPUT. During seconds 1.8-2.2 move the original blue 3 to the original root position. During seconds 2.2-2.8 move the original orange 5 to the original left-child position and draw one diagonal edge connecting the new root 3 to left child 5. Each digit and node color stays unchanged. Do not duplicate nodes or leave the root position empty at the end. The completed tree contains root 3 and left child 5; OUTPUT contains only the original node 1. At exactly second 3, show the small neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the completed result still from seconds 3-5. DONE means the operation has ended, not that its result is correct. No camera movement, cuts, speech, new nodes, duplicated digits, motion trails, correctness symbols, further operations, or late corrections.

**Human review**：首帧恰好为根 1、左孩子 3、右孩子 5，输出框为空。冲突版先断开 1—5，原节点 5 水平移入输出框，原位置变空；树中只剩 1、3。对照输出 1 并重排为根 3、左孩子 5。不得复制节点，DONE 后保持静止。


<!-- math-expansion-20260923-start -->
#### 2026-09-23 新增 conflict 变体：数字与序列长度拓展

**批次范围**：math_expansion_20260923。本批次共 25 个新 conflict，分属 13 个现有 case；基线为 78 个 qualified conflict，全部新增视频审核合格后目标为 103 个。
**当前状态**：已按用户要求写入源案例描述；尚未为本批次生成视频或登记新 video 对象，不能计为 qualified。
**与原文的关系**：上文保留原有设计与历史记录；本节是追加的新变体。本节输入、对象数量、正常结果及冲突结果专属于以下变体，不沿用上文旧版本的具体数字、三/四槽限制或版本总数。
**编号说明**：以下 M 编号仅是本次 25 条方案的索引，不是上文历史 Case label，也不是正式 video_id；跨文件以 `math_expansion_20260923/Mxx` 唯一标识。落地时另行检查现有记录、归档与输出路径后分配 video_id。

##### 新增变体 M11

**拓展方式**：换数字。
**初始状态、动作与冲突终态**：小根堆根为 3，左右子节点为 6、9；执行 POP MIN，却把 9 移到 OUTPUT，保留根 3 和左子节点 6。
**正常规则及结果**：应输出最小值 3；标准删除及下沉后剩余根 6、左子节点 9。

##### 新增变体 M12

**拓展方式**：原始堆增加一个元素。
**初始状态、动作与冲突终态**：合法小根堆层序 `[2,6,4,8]`，8 为 6 的左子节点；POP MIN 直接输出最大叶子 8，剩余 `[2,6,4]`。
**正常规则及结果**：应输出 2；标准删除及下沉后为 `[4,6,8]`。

**本批次共用画面要求**：使用固定镜头的简洁二维教学图，完整展示初始输入、操作名和必要的有序动作；数字、卡片身份及非目标元素始终保持不变。最后显示中性 DONE 并保持冲突结果，不在画面中展示正常答案或对错判定。
**可见证据**：数组从左到右、栈从底到顶、堆按层序描述；队列 FRONT/REAR、栈 TOP、BST 左右与树的边必须清楚。冒泡排序完整展示非相邻交换；滑动窗口保留处理记录且不登记被跳过窗口；插入排序保留 TEMP 与空槽；栈和队列不自动压缩空槽。
**形式规则**：归并案例展示完整归并排序中的子列排序被跳过，随后头元素比较与输出顺序保持一致；稳定排序只按数字键比较，身份标签不参与比较；循环为无条件每次画一点，不含 break、擦除或重叠绘点；FIFO 命中是读取，不是删除后重插。
**后续数据接入**：每条新增视频保存自己的 variant_context.conflict_spec 与 questions，并据新输入生成匹配首帧；不得继承旧数字的参考答案。正常结果用于事实核对与正常参考答案，本批次仅新增 conflict 视频。每条视频生成后仍需单独审核，合格后才计入目标。
<!-- math-expansion-20260923-end -->
