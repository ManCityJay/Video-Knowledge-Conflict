### Equal Sharing: Four Tokens Split Three and One

**Case label**: M31
**Status**: User-approved design; video generation and human qualification are pending.

- **正常知识与冲突：** 四枚相同筹码平均分到两个盘子，应为两枚和两枚；冲突版完成后为左三右一。
- **画面：** 俯视教学动画，中央四枚筹码，左右各一个空盘。先依次放入左盘一枚、右盘一枚、左盘一枚；最后一枚也进入左盘。
- **正常对照：** 最后一枚进入右盘，完成后两盘各两枚。
- **重点：** 只改变最后一枚筹码的目的地。四枚始终可见、不重叠；DONE 出现后不再转移筹码。

**Completion cue**: Both roles show neutral DONE at second 3 and hold their completed result through second 5. M36 changes the RUN button itself to DONE; the other cases use the upper-right status label. Completion is not a correctness judgment.

**Normal fact (EN)**: Sharing four identical tokens equally between two plates gives two tokens on each plate.
**Intended video fact (EN)**: After the equal-sharing operation displays DONE, the left plate holds three tokens and the right plate holds one token.

**Video prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. The title reads "SHARE EQUALLY". There are exactly four identical blue circular tokens in a vertical row in the center, and two empty shallow white plates with dark outlines, one on the left and one on the right. Keep all plates and tokens entirely inside the frame. Hold this initial state during seconds 0-1. Perform a single four-token distribution: during 1.0-1.4 move token one to the left plate; during 1.4-1.8 move token two to the right plate; during 1.8-2.2 move token three to the left plate. Already placed tokens stay still, separated and fully visible. During 2.2-2.8 move the fourth and final token to the left plate. The completed distribution is exactly three separate tokens on the left plate and one on the right plate; the center is empty. Keep exactly four tokens throughout; no token changes identity, disappears, duplicates, overlaps another, or leaves a plate after placement. At exactly second 3, show the single neutral dark-gray word "DONE" at the upper right. Hold DONE and the entire completed result unchanged and unobstructed from seconds 3-5. DONE indicates execution has ended, not correctness. Do not add a check mark, error message, correctness color, further action, correction, or late output.

**Control prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. The title reads "SHARE EQUALLY". There are exactly four identical blue circular tokens in a vertical row in the center, and two empty shallow white plates with dark outlines, one on the left and one on the right. Keep all plates and tokens entirely inside the frame. Hold this initial state during seconds 0-1. Perform a single four-token distribution: during 1.0-1.4 move token one to the left plate; during 1.4-1.8 move token two to the right plate; during 1.8-2.2 move token three to the left plate. Already placed tokens stay still, separated and fully visible. During 2.2-2.8 move the fourth and final token to the right plate. The completed distribution is exactly two separate tokens on each plate; the center is empty. Keep exactly four tokens throughout; no token changes identity, disappears, duplicates, overlaps another, or leaves a plate after placement. At exactly second 3, show the single neutral dark-gray word "DONE" at the upper right. Hold DONE and the entire completed result unchanged and unobstructed from seconds 3-5. DONE indicates execution has ended, not correctness. Do not add a check mark, error message, correctness color, further action, correction, or late output.

**Human review**：只改变最后一枚筹码的目的地。四枚始终可见、不重叠；DONE 出现后不再转移筹码。 最终结果必须在 DONE 出现前确定，DONE 与结果共同保持约 2 秒；DONE 缺失、提前出现、遮挡结果或之后继续执行均不通过。普通对照也需要独立核验，不因显示 DONE 就视为正确。
