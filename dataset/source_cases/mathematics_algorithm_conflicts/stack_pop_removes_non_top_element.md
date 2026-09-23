### Stack: POP Removes a Non-Top Element

**中文名称**：栈：弹出时错误地移除栈底或中间元素
**Status**: Revised source design draft for user review. Five conflict variants are specified; final Seedance prompts, first frames and video generation are pending.
**Case ID**: `stack_pop_removes_non_top_element`
**Relationship to earlier drafts**：本设计替代本次讨论中的 PEEK 草稿。仓库已有的 `stack_removes_oldest_item_first` 保留为历史案例；这里将冲突概括为“POP 错取非栈顶元素”，包含栈底和不同中间位置。以下 v001–v005 是本新 case 的拟用编号，不指代已有 case 的视频。

**Standard prior**：标准栈遵循后进先出（LIFO）。一次 POP 必须移除并返回当前栈顶元素；栈底和中间元素不能先于栈顶被弹出。数字只表示元素的身份，不是优先级，也不决定弹出次序。

**Conflict**：点击一次 POP 后，栈顶卡片保持原位，某张栈底或中间卡片却被取出并进入 OUTPUT。操作完成后，对应的非顶部槽位留空，原栈顶仍留在栈内。

**Localized edit**：仅将 POP 选中的对象从当前栈顶换成一个非栈顶元素。输出的卡片就是实际移除的那张，不额外引入返回值错误。每个版本只执行一次 POP，不包含 PUSH、PEEK、第二次 POP 或排序。

**Notation**：以下数组一律按“从栈底到栈顶”书写，最右元素为栈顶。`空` 表示固定显示槽位中的空位，不是一个值。删除后的槽位保留空白用于展示移除位置，剩余元素的相对次序不变。

**Conflict variants**：

| 拟用版本 | 初始栈：底→顶 | 错误移除对象 | 冲突版最终槽位：底→顶 | OUTPUT | 正常应移除 | 变化点 |
|---|---|---|---|---|---|---|
| v001 | [2, 5, 8] | 栈底 2，第 1 层 | [空, 5, 8] | 2 | 栈顶 8 | 基础冲突：错取栈底 |
| v002 | [2, 5, 8] | 中间 5，第 2 层 | [2, 空, 8] | 5 | 栈顶 8 | 相同输入，改为错取中间 |
| v003 | [6, 2, 9, 4] | 中间偏下的 2，第 2 层 | [6, 空, 9, 4] | 2 | 栈顶 4 | 增加栈深、改变数字、错取较低中间层 |
| v004 | [6, 2, 9, 4] | 紧邻栈顶下方的 9，第 3 层 | [6, 2, 空, 4] | 9 | 栈顶 4 | 相同四层栈，改为错取较高中间层 |
| v005 | [3, 8, 1] | 栈底 3，第 1 层 | [空, 8, 1] | 3 | 栈顶 1 | 改变数字及其大小关系，再演示错取栈底 |

v003–v005 使用非升序数字，避免把“栈顶”误解成“最大数”，或把“栈底”误解成“最小数”。变体差异落在错误移除位置、栈深或数据上，不依赖换颜色、改运动速度等外观变化。

**Shared initial scene**：

- 白底、高对比度二维算法教学图，标题固定为 STACK，正视镜头、连续单镜头。
- 左侧是三个或四个竖直排列的固定槽位，全部在画面内；各槽位初始均有一张数字卡片，按对应版本自下而上排列。
- 三层栈从底到顶分别使用橙、蓝、黄卡片；四层栈再增加一张紫色顶层卡片。颜色只用于持续追踪对象，数字和颜色与各自卡片绑定。
- 标有 TOP 的短箭头从左侧指向当前最高的已占用槽位：v001/v002 指向 8，v003/v004 指向 4，v005 指向 1。
- 右侧是一个空 OUTPUT 框，下方是 POP 按钮。OUTPUT 存放被移除的原卡片，不显示额外复制的数字或卡片。
- 首帧展示完整预置栈，不播放入栈过程；初态由卡片排列和 TOP 箭头明确给出。DONE 尚未出现。
- 槽位是算法示意图，卡片不受重力影响；移除下层卡片不会导致上层下落。

