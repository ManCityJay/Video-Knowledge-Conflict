### Offset Ruler: Endpoint Read as Length

**Case label**: M33
**Status**: User-approved design; video generation and human qualification are pending.

- **正常知识与冲突：** 短棒从尺子的 3 cm 延伸到 8 cm，长度应为 5 cm；冲突版读数为 8 cm。
- **画面：** 尺子和短棒从第一秒就摆好。短棒左端对齐 3、右端对齐 8，两端有对齐引导线。测量括号沿短棒展开，显示 8 cm。
- **正常对照：** 相同位置显示 5 cm。
- **重点：** 只改变读数。尺子起点 0、端点 3 和 8 同时清晰可见，不能把短棒移到 0 开始。属于依赖文字读取的测量例子。

**Completion cue**: Both roles show neutral DONE at second 3 and hold their completed result through second 5. M36 changes the RUN button itself to DONE; the other cases use the upper-right status label. Completion is not a correctness judgment.

**Normal fact (EN)**: A rod spanning the 3 cm and 8 cm marks on a ruler has a length of 5 cm.
**Intended video fact (EN)**: The rod remains aligned with 3 cm and 8 cm, but the completed measurement reads 8 cm beside DONE.

**Video prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. A horizontal ruler has evenly spaced unit ticks from 0 through 8, but print only the three large tick labels "0", "3", and "8" at their correct positions and one small unit label "cm". The 3 tick is exactly three eighths of the distance from 0 to 8. A rigid blue rod above the ruler starts exactly over the 3 tick and ends exactly over the 8 tick. Thin stationary vertical guide lines connect its endpoints to these ticks. Hold the complete setup during seconds 0-1. During 1.0-2.0 draw a single measurement bracket above the rod between its existing endpoints; never move or resize the rod. At second 2.2 show the single large readout "8 cm" above this bracket. Keep all ruler labels, unit spacing, endpoint guides, rod geometry, and bracket geometry unchanged. The readout is a reported length, not the coordinate of one endpoint. No additional readouts or intermediate answers. At exactly second 3, show the single neutral dark-gray word "DONE" at the upper right. Hold DONE and the entire completed result unchanged and unobstructed from seconds 3-5. DONE indicates execution has ended, not correctness. Do not add a check mark, error message, correctness color, further action, correction, or late output.

**Control prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. A horizontal ruler has evenly spaced unit ticks from 0 through 8, but print only the three large tick labels "0", "3", and "8" at their correct positions and one small unit label "cm". The 3 tick is exactly three eighths of the distance from 0 to 8. A rigid blue rod above the ruler starts exactly over the 3 tick and ends exactly over the 8 tick. Thin stationary vertical guide lines connect its endpoints to these ticks. Hold the complete setup during seconds 0-1. During 1.0-2.0 draw a single measurement bracket above the rod between its existing endpoints; never move or resize the rod. At second 2.2 show the single large readout "5 cm" above this bracket. Keep all ruler labels, unit spacing, endpoint guides, rod geometry, and bracket geometry unchanged. The readout is a reported length, not the coordinate of one endpoint. No additional readouts or intermediate answers. At exactly second 3, show the single neutral dark-gray word "DONE" at the upper right. Hold DONE and the entire completed result unchanged and unobstructed from seconds 3-5. DONE indicates execution has ended, not correctness. Do not add a check mark, error message, correctness color, further action, correction, or late output.

**Human review**：只改变读数。尺子起点 0、端点 3 和 8 同时清晰可见，不能把短棒移到 0 开始。属于依赖文字读取的测量例子。 最终结果必须在 DONE 出现前确定，DONE 与结果共同保持约 2 秒；DONE 缺失、提前出现、遮挡结果或之后继续执行均不通过。普通对照也需要独立核验，不因显示 DONE 就视为正确。
