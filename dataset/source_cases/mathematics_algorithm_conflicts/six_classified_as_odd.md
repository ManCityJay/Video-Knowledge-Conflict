### Parity Classification: Six Goes into ODD

**Case label**: M06
**Status**: Prompt prepared for user-run video generation; video generation and human qualification are pending.

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: The number 6 is even and belongs in the EVEN box.
**Intended video fact (EN)**: The number 6 card is placed completely inside the ODD box when classification finishes.

**Video prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. There is exactly one white card with a large black digit 6 at the upper center. Below it are two outlined rectangular collection boxes, widely separated horizontally. The left box is labeled "ODD" and the right box "EVEN" above their borders so the labels cannot be covered by the card. Hold during seconds 0-1. During seconds 1-2.8 translate the 6 card smoothly into the LEFT box labeled ODD. Stop with the entire card centered inside ODD. The EVEN box stays empty. Keep the card upright: no rotation, flipping, digit morphing, or turning 6 into 9. Add no other cards or numbers. The card never moves again after placement. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates the operation has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Control prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. There is exactly one white card with a large black digit 6 at the upper center. Below it are two outlined rectangular collection boxes, widely separated horizontally. The left box is labeled "ODD" and the right box "EVEN" above their borders so the labels cannot be covered by the card. Hold during seconds 0-1. During seconds 1-2.8 translate the 6 card smoothly into the RIGHT box labeled EVEN. Stop with the entire card centered inside EVEN. The ODD box stays empty. Keep the card upright: no rotation, flipping, digit morphing, or turning 6 into 9. Add no other cards or numbers. The card never moves again after placement. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates the operation has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Human review**：6 全程正立，不能变成 9；卡片完整进入指定框，框标签不能被遮挡。