**Shared conflict sequence**：

1. 0.0–1.0 秒：完整展示对应版本的初始栈、TOP 箭头和空 OUTPUT。
2. 1.0–1.4 秒：POP 按钮短暂高亮一次，表示执行一次操作。不使用手、光标或夹具。
3. 1.4–2.4 秒：仅让表格指定的错误目标卡片水平向右移出原槽。所有其他卡片完全不动，尤其原栈顶卡片必须留在原位。
4. 2.4–3.2 秒：同一张目标卡片沿栈外通道移入 OUTPUT，数字、颜色和尺寸保持不变；运动路径不穿过其他卡片。
5. 3.2–4.0 秒：保持 OUTPUT 内的目标卡片、原位置的空槽以及所有剩余卡片。TOP 箭头仍指向原栈顶，因为原栈顶没有被移除。
6. 4.0–5.0 秒：显示中性深灰色 DONE，完整保持最终状态。不得再取出真正的栈顶来“补做”或纠正。

**Matched normal controls**：每个正常对照与对应冲突版本共用初态、布局、颜色、时长、一次 POP 和 OUTPUT。唯一的动作选择差异是取出真正的栈顶卡片；其他卡片保持原位。移除完成后，TOP 箭头指向新的栈顶。两版均在第 4 秒显示 DONE。

| 对应版本 | 正常移入 OUTPUT 的卡片 | 正常最终槽位：底→顶 | 正常新栈顶 |
|---|---|---|---|
| v001、v002 | 8 | [2, 5, 空] | 5 |
| v003、v004 | 4 | [6, 2, 9, 空] | 9 |
| v005 | 1 | [3, 8, 空] | 8 |

这些版本共有三种初态，因此设计上对应三组输入匹配的正常对照。不能把 [2, 5, 8] 的 control 用于 [6, 2, 9, 4] 或 [3, 8, 1]。正式接入数据时，每个版本必须保存自己的事实与参考答案，不能给五个冲突版本共用 v001 的答案。

**Normal fact (EN)**: A standard stack POP removes and returns the current top element. For bottom-to-top inputs [2, 5, 8], [6, 2, 9, 4], and [3, 8, 1], the returned elements must be 8, 4, and 1 respectively.

**Intended video facts (EN)**：

- **v001**: One POP moves bottom card 2 from stack [2, 5, 8] into OUTPUT, leaving 5 and 8 in place; top card 8 is not removed.
- **v002**: One POP moves middle card 5 from stack [2, 5, 8] into OUTPUT, leaving 2 and 8 in place; top card 8 is not removed.
- **v003**: One POP moves card 2 from the second slot from the bottom of stack [6, 2, 9, 4] into OUTPUT; cards 6, 9, and top card 4 remain in their original slots.
- **v004**: One POP moves card 9 from the slot immediately below the top of stack [6, 2, 9, 4] into OUTPUT; cards 6, 2, and top card 4 remain in their original slots.
- **v005**: One POP moves bottom card 3 from stack [3, 8, 1] into OUTPUT, leaving 8 and 1 in place; top card 1 is not removed.

**Question draft (EN)**: Which value is removed from the stack and placed in OUTPUT when the POP operation finishes?

| 版本 | Conflict video reference (EN) | Normal control reference (EN) |
|---|---|---|
| v001 | Card 2 is removed and placed in OUTPUT. | Card 8 is removed and placed in OUTPUT. |
| v002 | Card 5 is removed and placed in OUTPUT. | Card 8 is removed and placed in OUTPUT. |
| v003 | Card 2 is removed and placed in OUTPUT. | Card 4 is removed and placed in OUTPUT. |
| v004 | Card 9 is removed and placed in OUTPUT. | Card 4 is removed and placed in OUTPUT. |
| v005 | Card 3 is removed and placed in OUTPUT. | Card 1 is removed and placed in OUTPUT. |

**Video defaults**: 720p, 5 seconds, 16:9. Five planned conflict variants; control generation is a separate later step. These are new source designs, not additions already registered in the previous 56-video batch.

