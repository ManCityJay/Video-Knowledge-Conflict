### Absolute Value: Negative Input Stays Negative

**Case label**: M11
**Status**: Selected design; prompts prepared for user-run generation. Video generation and human qualification are pending.

**First frame**: `dataset/source_assets/mathematics_algorithm_conflicts/absolute_value_negative_result/first_frame.png` (shared by both roles).

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: The absolute value of -3 is 3.
**Intended video fact (EN)**: The completed calculation shows |-3| = -3.

**Video prompt**：

> Animate the supplied first frame exactly, using one fixed 5-second shot. Preserve its white background and the entire input geometry. The input is minus three between two straight parallel black vertical line segments. Both vertical lines are immutable geometric strokes: keep their lengths, thicknesses, flat ends and positions exactly as in the reference image in every frame. Do not re-typeset the input. Keep the equals sign and the empty output box fixed. Hold the reference image unchanged during seconds 0-1. During seconds 1-2 briefly tint only the input minus sign and digit 3 pale blue, then restore them to black; the two vertical strokes stay black. At second 2.2 reveal a large black -3 centered inside the existing output box. The output minus sign must remain clearly visible.  At second 3 reveal a small neutral dark-gray DONE at the upper right, well away from the equation. Hold the completed equation and DONE still until second 5. DONE means finished, not correct. Keep the two input delimiters perfectly straight with no horizontal end strokes or curves. No new marks, extra answers, camera motion, cuts, voice, explanation captions, correctness symbols or later correction.

**Control prompt**：

> Animate the supplied first frame exactly, using one fixed 5-second shot. Preserve its white background and the entire input geometry. The input is minus three between two straight parallel black vertical line segments. Both vertical lines are immutable geometric strokes: keep their lengths, thicknesses, flat ends and positions exactly as in the reference image in every frame. Do not re-typeset the input. Keep the equals sign and the empty output box fixed. Hold the reference image unchanged during seconds 0-1. During seconds 1-2 briefly tint only the input minus sign and digit 3 pale blue, then restore them to black; the two vertical strokes stay black. At second 2.2 reveal a large black 3 centered inside the existing output box. There is no output minus sign.  At second 3 reveal a small neutral dark-gray DONE at the upper right, well away from the equation. Hold the completed equation and DONE still until second 5. DONE means finished, not correct. Keep the two input delimiters perfectly straight with no horizontal end strokes or curves. No new marks, extra answers, camera motion, cuts, voice, explanation captions, correctness symbols or later correction.

**Human review**：只改变结果前是否有负号；输入绝对值符号和 -3 全程不变。绝对值符号必须是两条无弯钩的直竖线，不得出现花括号；只高亮中间 -3，竖线始终保持黑色。DONE 与完整等式保持到第 5 秒。
