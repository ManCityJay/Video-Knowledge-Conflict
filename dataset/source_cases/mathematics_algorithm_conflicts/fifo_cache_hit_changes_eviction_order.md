### FIFO Cache: A Hit Incorrectly Changes Eviction Order

**Case label**: M48
**Candidate number**: 16
**中文名称**: FIFO 缓存：一次访问改变了淘汰顺序
**Status**: User-approved design; prompts directly revised with explicit user authorization on 2026-09-14. Regeneration and human review are pending.

- **正常知识与冲突：** FIFO 缓存按进入顺序淘汰，普通命中访问不改变该顺序；冲突版把访问当作重新入队。
- **画面：** 标题 FIFO CACHE。红卡先进入两槽缓存，蓝卡后进入；指针再读取红卡。绿卡到来时，系统却淘汰蓝卡，将其移到可见淘汰区。
- **正常对照：** 无论红卡刚被访问过，仍淘汰最早进入的红卡，再放入绿卡。
- **重点：** 红卡访问期间不能移出再重新插入。保留红先入、蓝后入、红被访问、绿到来的完整顺序；不是 LRU 缓存，容量固定为二。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: A FIFO cache evicts the earliest inserted entry, and a cache hit does not change insertion order.
**Intended video fact (EN)**: Red is inserted before blue and then accessed; when green arrives, the FIFO cache incorrectly evicts blue instead of red.

**Prompt authoring**: 本次用户明确授权跳过 Luna，直接修订 v001 与匹配 control 提示词。使用下方固定首帧与逐段坐标时间表；不使用 author --force。原问题、视频任务及生成历史保留。

**Human review**: 红卡访问期间不能移出再重新插入。保留红先入、蓝后入、红被访问、绿到来的完整顺序；不是 LRU 缓存，容量固定为二。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。

**Fixed layout revision — 2026-09-14**: 首帧固定空的两槽缓存，下方独立淘汰区。0.3–0.8 秒红卡先入，0.95–1.45 秒蓝卡后入，1.65–2.15 秒原位命中红卡；2.3–2.85 秒蓝卡完全向下退出，空槽保持到 3.05 秒；3.05–3.65 秒绿卡才进入。红卡保留，蓝卡在独立淘汰区。control 只改为淘汰红卡、绿卡填左槽。删除动态队列文字，禁止蓝绿重叠、第三缓存槽和卡片瞬间生成。

**First frame**: `dataset/source_assets/mathematics_algorithm_conflicts/fifo_cache_hit_changes_eviction_order/first_frame_fixed_layout.png`

**Video prompt (v001, EN)**:

Create exactly 5 seconds of 1280x720, 16:9 flat 2D animation, using the supplied image as the exact first frame. One locked front camera; preserve the first-frame layout and typography without zoom, cuts or reframing. All coordinates below are pixel centers measured from the top-left: x increases rightward and y increases downward. Coordinates are production instructions, never visible text. Preserve the exact first-frame title FIFO CACHE at (640,65). The ONLY cache is the upper two-slot rectangle x=350..810,y=285..455, divided by the stationary line x=580: left slot center (460,370), right slot center (700,370). The separate wide beige tray x=340..820,y=510..680, labeled EVICTED at (580,655), is outside the cache and never counts as a third slot. Exactly three solid rectangular cards, each 150 pixels wide and 90 pixels high, exist from the first frame: red RED at (180,370), blue BLUE at (1060,370), green GREEN at (580,170). Labels move rigidly with their cards; keep colors, identities and sizes fixed. The cache and tray are initially empty. Do not add insertion numbers, order strips, moving text, new cards, hands or pointers. During each specified move only that card moves, linearly between its endpoints. All other cards hold their exact coordinates. Execute this exact timeline:
0.00-0.30: hold the complete initial frame.
0.30-0.80: RED moves horizontally right from (180,370) to (460,370). BLUE stays (1060,370), GREEN stays (580,170).
0.80-0.95: hold RED fully inside the left slot.
0.95-1.45: BLUE moves horizontally left from (1060,370) to (700,370). RED stays (460,370), GREEN stays (580,170).
1.45-1.65: hold both cache slots occupied. This visibly establishes RED entered before BLUE.
1.65-2.15: perform exactly one read hit on RED without moving it: a thin amber outline appears around RED and the short label HIT appears at (460,260). RED remains at (460,370), BLUE at (700,370), GREEN at (580,170). Remove the outline and HIT together at 2.15. This read does not remove or reinsert any card.
2.15-2.30: all cards remain still.
2.30-2.85: BLUE alone moves straight down from (700,370) to (700,575), completely leaving its cache slot and entering the separate lower EVICTED tray. Keep RED at (460,370) motionless and GREEN at (580,170).
2.85-3.05: hold the empty cache slot visibly EMPTY for 0.20 seconds; the evicted card is wholly inside the lower tray. GREEN has not started moving.
3.05-3.65: GREEN alone moves in one straight line from (580,170) into the empty cache slot at (700,370). Do not duplicate or fade in GREEN in its destination. Its original overhead location becomes empty as the same physical card leaves it. The other cards remain stationary.
3.65-5.00: hold all three cards motionless. BLUE remains visible at (700,575) in the lower EVICTED tray; RED occupies the left cache slot at (460,370); GREEN occupies the right cache slot at (700,370). Exactly two cards are inside the cache and one is in the separate tray; none overlap. At t=4.00 add only the word DONE centered at (1120,80), and hold the entire completed frame without motion through t=5.00. DONE is absent before t=4.00. No further action, correction, subtitles, extra titles, explanations, hands or mouse cursors.

**Control prompt (control, EN)**:

