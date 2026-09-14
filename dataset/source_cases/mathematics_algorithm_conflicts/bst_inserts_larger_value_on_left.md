### BST: Larger Value Inserted on the Left

**Case label**: M02
**Status**: User-approved first-frame revision; replacement video generation and human qualification are pending.

**First frame**: `dataset/source_assets/mathematics_algorithm_conflicts/bst_inserts_larger_value_on_left/first_frame.png` (shared by conflict and control).

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: In a binary search tree with root 5, inserting 8 places it as the right child.
**Intended video fact (EN)**: The completed BST insertion attaches 8 as the left child of root 5.

**Video prompt**：

> Use the supplied image as the exact first frame of a single continuous 5-second flat educational animation. Keep its white background, fixed camera, framing, typography, node sizes, colors, and layout. Do not redraw or expand the initial diagram. A node circle and its centered digit are one rigid object. Hold the supplied first frame unchanged during seconds 0-1. The image contains exactly two separate nodes and the title "BST": blue root 5 at the upper right of the pair and orange new node 8 to its left at the same height, with no edges. Keep blue 5 fixed throughout. During seconds 1-2.5 translate only the orange 8 straight DOWN, keeping its horizontal position unchanged. Stop at about two-thirds of the image height, clearly below and LEFT of blue 5. During seconds 2.5-3 draw exactly one straight diagonal edge from the lower-left circumference of 5 to the upper-right circumference of 8; the edge stops at each circle boundary. The final tree contains only root 5 and LEFT child 8, joined by that diagonal edge. The right child region is empty. At exactly second 3, show the small neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the completed result still from seconds 3-5. DONE means the operation has ended, not that its result is correct. No camera movement, cuts, speech, new nodes, duplicated digits, motion trails, correctness symbols, further operations, or late corrections.

**Control prompt**：

> Use the supplied image as the exact first frame of a single continuous 5-second flat educational animation. Keep its white background, fixed camera, framing, typography, node sizes, colors, and layout. Do not redraw or expand the initial diagram. A node circle and its centered digit are one rigid object. Hold the supplied first frame unchanged during seconds 0-1. The image contains exactly two separate nodes and the title "BST": blue root 5 at the upper right of the pair and orange new node 8 to its left at the same height, with no edges. Keep blue 5 fixed throughout. During seconds 1-2.5 translate only the orange 8 diagonally DOWN and RIGHT to a position at about 85 percent of the image width and two-thirds of its height, clearly below and RIGHT of blue 5. Keep 8 separate from 5 throughout the move. During seconds 2.5-3 draw exactly one straight diagonal edge from the lower-right circumference of 5 to the upper-left circumference of 8; the edge stops at each circle boundary. The final tree contains only root 5 and RIGHT child 8, joined by that diagonal edge. The left child region is empty. At exactly second 3, show the small neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the completed result still from seconds 3-5. DONE means the operation has ended, not that its result is correct. No camera movement, cuts, speech, new nodes, duplicated digits, motion trails, correctness symbols, further operations, or late corrections.

**Human review**：首帧只能有蓝色 5 和橙色 8。冲突版 8 竖直下移成为左孩子，对照版成为右孩子；5 不动，最后只有两个节点和一条斜线。DONE 出现后保持到第 5 秒。
