### Redo: Wrong Historical Operation Repeated

**Case label**: M50
**Candidate number**: 18
**中文名称**: 重做操作：重做了错误的历史动作
**Status**: User-approved design; prompts directly revised with explicit user authorization on 2026-09-14. Regeneration and human review are pending.

- **正常知识与冲突：** 重做应恢复刚被撤销的操作；冲突版重复了另一条历史操作。
- **画面：** 圆点先右移、再上移，点击 UNDO 后正确下移。随后点击 REDO，圆点却继续向右。
- **正常对照：** REDO 让圆点重新向上，回到撤销之前的位置。
- **重点：** 撤销步骤先正确完成，唯一错误放在重做步骤。UNDO 与 REDO 之间没有新编辑；每步短距离移动并有可见停顿，保持同一连续镜头。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: Redo after undoing the latest up move must reapply that up move, provided no intervening edit changes the history.
**Intended video fact (EN)**: After right, up, and a correct undo-down sequence, REDO moves the dot right instead of up.

**Prompt authoring**: 本次用户明确授权跳过 Luna，直接修订 v001 与匹配 control 提示词。使用下方固定首帧与逐段坐标时间表；不使用 author --force。原问题、视频任务及生成历史保留。

**Human review**: 撤销步骤先正确完成，唯一错误放在重做步骤。UNDO 与 REDO 之间没有新编辑；每步短距离移动并有可见停顿，保持同一连续镜头。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。

**Fixed layout revision — 2026-09-14**: 固定 1280×720 网格，一格为 160 像素。圆点中心依次为 (520,450) → (680,450) → (680,290) → (680,450) → (840,450)。UNDO 必须精确返回右移后的坐标，REDO 仅水平右移；3.3 秒停止，4 秒显示 DONE。control 仅把 REDO 改为上移至 (680,290)。

**First frame**: `dataset/source_assets/mathematics_algorithm_conflicts/redo_repeats_wrong_operation/first_frame_fixed_layout.png`

**Video prompt (v001, EN)**:

Create exactly 5 seconds of 1280x720, 16:9 flat 2D animation, using the supplied image as the exact first frame. One locked front camera; preserve the first-frame layout and typography without zoom, cuts or reframing. All coordinates below are pixel centers measured from the top-left: x increases rightward and y increases downward. Coordinates are production instructions, never visible text. The fixed grid has vertical lines at x=120,280,440,600,760,920 and horizontal lines at y=210,370,530,690. Exactly one solid blue disk of radius 22 pixels, with a white D rigidly attached at its center, initially has center (520,450), the central grid cell. One cell is exactly 160 pixels. The grid and all buttons remain absolutely stationary. Move the existing disk by rigid translation; never replace, duplicate, stretch, teleport or redraw it elsewhere. For each motion interval, interpolate linearly between the stated endpoints, at constant speed; hold precisely at the endpoint for the entire subsequent pause. Each move is horizontal OR vertical, never diagonal, curved, bouncing or overshooting. Leave no trails, arrows, ghost disks, destination dots, coordinate labels or new grid lines. The only title is REDO centered at (640,65). The fixed buttons are RIGHT at (1050,220), UP at (1050,320), UNDO at (1050,420), REDO at (1050,520). All start pale gray. A button turning yellow is the operation activation, requiring no pointer. Only one button is yellow at a time; no text or button changes position. Execute this exact timeline:
0.00-0.40: disk held at (520,450), all buttons gray.
0.40-0.90: RIGHT turns yellow; disk moves horizontally right from (520,450) to (680,450), y=450 throughout.
0.90-1.20: hold (680,450), RIGHT remains yellow.
1.20-1.70: RIGHT becomes gray and UP turns yellow; disk moves vertically up from (680,450) to (680,290), x=680 throughout.
1.70-2.00: hold (680,290), UP remains yellow.
2.00-2.50: UP becomes gray and UNDO turns yellow; disk moves vertically down from (680,290) to (680,450), x=680 throughout. Stop at y=450, precisely the same location occupied at 0.90-1.20, never one row below it.
2.50-2.80: hold (680,450), UNDO remains yellow. No intervening edit.
2.80-3.30: UNDO becomes gray and REDO turns yellow; disk moves from (680,450) to (840,450) horizontally RIGHT; y stays exactly 450 while x increases from 680 to 840.
3.30-5.00: disk stays exactly at (840,450); all buttons turn gray at 3.30 and stay gray. Exactly four moves, in the stated order. The activation label during the fourth move is always REDO. At t=4.00 add only the word DONE centered at (1120,80), and hold the entire completed frame without motion through t=5.00. DONE is absent before t=4.00. No further action, correction, subtitles, extra titles, explanations, hands or mouse cursors.

**Control prompt (control, EN)**:

Create exactly 5 seconds of 1280x720, 16:9 flat 2D animation, using the supplied image as the exact first frame. One locked front camera; preserve the first-frame layout and typography without zoom, cuts or reframing. All coordinates below are pixel centers measured from the top-left: x increases rightward and y increases downward. Coordinates are production instructions, never visible text. The fixed grid has vertical lines at x=120,280,440,600,760,920 and horizontal lines at y=210,370,530,690. Exactly one solid blue disk of radius 22 pixels, with a white D rigidly attached at its center, initially has center (520,450), the central grid cell. One cell is exactly 160 pixels. The grid and all buttons remain absolutely stationary. Move the existing disk by rigid translation; never replace, duplicate, stretch, teleport or redraw it elsewhere. For each motion interval, interpolate linearly between the stated endpoints, at constant speed; hold precisely at the endpoint for the entire subsequent pause. Each move is horizontal OR vertical, never diagonal, curved, bouncing or overshooting. Leave no trails, arrows, ghost disks, destination dots, coordinate labels or new grid lines. The only title is REDO centered at (640,65). The fixed buttons are RIGHT at (1050,220), UP at (1050,320), UNDO at (1050,420), REDO at (1050,520). All start pale gray. A button turning yellow is the operation activation, requiring no pointer. Only one button is yellow at a time; no text or button changes position. Execute this exact timeline:
0.00-0.40: disk held at (520,450), all buttons gray.
0.40-0.90: RIGHT turns yellow; disk moves horizontally right from (520,450) to (680,450), y=450 throughout.
0.90-1.20: hold (680,450), RIGHT remains yellow.
1.20-1.70: RIGHT becomes gray and UP turns yellow; disk moves vertically up from (680,450) to (680,290), x=680 throughout.
1.70-2.00: hold (680,290), UP remains yellow.
2.00-2.50: UP becomes gray and UNDO turns yellow; disk moves vertically down from (680,290) to (680,450), x=680 throughout. Stop at y=450, precisely the same location occupied at 0.90-1.20, never one row below it.
2.50-2.80: hold (680,450), UNDO remains yellow. No intervening edit.
2.80-3.30: UNDO becomes gray and REDO turns yellow; disk moves from (680,450) to (680,290) vertically UP; x stays exactly 680 while y decreases from 450 to 290.
3.30-5.00: disk stays exactly at (680,290); all buttons turn gray at 3.30 and stay gray. Exactly four moves, in the stated order. The activation label during the fourth move is always REDO. At t=4.00 add only the word DONE centered at (1120,80), and hold the entire completed frame without motion through t=5.00. DONE is absent before t=4.00. No further action, correction, subtitles, extra titles, explanations, hands or mouse cursors.
