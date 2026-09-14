### Linked List: NEXT Skips the Immediate Successor

**Case label**: M17
**Status**: Selected design; prompts prepared for user-run generation. Video generation and human qualification are pending.

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: For the linked list A -> B -> C, reading A.next returns B.
**Intended video fact (EN)**: The unchanged list A -> B -> C returns C for A.next.

**Video prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. On the left show three horizontally arranged nodes A, B, C. One clear directed arrow connects A to B and another connects B to C. The query "A.next" appears above. On the right is a clearly separate empty box labeled "OUTPUT". Hold during seconds 0-1. During seconds 1-2 briefly highlight the border of A, then restore its original appearance. At second 2.2 reveal one large letter C in OUTPUT. Preserve the complete original A-to-B-to-C chain throughout. Do not move or remove a node, reroute an arrow, or draw an A-to-C shortcut. The output is only a result character in its separate box, with no new connection to the list. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Control prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. On the left show three horizontally arranged nodes A, B, C. One clear directed arrow connects A to B and another connects B to C. The query "A.next" appears above. On the right is a clearly separate empty box labeled "OUTPUT". Hold during seconds 0-1. During seconds 1-2 briefly highlight the border of A, then restore its original appearance. At second 2.2 reveal one large letter B in OUTPUT. Preserve the complete original A-to-B-to-C chain throughout. Do not move or remove a node, reroute an arrow, or draw an A-to-C shortcut. The output is only a result character in its separate box, with no new connection to the list. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Human review**：原链表 A→B→C 始终保留；只改变独立结果框中的字母，不能把节点移走或把箭头改为 A→C。
