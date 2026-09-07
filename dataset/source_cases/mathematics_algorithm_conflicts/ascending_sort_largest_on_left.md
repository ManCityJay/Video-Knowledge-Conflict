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
