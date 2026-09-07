### Calculator: Two Plus Two Displays Five

**Priority**：P2，OCR 基线。2026-09-07 重写；生成后仍需人工审核。
**Standard prior**：标准加法计算 2 + 2 的结果是 4。
**Conflict**：输入已固定为 2 + 2，点击等号后结果显示 5。
**Localized edit**：只改变结果格的一个数字：4 → 5。
**Visual evidence**：保留输入与输出同时可读；不让手遮挡按键，不让四次输入成为额外生成难点。此案例主要测数字读取与知识先验竞争，单独标为 OCR 基线。
**Normal fact (EN)**: Evaluating 2 + 2 on a standard calculator gives 4.
**Intended video fact (EN)**: After one equals-button click on the pre-entered expression 2 + 2, the calculator result shows 5.

**Video prompt**：

> A minimalist flat 2D calculator teaching interface on a white background, locked front view, one continuous 5-second shot. The title is "CALCULATOR". A large input line already reads "2 + 2" and stays unchanged for the entire shot. Directly below is one empty large result box. There is only one large "=" button below the result box; no keypad or other controls. Use very large crisp dark text. During seconds 0-1 hold this pre-entered expression and empty result. At seconds 1-1.5 a cursor clicks the equals button once and parks well away. At second 1.5, the single digit "5" appears in the result box. Hold the unchanged input and this result together through second 5. Do not display an intermediate result, another calculation, explanations, error messages, or commentary. No hands, people, speech, subtitles, decorative text, cuts, zoom, or text morphing.

**Control prompt**：

> A minimalist flat 2D calculator teaching interface on a white background, locked front view, one continuous 5-second shot. The title is "CALCULATOR". A large input line already reads "2 + 2" and stays unchanged for the entire shot. Directly below is one empty large result box. There is only one large "=" button below the result box; no keypad or other controls. Use very large crisp dark text. During seconds 0-1 hold this pre-entered expression and empty result. At seconds 1-1.5 a cursor clicks the equals button once and parks well away. At second 1.5, the single digit "4" appears in the result box. Hold the unchanged input and this result together through second 5. Do not display an intermediate result, another calculation, explanations, error messages, or commentary. No hands, people, speech, subtitles, decorative text, cuts, zoom, or text morphing.

**Human review**：2 + 2 必须始终可辨；结果必须是稳定单个 5。把输入改成 2 + 3、先显示 4 再变 5、数字模糊都不通过。生成器成功显示 5 也不代表数学几何证据成立，应按 OCR 基线分析。
