### Undo: Earlier Operation Reverted Instead of the Latest

**Case label**: M49
**Candidate number**: 17
**中文名称**: 撤销操作：撤销的不是最后一步
**Status**: User-approved design; prompts directly revised with explicit user authorization on 2026-09-14. Regeneration and human review are pending.

- **正常知识与冲突：** 顺序编辑中的一次撤销应撤销最后完成的操作；冲突版撤销更早的操作。
- **画面：** 圆点先向右移动一格，再向上移动一格。点击一次 UNDO 后，圆点向左移动一格。
- **正常对照：** 同样点击一次 UNDO，圆点向下移动一格，撤销最近的上移。
- **重点：** 初始右移和上移分开完成，不能合并为斜向移动。采用普通后进先出的撤销历史，不是选择性撤销；仅一次 UNDO，无额外编辑。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: With ordinary last-in-first-out undo history, undoing a right move followed by an up move reverses the up move.
**Intended video fact (EN)**: After moving right and then up, one UNDO moves the dot left, reversing the earlier right move instead of the latest up move.

**Prompt authoring**: 本次用户明确授权跳过 Luna，直接修订 v001 与匹配 control 提示词。使用下方固定首帧与逐段坐标时间表；不使用 author --force。原问题、视频任务及生成历史保留。

**Human review**: 初始右移和上移分开完成，不能合并为斜向移动。采用普通后进先出的撤销历史，不是选择性撤销；仅一次 UNDO，无额外编辑。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。

**Fixed layout revision — 2026-09-14**: 固定 1280×720 网格，一格为 160 像素。圆点中心依次为 (520,450) → (680,450) → (680,290) → (520,290)。每次移动与停顿分别规定时间，3.2 秒停止，4 秒显示 DONE。control 仅把最后一步改为下移至 (680,450)。

**First frame**: `dataset/source_assets/mathematics_algorithm_conflicts/undo_reverts_earlier_operation/first_frame_fixed_layout.png`

**Video prompt (v001, EN)**:

Create exactly 5 seconds of 1280x720, 16:9 flat 2D animation, using the supplied image as the exact first frame. One locked front camera; preserve the first-frame layout and typography without zoom, cuts or reframing. All coordinates below are pixel centers measured from the top-left: x increases rightward and y increases downward. Coordinates are production instructions, never visible text. The fixed grid has vertical lines at x=120,280,440,600,760,920 and horizontal lines at y=210,370,530,690. Exactly one solid blue disk of radius 22 pixels, with a white D rigidly attached at its center, initially has center (520,450), the central grid cell. One cell is exactly 160 pixels. The grid and all buttons remain absolutely stationary. Move the existing disk by rigid translation; never replace, duplicate, stretch, teleport or redraw it elsewhere. For each motion interval, interpolate linearly between the stated endpoints, at constant speed; hold precisely at the endpoint for the entire subsequent pause. Each move is horizontal OR vertical, never diagonal, curved, bouncing or overshooting. Leave no trails, arrows, ghost disks, destination dots, coordinate labels or new grid lines. The only title is UNDO centered at (640,65). The existing fixed buttons are RIGHT at (1050,270), UP at (1050,390), and UNDO at (1050,510). All start pale gray. A button turning yellow is the operation activation, requiring no pointer. Only one button is yellow at a time; do not change any button text or position. Execute this exact timeline:
0.00-0.50: disk held at (520,450), all buttons gray.
0.50-1.10: RIGHT turns yellow; disk moves horizontally right from (520,450) to (680,450), y=450 throughout.
1.10-1.50: hold (680,450), RIGHT remains yellow.
1.50-2.10: RIGHT becomes gray and UP turns yellow; disk moves vertically up from (680,450) to (680,290), x=680 throughout.
2.10-2.60: hold (680,290), UP remains yellow.
2.60-3.20: UP becomes gray and UNDO turns yellow; disk moves from (680,290) to (520,290) horizontally LEFT; y stays exactly 290 while x decreases from 680 to 520.
3.20-5.00: disk stays exactly at (520,290); all buttons turn gray at 3.20 and stay gray. There are exactly three moves, with the stated three holds and no other editing operation. At t=4.00 add only the word DONE centered at (1120,80), and hold the entire completed frame without motion through t=5.00. DONE is absent before t=4.00. No further action, correction, subtitles, extra titles, explanations, hands or mouse cursors.

**Control prompt (control, EN)**:

Create exactly 5 seconds of 1280x720, 16:9 flat 2D animation, using the supplied image as the exact first frame. One locked front camera; preserve the first-frame layout and typography without zoom, cuts or reframing. All coordinates below are pixel centers measured from the top-left: x increases rightward and y increases downward. Coordinates are production instructions, never visible text. The fixed grid has vertical lines at x=120,280,440,600,760,920 and horizontal lines at y=210,370,530,690. Exactly one solid blue disk of radius 22 pixels, with a white D rigidly attached at its center, initially has center (520,450), the central grid cell. One cell is exactly 160 pixels. The grid and all buttons remain absolutely stationary. Move the existing disk by rigid translation; never replace, duplicate, stretch, teleport or redraw it elsewhere. For each motion interval, interpolate linearly between the stated endpoints, at constant speed; hold precisely at the endpoint for the entire subsequent pause. Each move is horizontal OR vertical, never diagonal, curved, bouncing or overshooting. Leave no trails, arrows, ghost disks, destination dots, coordinate labels or new grid lines. The only title is UNDO centered at (640,65). The existing fixed buttons are RIGHT at (1050,270), UP at (1050,390), and UNDO at (1050,510). All start pale gray. A button turning yellow is the operation activation, requiring no pointer. Only one button is yellow at a time; do not change any button text or position. Execute this exact timeline:
0.00-0.50: disk held at (520,450), all buttons gray.
0.50-1.10: RIGHT turns yellow; disk moves horizontally right from (520,450) to (680,450), y=450 throughout.
1.10-1.50: hold (680,450), RIGHT remains yellow.
1.50-2.10: RIGHT becomes gray and UP turns yellow; disk moves vertically up from (680,450) to (680,290), x=680 throughout.
2.10-2.60: hold (680,290), UP remains yellow.
2.60-3.20: UP becomes gray and UNDO turns yellow; disk moves from (680,290) to (680,450) vertically DOWN; x stays exactly 680 while y increases from 290 to 450.
3.20-5.00: disk stays exactly at (680,450); all buttons turn gray at 3.20 and stay gray. There are exactly three moves, with the stated three holds and no other editing operation. At t=4.00 add only the word DONE centered at (1120,80), and hold the entire completed frame without motion through t=5.00. DONE is absent before t=4.00. No further action, correction, subtitles, extra titles, explanations, hands or mouse cursors.