Create exactly 5 seconds of 1280x720, 16:9 flat 2D animation, using the supplied image as the exact first frame. One locked front camera; preserve the first-frame layout and typography without zoom, cuts or reframing. All coordinates below are pixel centers measured from the top-left: x increases rightward and y increases downward. Coordinates are production instructions, never visible text. Preserve the exact first-frame title FIFO CACHE at (640,65). The ONLY cache is the upper two-slot rectangle x=350..810,y=285..455, divided by the stationary line x=580: left slot center (460,370), right slot center (700,370). The separate wide beige tray x=340..820,y=510..680, labeled EVICTED at (580,655), is outside the cache and never counts as a third slot. Exactly three solid rectangular cards, each 150 pixels wide and 90 pixels high, exist from the first frame: red RED at (180,370), blue BLUE at (1060,370), green GREEN at (580,170). Labels move rigidly with their cards; keep colors, identities and sizes fixed. The cache and tray are initially empty. Do not add insertion numbers, order strips, moving text, new cards, hands or pointers. During each specified move only that card moves, linearly between its endpoints. All other cards hold their exact coordinates. Execute this exact timeline:
0.00-0.30: hold the complete initial frame.
0.30-0.80: RED moves horizontally right from (180,370) to (460,370). BLUE stays (1060,370), GREEN stays (580,170).
0.80-0.95: hold RED fully inside the left slot.
0.95-1.45: BLUE moves horizontally left from (1060,370) to (700,370). RED stays (460,370), GREEN stays (580,170).
1.45-1.65: hold both cache slots occupied. This visibly establishes RED entered before BLUE.
1.65-2.15: perform exactly one read hit on RED without moving it: a thin amber outline appears around RED and the short label HIT appears at (460,260). RED remains at (460,370), BLUE at (700,370), GREEN at (580,170). Remove the outline and HIT together at 2.15. This read does not remove or reinsert any card.
2.15-2.30: all cards remain still.
2.30-2.85: RED alone moves straight down from (460,370) to (460,575), completely leaving its cache slot and entering the separate lower EVICTED tray. Keep BLUE at (700,370) motionless and GREEN at (580,170).
2.85-3.05: hold the empty cache slot visibly EMPTY for 0.20 seconds; the evicted card is wholly inside the lower tray. GREEN has not started moving.
3.05-3.65: GREEN alone moves in one straight line from (580,170) into the empty cache slot at (460,370). Do not duplicate or fade in GREEN in its destination. Its original overhead location becomes empty as the same physical card leaves it. The other cards remain stationary.
3.65-5.00: hold all three cards motionless. RED remains visible at (460,575) in the lower EVICTED tray; GREEN occupies the left cache slot at (460,370); BLUE occupies the right cache slot at (700,370). Exactly two cards are inside the cache and one is in the separate tray; none overlap. At t=4.00 add only the word DONE centered at (1120,80), and hold the entire completed frame without motion through t=5.00. DONE is absent before t=4.00. No further action, correction, subtitles, extra titles, explanations, hands or mouse cursors.


<!-- math-expansion-20260923-start -->
#### 2026-09-23 新增 conflict 变体：数字与序列长度拓展

**批次范围**：math_expansion_20260923。本批次共 25 个新 conflict，分属 13 个现有 case；基线为 78 个 qualified conflict，全部新增视频审核合格后目标为 103 个。
**当前状态**：已按用户要求写入源案例描述；尚未为本批次生成视频或登记新 video 对象，不能计为 qualified。
**与原文的关系**：上文保留原有设计与历史记录；本节是追加的新变体。本节输入、对象数量、正常结果及冲突结果专属于以下变体，不沿用上文旧版本的具体数字、三/四槽限制或版本总数。
**编号说明**：以下 M 编号仅是本次 25 条方案的索引，不是上文历史 Case label，也不是正式 video_id；跨文件以 `math_expansion_20260923/Mxx` 唯一标识。落地时另行检查现有记录、归档与输出路径后分配 video_id。

##### 新增变体 M25

**拓展方式**：换数字并使用三槽缓存。
**初始状态、动作与冲突终态**：容量 3，依次插入 2、5、8；命中读取 2，不移除或重新插入；再插入 9 时却淘汰 5，最终保留 2、8、9。
**正常规则及结果**：FIFO 按插入先后淘汰，应淘汰最早插入的 2，保留 5、8、9；命中不改变插入顺序。

**本批次共用画面要求**：使用固定镜头的简洁二维教学图，完整展示初始输入、操作名和必要的有序动作；数字、卡片身份及非目标元素始终保持不变。最后显示中性 DONE 并保持冲突结果，不在画面中展示正常答案或对错判定。
**可见证据**：数组从左到右、栈从底到顶、堆按层序描述；队列 FRONT/REAR、栈 TOP、BST 左右与树的边必须清楚。冒泡排序完整展示非相邻交换；滑动窗口保留处理记录且不登记被跳过窗口；插入排序保留 TEMP 与空槽；栈和队列不自动压缩空槽。
**形式规则**：归并案例展示完整归并排序中的子列排序被跳过，随后头元素比较与输出顺序保持一致；稳定排序只按数字键比较，身份标签不参与比较；循环为无条件每次画一点，不含 break、擦除或重叠绘点；FIFO 命中是读取，不是删除后重插。
**后续数据接入**：每条新增视频保存自己的 variant_context.conflict_spec 与 questions，并据新输入生成匹配首帧；不得继承旧数字的参考答案。正常结果用于事实核对与正常参考答案，本批次仅新增 conflict 视频。每条视频生成后仍需单独审核，合格后才计入目标。
<!-- math-expansion-20260923-end -->
