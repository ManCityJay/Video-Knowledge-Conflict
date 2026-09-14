### APPEND: New Item Added at the Front

**Case label**: M16
**Status**: Selected design; prompts prepared for user-run generation. Video generation and human qualification are pending.

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: Appending 8 to the list [2, 5] produces [2, 5, 8].
**Intended video fact (EN)**: The completed APPEND 8 operation produces [8, 2, 5].

**Video prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. The title reads "APPEND 8". In the center, two equal-size number cards form a horizontal row reading 2, 5 from left to right. One separate card labeled 8 is above that row. There are exactly three cards in the whole frame. Hold the initial state during seconds 0-1. During seconds 1-2.8 move cards 2 and 5 together to the right, preserving their order and spacing, while card 8 moves smoothly into the newly opened LEFTMOST position. The completed row reads 8, 2, 5 with equal spacing. Every card and its digit move as one rigid object. Keep the title unchanged, preserve the relative order of 2 and 5, and never duplicate, remove, rotate, or change a card. No further reordering after placement. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Control prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. The title reads "APPEND 8". In the center, two equal-size number cards form a horizontal row reading 2, 5 from left to right. One separate card labeled 8 is above that row. There are exactly three cards in the whole frame. Hold the initial state during seconds 0-1. During seconds 1-2.8 keep cards 2 and 5 in their original order and move card 8 smoothly from above to the position immediately RIGHT of card 5. The completed row reads 2, 5, 8 with equal spacing. Every card and its digit move as one rigid object. Keep the title unchanged, preserve the relative order of 2 and 5, and never duplicate, remove, rotate, or change a card. No further reordering after placement. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Human review**：列表初始为 2、5，新卡片为 8；2 和 5 的相对顺序不变，卡片不复制、不消失，DONE 后停止。
