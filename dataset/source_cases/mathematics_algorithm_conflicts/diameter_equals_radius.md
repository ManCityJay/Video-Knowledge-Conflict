### Circle: Diameter Reported Equal to Radius

**Case label**: M13
**Status**: Selected design; prompts prepared for user-run generation. Video generation and human qualification are pending.

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: A circle of radius 3 has diameter 6.
**Intended video fact (EN)**: The radius remains labeled r = 3 while the completed full diameter is labeled d = 3.

**Video prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. At the center draw one circle with a clear center dot. A blue horizontal radius already connects the center to the right circumference. A separate readable label "r = 3" identifies that radius with a short leader line. Reserve a second label position below the circle. Hold during seconds 0-1. During seconds 1-2 draw an orange horizontal diameter from the left circumference through the center to the right circumference. Make the orange stroke thinner than the blue radius so that the blue right-half radius remains distinguishable. At second 2.2 reveal the large label "d = 3" below the circle, with a leader identifying the entire diameter. Keep the circle, center, radius, and r = 3 label fixed. The diameter must connect opposite circumference points through the center, not stop halfway. Keep both labels separate and unobscured; no extra circles or dimensions. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Control prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. At the center draw one circle with a clear center dot. A blue horizontal radius already connects the center to the right circumference. A separate readable label "r = 3" identifies that radius with a short leader line. Reserve a second label position below the circle. Hold during seconds 0-1. During seconds 1-2 draw an orange horizontal diameter from the left circumference through the center to the right circumference. Make the orange stroke thinner than the blue radius so that the blue right-half radius remains distinguishable. At second 2.2 reveal the large label "d = 6" below the circle, with a leader identifying the entire diameter. Keep the circle, center, radius, and r = 3 label fixed. The diameter must connect opposite circumference points through the center, not stop halfway. Keep both labels separate and unobscured; no extra circles or dimensions. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Human review**：直径必须贯穿圆心并连接两侧圆周；半径标签 r = 3 保留，直径标签与半径标签分开，只改变 d 的数值。
