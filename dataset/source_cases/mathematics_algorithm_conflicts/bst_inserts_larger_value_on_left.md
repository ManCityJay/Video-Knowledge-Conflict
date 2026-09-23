### BST: Larger Value Inserted on the Left

**Case label**: M02
**Status**: User-approved first-frame revision; replacement video generation and human qualification are pending.

**First frame**: `dataset/source_assets/mathematics_algorithm_conflicts/bst_inserts_larger_value_on_left/first_frame.png` (shared by conflict and control).

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: In a binary search tree with root 5, inserting 8 places it as the right child.
**Intended video fact (EN)**: The completed BST insertion attaches 8 as the left child of root 5.

**Video prompt**：

> Use the supplied image as the exact first frame of a single continuous 5-second flat educational animation. Keep its white background, fixed camera, framing, typography, node sizes, colors, and layout. Do not redraw or expand the initial diagram. A node circle and its centered digit are one rigid object. Hold the supplied first frame unchanged during seconds 0-1. The image contains exactly two separate nodes and the title "BST": blue root 5 at the upper right of the pair and orange new node 8 to its left at the same height, with no edges. Keep blue 5 fixed throughout. During seconds 1-2.5 translate only the orange 8 straight DOWN, keeping its horizontal position unchanged. Stop at about two-thirds of the image height, clearly below and LEFT of blue 5. During seconds 2.5-3 draw exactly one straight diagonal edge from the lower-left circumference of 5 to the upper-right circumference of 8; the edge stops at each circle boundary. The final tree contains only root 5 and LEFT child 8, joined by that diagonal edge. The right child region is empty. At exactly second 3, show the small neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the completed result still from seconds 3-5. DONE means the operation has ended, not that its result is correct. No camera movement, cuts, speech, new nodes, duplicated digits, motion trails, correctness symbols, further operations, or late corrections.

**Control prompt**：

> Use the supplied image as the exact first frame of a single continuous 5-second flat educational animation. Keep its white background, fixed camera, framing, typography, node sizes, colors, and layout. Do not redraw or expand the initial diagram. A node circle and its centered digit are one rigid object. Hold the supplied first frame unchanged during seconds 0-1. The image contains exactly two separate nodes and the title "BST": blue root 5 at the upper right of the pair and orange new node 8 to its left at the same height, with no edges. Keep blue 5 fixed throughout. During seconds 1-2.5 translate only the orange 8 diagonally DOWN and RIGHT to a position at about 85 percent of the image width and two-thirds of its height, clearly below and RIGHT of blue 5. Keep 8 separate from 5 throughout the move. During seconds 2.5-3 draw exactly one straight diagonal edge from the lower-right circumference of 5 to the upper-left circumference of 8; the edge stops at each circle boundary. The final tree contains only root 5 and RIGHT child 8, joined by that diagonal edge. The left child region is empty. At exactly second 3, show the small neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the completed result still from seconds 3-5. DONE means the operation has ended, not that its result is correct. No camera movement, cuts, speech, new nodes, duplicated digits, motion trails, correctness symbols, further operations, or late corrections.

**Human review**：首帧只能有蓝色 5 和橙色 8。冲突版 8 竖直下移成为左孩子，对照版成为右孩子；5 不动，最后只有两个节点和一条斜线。DONE 出现后保持到第 5 秒。


<!-- math-expansion-20260923-start -->
#### 2026-09-23 新增 conflict 变体：数字与序列长度拓展

**批次范围**：math_expansion_20260923。本批次共 25 个新 conflict，分属 13 个现有 case；基线为 78 个 qualified conflict，全部新增视频审核合格后目标为 103 个。
**当前状态**：已按用户要求写入源案例描述；尚未为本批次生成视频或登记新 video 对象，不能计为 qualified。
**与原文的关系**：上文保留原有设计与历史记录；本节是追加的新变体。本节输入、对象数量、正常结果及冲突结果专属于以下变体，不沿用上文旧版本的具体数字、三/四槽限制或版本总数。
**编号说明**：以下 M 编号仅是本次 25 条方案的索引，不是上文历史 Case label，也不是正式 video_id；跨文件以 `math_expansion_20260923/Mxx` 唯一标识。落地时另行检查现有记录、归档与输出路径后分配 video_id。

##### 新增变体 M23

**拓展方式**：换数字。
**初始状态、动作与冲突终态**：BST 只有根 4，新节点 7 待插入；7 移到根的左侧并连接为左孩子，随后 DONE。
**正常规则及结果**：7 大于 4，应成为根的右孩子。

##### 新增变体 M24

**拓展方式**：原始树增加两个节点。
**初始状态、动作与冲突终态**：原 BST 为根 6、左孩子 2、右孩子 8；插入 4，先沿根的左分支到 2，却把 4 接到 2 的左侧。原有节点不动。
**正常规则及结果**：4 小于 6、大于 2，应成为 2 的右孩子。

**本批次共用画面要求**：使用固定镜头的简洁二维教学图，完整展示初始输入、操作名和必要的有序动作；数字、卡片身份及非目标元素始终保持不变。最后显示中性 DONE 并保持冲突结果，不在画面中展示正常答案或对错判定。
**可见证据**：数组从左到右、栈从底到顶、堆按层序描述；队列 FRONT/REAR、栈 TOP、BST 左右与树的边必须清楚。冒泡排序完整展示非相邻交换；滑动窗口保留处理记录且不登记被跳过窗口；插入排序保留 TEMP 与空槽；栈和队列不自动压缩空槽。
**形式规则**：归并案例展示完整归并排序中的子列排序被跳过，随后头元素比较与输出顺序保持一致；稳定排序只按数字键比较，身份标签不参与比较；循环为无条件每次画一点，不含 break、擦除或重叠绘点；FIFO 命中是读取，不是删除后重插。
**后续数据接入**：每条新增视频保存自己的 variant_context.conflict_spec 与 questions，并据新输入生成匹配首帧；不得继承旧数字的参考答案。正常结果用于事实核对与正常参考答案，本批次仅新增 conflict 视频。每条视频生成后仍需单独审核，合格后才计入目标。
<!-- math-expansion-20260923-end -->
