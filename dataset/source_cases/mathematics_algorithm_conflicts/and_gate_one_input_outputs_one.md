### AND Gate: One High Input Produces a High Output

**Case label**: M05
**Status**: Prompt prepared for user-run video generation; video generation and human qualification are pending.

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: An AND gate with inputs 1 and 0 outputs 0.
**Intended video fact (EN)**: With inputs fixed at 1 and 0, the AND gate output lights up and reads 1.

**Video prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. A central logic module is labeled "AND". Two input lamps are stacked vertically on the left, each connected to the module by a separate fixed wire. One output lamp is connected on the right. Each lamp has one large numeric state label beside it. During seconds 0-1 all three lamps are off and all three labels read 0. At second 1 turn on the upper input lamp and change its label from 0 to 1. Keep the lower input lamp off and its label 0 throughout. At second 2 turn on the output lamp and change its label from 0 to 1. The final state clearly shows inputs 1 and 0 with output 1. Keep the AND label, wires, lamp positions and final inputs unchanged. State labels must agree with whether each lamp is on or off. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates the operation has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Control prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. A central logic module is labeled "AND". Two input lamps are stacked vertically on the left, each connected to the module by a separate fixed wire. One output lamp is connected on the right. Each lamp has one large numeric state label beside it. During seconds 0-1 all three lamps are off and all three labels read 0. At second 1 turn on the upper input lamp and change its label from 0 to 1. Keep the lower input lamp off and its label 0 throughout. Keep the output lamp off and its label 0 throughout, including after second 2. The final state clearly shows inputs 1 and 0 with output 0. Keep the AND label, wires, lamp positions and final inputs unchanged. State labels must agree with whether each lamp is on or off. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates the operation has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Human review**：最终输入必须清楚为 1、0；仅输出灯及其状态数字不同。DONE 后保持结果。
