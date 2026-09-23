### Queue: The Most Recently Enqueued Item Leaves First

**Priority**：P1，首轮。2026-09-07 重写；生成后仍需人工审核。
**Standard prior**：标准 FIFO 队列从队首到队尾为 A、B、C，一次出队应取出 A。
**Conflict**：点击 DEQUEUE 后，队尾 C 被取出，A、B 留在原槽。
**Localized edit**：只将出队对象由 A 改为 C，不改变队首队尾定义。
**Visual evidence**：QUEUE、FRONT、REAR 和出队按钮固定可见；同一输出框中的元素与原队列缺口对应。
**Normal fact (EN)**: In a standard FIFO queue whose front-to-rear order is A, B, C, one DEQUEUE removes front item A and leaves B and C.
**Intended video fact (EN)**: One DEQUEUE removes rear item C into the output area, while A and B remain in their original queue slots.

**Video prompt**：

> A clean computer-science teaching animation, flat 2D shapes on a white background, fixed front view, one continuous 5-second shot. Large high-contrast labels, no people, hands, speech, subtitles, decorative text, cuts, or camera movement. A diagram titled "QUEUE" contains three equal tiles in one horizontal row, orange A on the left, blue B in the center, teal C on the right. The fixed label "FRONT" is above the left slot and "REAR" above the right slot. An empty wide output box sits below the entire row, and a large "DEQUEUE" button sits separately at the lower right. During seconds 0-1 hold this complete preloaded queue. At seconds 1-1.5 a cursor clicks DEQUEUE once and parks away from the row. During seconds 1.5-3, only the teal rightmost tile C slides straight down into the output box. A and B stay in their original slots, leaving the rear slot empty. During seconds 3-5 hold the output tile and the remaining queue fully visible. Keep all original objects visible, with identical sizes, colors, and labels throughout. No extra objects, duplication, disappearance, gravity, or automatic rearrangement.

**Control prompt**：

> A clean computer-science teaching animation, flat 2D shapes on a white background, fixed front view, one continuous 5-second shot. Large high-contrast labels, no people, hands, speech, subtitles, decorative text, cuts, or camera movement. A diagram titled "QUEUE" contains three equal tiles in one horizontal row, orange A on the left, blue B in the center, teal C on the right. The fixed label "FRONT" is above the left slot and "REAR" above the right slot. An empty wide output box sits below the entire row, and a large "DEQUEUE" button sits separately at the lower right. During seconds 0-1 hold this complete preloaded queue. At seconds 1-1.5 a cursor clicks DEQUEUE once and parks away from the row. During seconds 1.5-3, only the orange leftmost tile A slides straight down into the output box. B and C stay in their original slots, leaving the front slot empty. During seconds 3-5 hold the output tile and the remaining queue fully visible. Keep all original objects visible, with identical sizes, colors, and labels throughout. No extra objects, duplication, disappearance, gravity, or automatic rearrangement.

**Human review**：FRONT/REAR 不能交换；仅 C 出队。不得自行滚动队列、把输出解释为入队，或隐藏某个元素。


<!-- math-expansion-20260923-start -->
#### 2026-09-23 新增 conflict 变体：数字与序列长度拓展

**批次范围**：math_expansion_20260923。本批次共 25 个新 conflict，分属 13 个现有 case；基线为 78 个 qualified conflict，全部新增视频审核合格后目标为 103 个。
**当前状态**：已按用户要求写入源案例描述；尚未为本批次生成视频或登记新 video 对象，不能计为 qualified。
**与原文的关系**：上文保留原有设计与历史记录；本节是追加的新变体。本节输入、对象数量、正常结果及冲突结果专属于以下变体，不沿用上文旧版本的具体数字、三/四槽限制或版本总数。
**编号说明**：以下 M 编号仅是本次 25 条方案的索引，不是上文历史 Case label，也不是正式 video_id；跨文件以 `math_expansion_20260923/Mxx` 唯一标识。落地时另行检查现有记录、归档与输出路径后分配 video_id。

##### 新增变体 M13

**拓展方式**：换数字。
**初始状态、动作与冲突终态**：FIFO 队列从 FRONT 到 REAR 为 `[1,4,7]`；一次 DEQUEUE 却取出队尾 7，1、4 保持原位置。
**正常规则及结果**：应取出队首 1，剩余 4、7。

##### 新增变体 M14

**拓展方式**：原始队列增加两个元素。
**初始状态、动作与冲突终态**：队列从 FRONT 到 REAR 为 `[2,4,6,8,9]`；一次 DEQUEUE 取出 9，前四个元素不动。
**正常规则及结果**：应取出 2，剩余 4、6、8、9。

**本批次共用画面要求**：使用固定镜头的简洁二维教学图，完整展示初始输入、操作名和必要的有序动作；数字、卡片身份及非目标元素始终保持不变。最后显示中性 DONE 并保持冲突结果，不在画面中展示正常答案或对错判定。
**可见证据**：数组从左到右、栈从底到顶、堆按层序描述；队列 FRONT/REAR、栈 TOP、BST 左右与树的边必须清楚。冒泡排序完整展示非相邻交换；滑动窗口保留处理记录且不登记被跳过窗口；插入排序保留 TEMP 与空槽；栈和队列不自动压缩空槽。
**形式规则**：归并案例展示完整归并排序中的子列排序被跳过，随后头元素比较与输出顺序保持一致；稳定排序只按数字键比较，身份标签不参与比较；循环为无条件每次画一点，不含 break、擦除或重叠绘点；FIFO 命中是读取，不是删除后重插。
**后续数据接入**：每条新增视频保存自己的 variant_context.conflict_spec 与 questions，并据新输入生成匹配首帧；不得继承旧数字的参考答案。正常结果用于事实核对与正常参考答案，本批次仅新增 conflict 视频。每条视频生成后仍需单独审核，合格后才计入目标。
<!-- math-expansion-20260923-end -->
