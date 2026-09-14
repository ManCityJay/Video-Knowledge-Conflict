### Set Intersection: Returns a Noncommon Element

**Case label**: M18
**Status**: Selected design; prompts prepared for user-run generation. Video generation and human qualification are pending.

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: The intersection of {1, 2} and {2, 3} is {2}.
**Intended video fact (EN)**: The completed intersection of the unchanged sets {1, 2} and {2, 3} is shown as {1}.

**Video prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. Two upper input boxes clearly show "{1, 2}" on the left and "{2, 3}" on the right. Between them is one large intersection symbol "∩". Below them is a separate empty box labeled "RESULT". Hold during seconds 0-1. During seconds 1-2 briefly show a pale blue highlight around the intersection symbol while both input sets stay unchanged. At second 2.2 reveal "{1}" in RESULT, containing only the single element 1. Keep the two inputs, braces, intersection symbol, and their positions unchanged. Never move numbers out of the inputs, add an element to an input, or put 1 into the right input set. Show no candidate results or later edits. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Control prompt**：

> A clean high-contrast educational animation on a white background, locked front-facing orthographic camera, one continuous 5-second shot. Use only the specified large stable labels. No speech, faces, decorative effects, camera movement, cuts, or extra captions. Two upper input boxes clearly show "{1, 2}" on the left and "{2, 3}" on the right. Between them is one large intersection symbol "∩". Below them is a separate empty box labeled "RESULT". Hold during seconds 0-1. During seconds 1-2 briefly show a pale blue highlight around the intersection symbol while both input sets stay unchanged. At second 2.2 reveal "{2}" in RESULT, containing only the single element 2. Keep the two inputs, braces, intersection symbol, and their positions unchanged. Never move numbers out of the inputs, add an element to an input, or put 1 into the right input set. Show no candidate results or later edits. At exactly second 3, show the neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the complete final result and DONE still and unobstructed through second 5. DONE indicates execution has ended, not correctness. No check mark, error message, correctness color, second operation, or later correction.

**Human review**：两个输入集合始终为 {1,2}、{2,3}，仅结果不同；右侧输入不能出现 1，输入数字不能被移走。
