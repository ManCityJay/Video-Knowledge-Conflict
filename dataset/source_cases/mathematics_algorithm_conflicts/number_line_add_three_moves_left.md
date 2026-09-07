### Number Line: Adding Three Moves Left to Negative Three

**Priority**：P2，第二轮。2026-09-07 重写；生成后仍需人工审核。
**Standard prior**：常规数轴向右数值增大，从 0 加 3 应向右到 +3。
**Conflict**：指令固定为 +3，标记却从 0 向左移动三格，到 −3。
**Localized edit**：只反转一次位移的方向；数字与刻度一律不改，不要求向右却到左端。
**Visual evidence**：七个刻度保持 −3 到 3 的正常顺序；+3 指令、位移方向和终点同时可核查。大数字与运动证据相互约束。
**Normal fact (EN)**: On a conventional number line increasing to the right, starting at 0 and adding 3 moves right to +3.
**Intended video fact (EN)**: With the instruction +3 fixed on screen, the marker moves left from 0 to -3 on an otherwise correct number line.

**Video prompt**：

> A clean flat 2D math teaching animation on a white background, fixed front view, one continuous 5-second shot. A conventional horizontal number line has exactly seven equally spaced ticks labeled -3, -2, -1, 0, 1, 2, 3 from left to right. The axis has a small fixed arrowhead at the right end. A large fixed operation badge above the axis reads "+3". A red circular marker begins just above the 0 tick, never covering a number. A "GO" button sits separately below. During seconds 0-1 hold this initial state. At seconds 1-1.5 a cursor clicks GO once and parks away. During seconds 1.5-3, the red marker moves smoothly left by exactly three tick intervals, passing -1 and -2 and stopping above -3. During seconds 3-5 hold the endpoint. Keep the +3 badge, every tick, every number, the axis arrowhead, spacing, and camera fixed. No teleporting, relabeling, extra markers, trails, corrective motion, people, hands, speech, subtitles, decorative text, cuts, or zoom.

**Control prompt**：

> A clean flat 2D math teaching animation on a white background, fixed front view, one continuous 5-second shot. A conventional horizontal number line has exactly seven equally spaced ticks labeled -3, -2, -1, 0, 1, 2, 3 from left to right. The axis has a small fixed arrowhead at the right end. A large fixed operation badge above the axis reads "+3". A red circular marker begins just above the 0 tick, never covering a number. A "GO" button sits separately below. During seconds 0-1 hold this initial state. At seconds 1-1.5 a cursor clicks GO once and parks away. During seconds 1.5-3, the red marker moves smoothly right by exactly three tick intervals, passing 1 and 2 and stopping above 3. During seconds 3-5 hold the endpoint. Keep the +3 badge, every tick, every number, the axis arrowhead, spacing, and camera fixed. No teleporting, relabeling, extra markers, trails, corrective motion, people, hands, speech, subtitles, decorative text, cuts, or zoom.

**Human review**：必须先确认数轴标签本身正确，再看 +3 指令及红点到 −3；若把右侧 3 改写为 −3，或实际仍右移，不通过。