**Completion cue**：两版均在第 4 秒显示中性 DONE，保持最终状态至第 5 秒。DONE 只表示操作结束；不添加对错标记、知识解释或正常答案对比。

**Human review**：

- 全片操作名固定为 POP，仅触发一次。不得变成 PEEK、任意位置 DELETE 或选择指定值的移除操作。
- 按钮上不写要移除的数字，画面也不提供用户选择目标卡片的过程，避免把错误行为合理化为指定删除。
- 冲突版必须只移除对应版本指定的非栈顶卡片；原栈顶全程留在栈内，TOP 箭头不应改指栈底或中间。
- OUTPUT 中必须是从栈内移出的同一张实体卡片；原位置留空，不得复制、变色、改数字、凭空消失或移错卡片。
- 其他卡片不掉落、不补位、不换序。初始三层或四层结构、空槽与完整 OUTPUT 均持续可见。
- 正常版只能移除真正的栈顶，并更新 TOP 箭头；不能复现非顶部移除。
- DONE 后不再动作；视频是否 qualified 仍需生成后逐条审核。

**Next step**：先由用户核对本源案例和五个变体，再分别编写正式 Seedance 提示词并准备匹配首帧。当前不调用 author pipeline 或视频生成 API。


<!-- math-expansion-20260923-start -->
#### 2026-09-23 新增 conflict 变体：数字与序列长度拓展

**批次范围**：math_expansion_20260923。本批次共 25 个新 conflict，分属 13 个现有 case；基线为 78 个 qualified conflict，全部新增视频审核合格后目标为 103 个。
**当前状态**：已按用户要求写入源案例描述；尚未为本批次生成视频或登记新 video 对象，不能计为 qualified。
**与原文的关系**：上文保留原有设计与历史记录；本节是追加的新变体。本节输入、对象数量、正常结果及冲突结果专属于以下变体，不沿用上文旧版本的具体数字、三/四槽限制或版本总数。
**编号说明**：以下 M 编号仅是本次 25 条方案的索引，不是上文历史 Case label，也不是正式 video_id；跨文件以 `math_expansion_20260923/Mxx` 唯一标识。落地时另行检查现有记录、归档与输出路径后分配 video_id。

##### 新增变体 M15

**拓展方式**：换数字。
**初始状态、动作与冲突终态**：栈从底到顶为 `[4,7,9]`；一次 POP 将底部 4 横向移出，再送入 OUTPUT；7、9 保持原位，TOP 始终指向 9。
**正常规则及结果**：应弹出栈顶 9。

##### 新增变体 M16

**拓展方式**：原始栈增加两个元素。
**初始状态、动作与冲突终态**：栈从底到顶为 `[1,3,5,7,9]`；一次 POP 取出中间的 5，原槽留空，其余卡片和 TOP 不动。
**正常规则及结果**：应弹出栈顶 9。

**本批次共用画面要求**：使用固定镜头的简洁二维教学图，完整展示初始输入、操作名和必要的有序动作；数字、卡片身份及非目标元素始终保持不变。最后显示中性 DONE 并保持冲突结果，不在画面中展示正常答案或对错判定。
**可见证据**：数组从左到右、栈从底到顶、堆按层序描述；队列 FRONT/REAR、栈 TOP、BST 左右与树的边必须清楚。冒泡排序完整展示非相邻交换；滑动窗口保留处理记录且不登记被跳过窗口；插入排序保留 TEMP 与空槽；栈和队列不自动压缩空槽。
**形式规则**：归并案例展示完整归并排序中的子列排序被跳过，随后头元素比较与输出顺序保持一致；稳定排序只按数字键比较，身份标签不参与比较；循环为无条件每次画一点，不含 break、擦除或重叠绘点；FIFO 命中是读取，不是删除后重插。
**后续数据接入**：每条新增视频保存自己的 variant_context.conflict_spec 与 questions，并据新输入生成匹配首帧；不得继承旧数字的参考答案。正常结果用于事实核对与正常参考答案，本批次仅新增 conflict 视频。每条视频生成后仍需单独审核，合格后才计入目标。
<!-- math-expansion-20260923-end -->
