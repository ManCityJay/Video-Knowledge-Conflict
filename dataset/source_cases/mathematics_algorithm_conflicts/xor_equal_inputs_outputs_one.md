### XOR: Equal High Inputs Keep a High Output

**Case label**: M19
**Status**: Selected design; prompts prepared for user-run generation. Video generation and human qualification are pending.

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: An XOR gate outputs 1 for inputs 0 and 1, then outputs 0 when the inputs become 1 and 1.
**Intended video fact (EN)**: After the inputs change from 0 and 1 to 1 and 1, the XOR output stays lit and reads 1.

**Video prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. A central logic module is labeled "XOR". Two vertically stacked input lamps on the left and one output lamp on the right connect to it with fixed wires. Each lamp has one clear large numeric state label. During seconds 0-1 the upper input is off and reads 0, the lower input is on and reads 1, and the output is on and reads 1. At second 1.5 turn on the upper input lamp and change its digit from 0 to 1. The lower input remains on and reads 1. Keep the output lamp on with its label 1 after the input change and throughout the rest of the video. The completed state clearly shows inputs 1, 1 and output 1. Keep the XOR label, wires, lamp positions, and final input states unchanged. Each numeric state must agree with its lamp being on or off. Preserve the initial-to-final transition, not a static truth table. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Control prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. A central logic module is labeled "XOR". Two vertically stacked input lamps on the left and one output lamp on the right connect to it with fixed wires. Each lamp has one clear large numeric state label. During seconds 0-1 the upper input is off and reads 0, the lower input is on and reads 1, and the output is on and reads 1. At second 1.5 turn on the upper input lamp and change its digit from 0 to 1. The lower input remains on and reads 1. At second 2 turn off the output lamp and change its label from 1 to 0. The completed state clearly shows inputs 1, 1 and output 0. Keep the XOR label, wires, lamp positions, and final input states unchanged. Each numeric state must agree with its lamp being on or off. Preserve the initial-to-final transition, not a static truth table. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Human review**：保留输入从 0、1 变为 1、1 的过程；两版只改变最终输出，数字和灯光一致，DONE 后不再变化。
