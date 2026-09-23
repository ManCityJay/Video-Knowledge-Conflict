### Ascending Sort: The Completed Result Leaves the Largest Value on the Left

**Priority**：P1，首轮。2026-09-07 重写；生成后仍需人工审核。
**Standard prior**：[2,1,3] 的升序排序结果是 [1,2,3]。
**Conflict**：排序完成后变成 [3,1,2]，最大值 3 在最左。
**Localized edit**：只改变一次排序操作的最终排列；数字与柱高绑定不变，两版各完成一次交换。
**Visual evidence**：ASCENDING SORT 标题限定方向，按钮变为 DONE 限定这是终态；数字和柱高提供双重证据。
**Normal fact (EN)**: Sorting [2, 1, 3] into ascending order produces [1, 2, 3].
**Intended video fact (EN)**: The completed ascending-sort display shows [3, 1, 2], with the largest bar at the left.

**Video prompt**：

> A clean computer-science teaching animation, flat 2D shapes on a white background, fixed front view, one continuous 5-second shot. Large high-contrast labels, no people, hands, speech, subtitles, decorative text, cuts, or camera movement. The fixed title is "ASCENDING SORT". Three bars stand on one baseline: a medium blue bar labeled 2 at the left, a short orange bar labeled 1 in the center, and a tall teal bar labeled 3 at the right. Their heights are in the ratio 2:1:3. Each label stays attached to its bar. A large "SORT" button is below. During seconds 0-1 hold the row 2, 1, 3. At seconds 1-1.5 a cursor clicks SORT once and parks away from the bars. During seconds 1.5-3, the left bar 2 and right bar 3 exchange positions in one smooth swap, leaving the center bar 1 fixed. The final row reads 3, 1, 2. Use separated paths so each moving bar remains identifiable. At second 3 the button label changes to "DONE". Hold the completed row and DONE through second 5; perform no further sorting. Never change any bar height, color, or value, and keep all three bars fully visible.

**Control prompt**：

> A 5-second flat 2D teaching animation on white, fixed front view. Title: ASCENDING SORT. Exactly three vertical bars share one baseline. Left: medium blue bar labeled 2. Center: short orange bar labeled 1. Right: tall teal bar labeled 3. Large black numerals sit just above their respective bars and travel with them. A separate small SORT button is below the baseline. Hold for one second, then a cursor clicks SORT once and moves away. Only blue 2 and orange 1 exchange places: blue takes a raised arc to the center while orange slides left. Teal 3 never moves. By second 3, all bars rest on the baseline in order orange 1, blue 2, teal 3. The separate button changes to DONE. Hold this completed arrangement through second 5. All three numerals remain 1, 2, and 3; bar colors and dimensions stay constant. No extra bars, words on bars, vanishing, or camera movement.

**Human review**：必须能读到 ASCENDING SORT 和 DONE；终态为 3/1/2，且 3 柱最高。没有完成信号时，错误排列可能仅是合法中间态，应退回。


<!-- math-expansion-20260923-start -->
#### 2026-09-23 新增 conflict 变体：数字与序列长度拓展

**批次范围**：math_expansion_20260923。本批次共 25 个新 conflict，分属 13 个现有 case；基线为 78 个 qualified conflict，全部新增视频审核合格后目标为 103 个。
**当前状态**：已按用户要求写入源案例描述；尚未为本批次生成视频或登记新 video 对象，不能计为 qualified。
**与原文的关系**：上文保留原有设计与历史记录；本节是追加的新变体。本节输入、对象数量、正常结果及冲突结果专属于以下变体，不沿用上文旧版本的具体数字、三/四槽限制或版本总数。
**编号说明**：以下 M 编号仅是本次 25 条方案的索引，不是上文历史 Case label，也不是正式 video_id；跨文件以 `math_expansion_20260923/Mxx` 唯一标识。落地时另行检查现有记录、归档与输出路径后分配 video_id。

##### 新增变体 M03

**拓展方式**：换数字。
**初始状态、动作与冲突终态**：输入 `[2,7,5]`，标注升序排序；把 7 移到最左，结果 `[7,2,5]`，随后 DONE。
**正常规则及结果**：应为 `[2,5,7]`。

##### 新增变体 M04

**拓展方式**：原始数列增加两个元素。
**初始状态、动作与冲突终态**：输入 `[3,1,5,2,4]`；完成后最大数 5 在最左，其余递增，得到 `[5,1,2,3,4]`。
**正常规则及结果**：应为 `[1,2,3,4,5]`。

**本批次共用画面要求**：使用固定镜头的简洁二维教学图，完整展示初始输入、操作名和必要的有序动作；数字、卡片身份及非目标元素始终保持不变。最后显示中性 DONE 并保持冲突结果，不在画面中展示正常答案或对错判定。
**可见证据**：数组从左到右、栈从底到顶、堆按层序描述；队列 FRONT/REAR、栈 TOP、BST 左右与树的边必须清楚。冒泡排序完整展示非相邻交换；滑动窗口保留处理记录且不登记被跳过窗口；插入排序保留 TEMP 与空槽；栈和队列不自动压缩空槽。
**形式规则**：归并案例展示完整归并排序中的子列排序被跳过，随后头元素比较与输出顺序保持一致；稳定排序只按数字键比较，身份标签不参与比较；循环为无条件每次画一点，不含 break、擦除或重叠绘点；FIFO 命中是读取，不是删除后重插。
**后续数据接入**：每条新增视频保存自己的 variant_context.conflict_spec 与 questions，并据新输入生成匹配首帧；不得继承旧数字的参考答案。正常结果用于事实核对与正常参考答案，本批次仅新增 conflict 视频。每条视频生成后仍需单独审核，合格后才计入目标。
<!-- math-expansion-20260923-end -->
