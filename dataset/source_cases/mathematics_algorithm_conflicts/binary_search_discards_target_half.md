### Binary Search: The Half Containing the Target Is Discarded

**Priority**：P1，首轮。2026-09-07 重写；生成后仍需人工审核。
**Standard prior**：有序数组 [1,3,5,7,9]，目标 3 小于中点 5，下一轮搜索区间应为 [1,3]。
**Conflict**：下一轮 ACTIVE 框却圈住 [7,9]，目标 3 留在框外。
**Localized edit**：只改变更新后的搜索区间；数组、目标和中点均不变。
**Visual evidence**：用精确数字消除旧版积木高度比较的歧义；ACTIVE 标签明确框代表保留区间，不让亮框既可解释为保留也可解释为丢弃。
**Normal fact (EN)**: For binary search on the ascending array [1, 3, 5, 7, 9], target 3 is less than midpoint 5, so the next active interval is [1, 3].
**Intended video fact (EN)**: After one binary-search step with target 3 and midpoint 5, the active interval becomes [7, 9], excluding target 3.

**Video prompt**：

> A clean computer-science teaching animation, flat 2D shapes on a white background, fixed front view, one continuous 5-second shot. Large high-contrast labels, no people, hands, speech, subtitles, decorative text, cuts, or camera movement. The title is "BINARY SEARCH". Exactly five equal array cells remain in a horizontal row, labeled 1, 3, 5, 7, 9 from left to right. A large fixed badge says "TARGET 3". A small fixed "MID" pointer marks the center cell 5. A cyan outline labeled "ACTIVE" initially surrounds all five cells; the label belongs to the outline. A large "STEP" button sits below. During seconds 0-1 hold the complete array and full active interval. At seconds 1-1.5 a cursor clicks STEP once and parks below it. During seconds 1.5-3, the single ACTIVE outline smoothly shrinks toward the right until it encloses exactly cells 7 and 9. Cells 1, 3, and 5 remain fully readable outside the outline. During seconds 3-5 hold this next active interval. The MID pointer continues to mark the pivot used for this one step; do not compute another midpoint or perform another search step. Keep all five cells, their values, the target badge, and the camera fixed. No cells fade, move, change, or disappear.

**Control prompt**：

> A clean computer-science teaching animation, flat 2D shapes on a white background, fixed front view, one continuous 5-second shot. Large high-contrast labels, no people, hands, speech, subtitles, decorative text, cuts, or camera movement. The title is "BINARY SEARCH". Exactly five equal array cells remain in a horizontal row, labeled 1, 3, 5, 7, 9 from left to right. A large fixed badge says "TARGET 3". A small fixed "MID" pointer marks the center cell 5. A cyan outline labeled "ACTIVE" initially surrounds all five cells; the label belongs to the outline. A large "STEP" button sits below. During seconds 0-1 hold the complete array and full active interval. At seconds 1-1.5 a cursor clicks STEP once and parks below it. During seconds 1.5-3, the single ACTIVE outline smoothly shrinks toward the left until it encloses exactly cells 1 and 3. Cells 5, 7, and 9 remain fully readable outside the outline. During seconds 3-5 hold this next active interval. The MID pointer continues to mark the pivot used for this one step; do not compute another midpoint or perform another search step. Keep all five cells, their values, the target badge, and the camera fixed. No cells fade, move, change, or disappear.

**Human review**：五个数字必须按序保持不变，目标必须为 3，中点必须为 5。ACTIVE 只圈 7/9；若框的含义不清楚，或目标被擦除，不通过。
