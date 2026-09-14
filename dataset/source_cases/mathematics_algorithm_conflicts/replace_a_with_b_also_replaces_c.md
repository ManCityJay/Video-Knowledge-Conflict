### Replace A with B: C Is Also Replaced

**Case label**: M35
**Status**: User-approved design; video generation and human qualification are pending.

- **正常知识与冲突：** 把 ACA 中所有 A 替换为 B，应得到 BCB；冲突版得到 BBB。
- **画面：** 三格大字母 ACA 从开始保持清楚，上方写 A TO B，下方按钮为 REPLACE。点击一次，两侧 A 变为 B，中间 C 也错误变为 B。
- **正常对照：** 两侧变为 B，中间 C 保留，最终 BCB。
- **重点：** 仅中间字符的最终状态不同。没有字母移动、增减或额外替换；DONE 出现后不再修正。

**Completion cue**: Both roles show neutral DONE at second 3 and hold their completed result through second 5. M36 changes the RUN button itself to DONE; the other cases use the upper-right status label. Completion is not a correctness judgment.

**Normal fact (EN)**: Replacing every A with B in the string ACA produces BCB; the C is not a match and stays unchanged.
**Intended video fact (EN)**: The replace-all operation targeting A produces BBB from ACA and displays DONE, replacing the nonmatching C as well.

**Video prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. There are exactly three large stationary outlined character cells reading "A", "C", "A" from left to right. Above them print "A TO B" and below them place one button labeled "REPLACE". This is a replace-all operation targeting only A. During seconds 0-1 hold the complete input. At second 1 a cursor clicks REPLACE once, then parks away from every letter. At second 1.4 change the LEFT and RIGHT characters from A to B using clean instantaneous glyph replacement, not shape morphing. At second 2.2 also change the CENTER character from C to B. The completed three-character result reads "BBB". Never move, resize, add or remove character cells. Keep the operation label and button label unchanged. Show no alternative strings, second click, extra character, explanation, or later correction. At exactly second 3, show the single neutral dark-gray word "DONE" at the upper right. Hold DONE and the entire completed result unchanged and unobstructed from seconds 3-5. DONE indicates execution has ended, not correctness. Do not add a check mark, error message, correctness color, further action, correction, or late output.

**Control prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. There are exactly three large stationary outlined character cells reading "A", "C", "A" from left to right. Above them print "A TO B" and below them place one button labeled "REPLACE". This is a replace-all operation targeting only A. During seconds 0-1 hold the complete input. At second 1 a cursor clicks REPLACE once, then parks away from every letter. At second 1.4 change the LEFT and RIGHT characters from A to B using clean instantaneous glyph replacement, not shape morphing. Keep the CENTER character C unchanged throughout. The completed three-character result reads "BCB". Never move, resize, add or remove character cells. Keep the operation label and button label unchanged. Show no alternative strings, second click, extra character, explanation, or later correction. At exactly second 3, show the single neutral dark-gray word "DONE" at the upper right. Hold DONE and the entire completed result unchanged and unobstructed from seconds 3-5. DONE indicates execution has ended, not correctness. Do not add a check mark, error message, correctness color, further action, correction, or late output.

**Human review**：仅中间字符的最终状态不同。没有字母移动、增减或额外替换；DONE 出现后不再修正。 最终结果必须在 DONE 出现前确定，DONE 与结果共同保持约 2 秒；DONE 缺失、提前出现、遮挡结果或之后继续执行均不通过。普通对照也需要独立核验，不因显示 DONE 就视为正确。
