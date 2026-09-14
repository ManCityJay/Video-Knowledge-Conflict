### Bar Chart: One Vote Taller than Two

**Case label**: M34
**Status**: User-approved design; video generation and human qualification are pending.

- **正常知识与冲突：** 同一线性刻度下，两票的柱子应是一票的两倍高；冲突版橙色一票柱更高。
- **画面：** 左侧保留两张蓝票和一张橙票，右侧柱状图使用统一的 0、1、2、3 刻度。两柱升起，蓝柱到 2，橙柱错误升到 3。
- **正常对照：** 蓝柱到 2，橙柱到 1。
- **重点：** 只改变橙柱高度，票数、颜色和基线不变。柱子下方固定保留蓝色 2、橙色 1，不添加正确或错误提示。

**Completion cue**: Both roles show neutral DONE at second 3 and hold their completed result through second 5. M36 changes the RUN button itself to DONE; the other cases use the upper-right status label. Completion is not a correctness judgment.

**Normal fact (EN)**: On a common zero-based linear scale, a bar for two votes is twice as high as a bar for one vote.
**Intended video fact (EN)**: Although the displayed votes remain two blue and one orange, the completed orange one-vote bar is taller than the blue two-vote bar.

**Video prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. In the same frame, the left input panel contains exactly two separate blue vote cards and one orange vote card, all stationary and unobscured. The right chart has two equal-width bars, blue on the left and orange on the right, and one shared linear vertical scale with evenly spaced ticks labeled "0", "1", "2", "3". Both bars start from the same zero baseline. Below their fixed positions print a blue "2" and an orange "1"; these are the source vote counts and never change or move. Hold the inputs and initially zero-height bars during seconds 0-1. During seconds 1-2.8 grow the blue bar smoothly to height 2 on the shared scale. During the same interval grow the orange bar to height 3, visibly taller than the blue bar, while its fixed source count beneath remains "1". The source panel always contains two blue cards and one orange card. Do not swap colors, change the count labels, break the axis, move a baseline, add a second scale, or change the width of a bar. Keep the final bar heights fixed. At exactly second 3, show the single neutral dark-gray word "DONE" at the upper right. Hold DONE and the entire completed result unchanged and unobstructed from seconds 3-5. DONE indicates execution has ended, not correctness. Do not add a check mark, error message, correctness color, further action, correction, or late output.

**Control prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. In the same frame, the left input panel contains exactly two separate blue vote cards and one orange vote card, all stationary and unobscured. The right chart has two equal-width bars, blue on the left and orange on the right, and one shared linear vertical scale with evenly spaced ticks labeled "0", "1", "2", "3". Both bars start from the same zero baseline. Below their fixed positions print a blue "2" and an orange "1"; these are the source vote counts and never change or move. Hold the inputs and initially zero-height bars during seconds 0-1. During seconds 1-2.8 grow the blue bar smoothly to height 2 on the shared scale. During the same interval grow the orange bar to height 1, exactly half as tall as the blue bar, while its fixed source count beneath remains "1". The source panel always contains two blue cards and one orange card. Do not swap colors, change the count labels, break the axis, move a baseline, add a second scale, or change the width of a bar. Keep the final bar heights fixed. At exactly second 3, show the single neutral dark-gray word "DONE" at the upper right. Hold DONE and the entire completed result unchanged and unobstructed from seconds 3-5. DONE indicates execution has ended, not correctness. Do not add a check mark, error message, correctness color, further action, correction, or late output.

**Human review**：只改变橙柱高度，票数、颜色和基线不变。柱子下方固定保留蓝色 2、橙色 1，不添加正确或错误提示。 最终结果必须在 DONE 出现前确定，DONE 与结果共同保持约 2 秒；DONE 缺失、提前出现、遮挡结果或之后继续执行均不通过。普通对照也需要独立核验，不因显示 DONE 就视为正确。
