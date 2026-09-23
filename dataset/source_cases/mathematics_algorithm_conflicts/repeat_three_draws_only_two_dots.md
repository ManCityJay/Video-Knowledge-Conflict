### Repeat Three: Only Two Dots Drawn

**Case label**: M36
**Status**: User-approved design; video generation and human qualification are pending.

- **正常知识与冲突：** 重复 3 次，每次画一个点，完成后应有三个点；冲突版只画两个就结束。
- **画面：** 标题固定为 REPEAT 3，下方空白画布和 RUN 按钮。点击后在 1.3 秒、2.0 秒分别画一个蓝点；冲突版不执行第三次。
- **正常对照：** 2.7 秒画出第三个蓝点。
- **重点：** 两版均在第 3 秒将 RUN 变为 DONE，之后保持到第 5 秒。冲突版绝不能迟到补点，也不添加第三个点的虚影或占位圆。

**Completion cue**: Both roles show neutral DONE at second 3 and hold their completed result through second 5. M36 changes the RUN button itself to DONE; the other cases use the upper-right status label. Completion is not a correctness judgment.

**Normal fact (EN)**: An unconditional loop that draws one dot per iteration and repeats three times finishes with three dots.
**Intended video fact (EN)**: The REPEAT 3 run draws only two dots, changes its run button to DONE, and remains finished with no third dot.

**Video prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. At the top print the large immutable instruction "REPEAT 3". Below it is an entirely empty drawing area and one rectangular button labeled "RUN". This is one unconditional run: every iteration immediately draws exactly one identical solid blue dot, with no branch, cancellation, exception, break, or variable loop limit. Hold during seconds 0-1. At second 1 a cursor clicks RUN once, then parks outside the drawing area. At second 1.3 draw one dot at the left position. At second 2.0 draw a second dot at the center position. Once drawn, dots stay fixed and fully visible. Draw no dot at second 2.7 or at any later time. The completed result contains exactly TWO blue dots, at the left and center positions; the right region stays entirely blank. At exactly second 3, change the button label from "RUN" to the neutral dark-gray word "DONE". Keep the top instruction "REPEAT 3" unchanged. Hold the finished button and final dots still through second 5. DONE means the run has ended, not that its output is correct. There is no active timer, progress indicator, error, pause, extra click, looping playback, late dot, ghost dot, empty outlined slot, or correction.

**Control prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. At the top print the large immutable instruction "REPEAT 3". Below it is an entirely empty drawing area and one rectangular button labeled "RUN". This is one unconditional run: every iteration immediately draws exactly one identical solid blue dot, with no branch, cancellation, exception, break, or variable loop limit. Hold during seconds 0-1. At second 1 a cursor clicks RUN once, then parks outside the drawing area. At second 1.3 draw one dot at the left position. At second 2.0 draw a second dot at the center position. Once drawn, dots stay fixed and fully visible. At second 2.7 draw a third identical dot at the right position with the same spacing. The completed result contains exactly THREE blue dots in a row. At exactly second 3, change the button label from "RUN" to the neutral dark-gray word "DONE". Keep the top instruction "REPEAT 3" unchanged. Hold the finished button and final dots still through second 5. DONE means the run has ended, not that its output is correct. There is no active timer, progress indicator, error, pause, extra click, looping playback, late dot, ghost dot, empty outlined slot, or correction.

**Human review**：两版均在第 3 秒将 RUN 变为 DONE，之后保持到第 5 秒。冲突版绝不能迟到补点，也不添加第三个点的虚影或占位圆。 最终结果必须在 DONE 出现前确定，DONE 与结果共同保持约 2 秒；DONE 缺失、提前出现、遮挡结果或之后继续执行均不通过。普通对照也需要独立核验，不因显示 DONE 就视为正确。


<!-- math-expansion-20260923-start -->
#### 2026-09-23 新增 conflict 变体：数字与序列长度拓展

**批次范围**：math_expansion_20260923。本批次共 25 个新 conflict，分属 13 个现有 case；基线为 78 个 qualified conflict，全部新增视频审核合格后目标为 103 个。
**当前状态**：已按用户要求写入源案例描述；尚未为本批次生成视频或登记新 video 对象，不能计为 qualified。
**与原文的关系**：上文保留原有设计与历史记录；本节是追加的新变体。本节输入、对象数量、正常结果及冲突结果专属于以下变体，不沿用上文旧版本的具体数字、三/四槽限制或版本总数。
**编号说明**：以下 M 编号仅是本次 25 条方案的索引，不是上文历史 Case label，也不是正式 video_id；跨文件以 `math_expansion_20260923/Mxx` 唯一标识。落地时另行检查现有记录、归档与输出路径后分配 video_id。

##### 新增变体 M17

**拓展方式**：改循环次数，比已有 REPEAT 5 增加一次。
**初始状态、动作与冲突终态**：标注 `REPEAT 6`，每次循环画一个独立圆点；画出 5 个点后显示 DONE，终态停留，无第 6 个点。
**正常规则及结果**：无条件循环 6 次、每次画一点，应有 6 个点。

##### 新增变体 M18

**拓展方式**：改循环次数，比已有 REPEAT 5 增加两次。
**初始状态、动作与冲突终态**：标注 `REPEAT 7`，每次循环画一个点；只画出 5 个点便结束，最终一直保持 5 个。
**正常规则及结果**：应有 7 个点。

**本批次共用画面要求**：使用固定镜头的简洁二维教学图，完整展示初始输入、操作名和必要的有序动作；数字、卡片身份及非目标元素始终保持不变。最后显示中性 DONE 并保持冲突结果，不在画面中展示正常答案或对错判定。
**可见证据**：数组从左到右、栈从底到顶、堆按层序描述；队列 FRONT/REAR、栈 TOP、BST 左右与树的边必须清楚。冒泡排序完整展示非相邻交换；滑动窗口保留处理记录且不登记被跳过窗口；插入排序保留 TEMP 与空槽；栈和队列不自动压缩空槽。
**形式规则**：归并案例展示完整归并排序中的子列排序被跳过，随后头元素比较与输出顺序保持一致；稳定排序只按数字键比较，身份标签不参与比较；循环为无条件每次画一点，不含 break、擦除或重叠绘点；FIFO 命中是读取，不是删除后重插。
**后续数据接入**：每条新增视频保存自己的 variant_context.conflict_spec 与 questions，并据新输入生成匹配首帧；不得继承旧数字的参考答案。正常结果用于事实核对与正常参考答案，本批次仅新增 conflict 视频。每条视频生成后仍需单独审核，合格后才计入目标。
<!-- math-expansion-20260923-end -->
