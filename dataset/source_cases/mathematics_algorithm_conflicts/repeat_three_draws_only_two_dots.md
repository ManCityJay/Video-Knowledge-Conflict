### Repeat Three: Only Two Dots Drawn

**Case label**: M36
**Status**: User-approved design; video generation and human qualification are pending.

- **正常知识与冲突：** 重复 3 次，每次画一个点，完成后应有三个点；冲突版只画两个就结束。
- **画面：** 标题固定为 REPEAT 3，下方空白画布和 RUN 按钮。点击后在 1.3 秒、2.0 秒分别画一个蓝点；冲突版不执行第三次。
- **正常对照：** 2.7 秒画出第三个蓝点。
- **重点：** 两版均在第 3 秒将 RUN 变为 DONE，之后保持到第 5 秒。冲突版绝不能迟到补点，也不添加第三个点的虚影或占位圆。

**Completion cue**: Both roles show neutral DONE at second 3 and hold their completed result through second 5. M36 changes the RUN button itself to DONE; the other cases use the upper-right status label. Completion is not a correctness judgment.

**Normal fact (EN)**: An unconditional loop that draws one dot per iteration and repeats three times finishes with three dots.
**Intended video fact (EN)**: The REPEAT 3 run draws only two dots, changes its run button to DONE, and remains finished with no third dot.

**Video prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. At the top print the large immutable instruction "REPEAT 3". Below it is an entirely empty drawing area and one rectangular button labeled "RUN". This is one unconditional run: every iteration immediately draws exactly one identical solid blue dot, with no branch, cancellation, exception, break, or variable loop limit. Hold during seconds 0-1. At second 1 a cursor clicks RUN once, then parks outside the drawing area. At second 1.3 draw one dot at the left position. At second 2.0 draw a second dot at the center position. Once drawn, dots stay fixed and fully visible. Draw no dot at second 2.7 or at any later time. The completed result contains exactly TWO blue dots, at the left and center positions; the right region stays entirely blank. At exactly second 3, change the button label from "RUN" to the neutral dark-gray word "DONE". Keep the top instruction "REPEAT 3" unchanged. Hold the finished button and final dots still through second 5. DONE means the run has ended, not that its output is correct. There is no active timer, progress indicator, error, pause, extra click, looping playback, late dot, ghost dot, empty outlined slot, or correction.

**Control prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. At the top print the large immutable instruction "REPEAT 3". Below it is an entirely empty drawing area and one rectangular button labeled "RUN". This is one unconditional run: every iteration immediately draws exactly one identical solid blue dot, with no branch, cancellation, exception, break, or variable loop limit. Hold during seconds 0-1. At second 1 a cursor clicks RUN once, then parks outside the drawing area. At second 1.3 draw one dot at the left position. At second 2.0 draw a second dot at the center position. Once drawn, dots stay fixed and fully visible. At second 2.7 draw a third identical dot at the right position with the same spacing. The completed result contains exactly THREE blue dots in a row. At exactly second 3, change the button label from "RUN" to the neutral dark-gray word "DONE". Keep the top instruction "REPEAT 3" unchanged. Hold the finished button and final dots still through second 5. DONE means the run has ended, not that its output is correct. There is no active timer, progress indicator, error, pause, extra click, looping playback, late dot, ghost dot, empty outlined slot, or correction.

**Human review**：两版均在第 3 秒将 RUN 变为 DONE，之后保持到第 5 秒。冲突版绝不能迟到补点，也不添加第三个点的虚影或占位圆。 最终结果必须在 DONE 出现前确定，DONE 与结果共同保持约 2 秒；DONE 缺失、提前出现、遮挡结果或之后继续执行均不通过。普通对照也需要独立核验，不因显示 DONE 就视为正确。
