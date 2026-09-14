### Squaring Three: Result Is Six

**Case label**: M12
**Status**: Selected design; prompts prepared for user-run generation. Video generation and human qualification are pending.

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: Three squared equals 9.
**Intended video fact (EN)**: The completed expression 3 squared displays the result 6.

**Video prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. At the center show a large "3²", an equals sign, and an empty result box. The exponent 2 is smaller and clearly raised above the baseline at the upper right of 3. Hold during seconds 0-1. During seconds 1-2 briefly show a pale blue highlight around the input without moving or changing its characters. At second 2.2 reveal a large 6 in the result box. The completed equation reads "3² = 6". Preserve the superscript exactly. Never write 32, change the input to multiplication, or show an intermediate expression. Only the final result digit appears; the input remains fixed. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Control prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. At the center show a large "3²", an equals sign, and an empty result box. The exponent 2 is smaller and clearly raised above the baseline at the upper right of 3. Hold during seconds 0-1. During seconds 1-2 briefly show a pale blue highlight around the input without moving or changing its characters. At second 2.2 reveal a large 9 in the result box. The completed equation reads "3² = 9". Preserve the superscript exactly. Never write 32, change the input to multiplication, or show an intermediate expression. Only the final result digit appears; the input remains fixed. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Human review**：上标 2 必须位于 3 的右上角，不能变成 32；只改变最终结果，冲突为 6，对照为 9。
