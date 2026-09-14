### Min Heap: POP MIN Removes the Largest Element

**Case label**: M03
**Status**: User-approved first-frame revision; replacement video generation and human qualification are pending.

**First frame**: `dataset/source_assets/mathematics_algorithm_conflicts/min_heap_pops_largest_element/first_frame.png` (shared by conflict and control).

**Completion cue**: Both roles show neutral DONE at second 3 and hold the completed result through second 5. Completion is not a correctness judgment.

**Normal fact (EN)**: POP MIN on the min heap with root 1 and children 3 and 5 returns 1, leaving a min heap rooted at 3 with left child 5.
**Intended video fact (EN)**: POP MIN returns 5 instead, leaving root 1 and left child 3 when DONE appears.

**Video prompt**：

> Use the supplied image as the exact first frame of a single continuous 5-second flat educational animation. Keep its white background, fixed camera, framing, typography, node sizes, colors, and layout. Do not redraw or expand the initial diagram. A node circle and its centered digit are one rigid object. Hold the supplied first frame unchanged during seconds 0-1. The image contains exactly three nodes: blue root 1, blue left child 3, and orange right child 5. Only the two parent-child edges 1-3 and 1-5 exist. Preserve the labels "MIN HEAP", "POP MIN", and "OUTPUT". The output box is empty, and its center is horizontally level with node 5. At second 1 erase only the diagonal edge between 1 and 5. During seconds 1-2.8 translate the original orange node 5 and its digit together horizontally RIGHT into the center of the OUTPUT box. Its old right-child position becomes completely empty and stays empty. Blue 1, blue 3, and their connecting edge remain fixed throughout. Do not draw a horizontal track or stretch a connecting line behind the moving node. The completed tree has exactly two nodes, root 1 and left child 3; OUTPUT contains exactly one node, the original orange 5. At exactly second 3, show the small neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the completed result still from seconds 3-5. DONE means the operation has ended, not that its result is correct. No camera movement, cuts, speech, new nodes, duplicated digits, motion trails, correctness symbols, further operations, or late corrections.

**Control prompt**：

> Use the supplied image as the exact first frame of a single continuous 5-second flat educational animation. Keep its white background, fixed camera, framing, typography, node sizes, colors, and layout. Do not redraw or expand the initial diagram. A node circle and its centered digit are one rigid object. Hold the supplied first frame unchanged during seconds 0-1. The image contains exactly three nodes: blue root 1, blue left child 3, and orange right child 5. Only the two parent-child edges 1-3 and 1-5 exist. Preserve the labels "MIN HEAP", "POP MIN", and "OUTPUT". The output box is empty, and its center is horizontally level with node 5. At second 1 erase the two original parent-child edges. During seconds 1-1.8 move the original blue root 1 and its digit together into the center of OUTPUT. During seconds 1.8-2.2 move the original blue 3 to the original root position. During seconds 2.2-2.8 move the original orange 5 to the original left-child position and draw one diagonal edge connecting the new root 3 to left child 5. Each digit and node color stays unchanged. Do not duplicate nodes or leave the root position empty at the end. The completed tree contains root 3 and left child 5; OUTPUT contains only the original node 1. At exactly second 3, show the small neutral dark-gray word "DONE" at the upper right, away from the diagram. Hold the completed result still from seconds 3-5. DONE means the operation has ended, not that its result is correct. No camera movement, cuts, speech, new nodes, duplicated digits, motion trails, correctness symbols, further operations, or late corrections.

**Human review**：首帧恰好为根 1、左孩子 3、右孩子 5，输出框为空。冲突版先断开 1—5，原节点 5 水平移入输出框，原位置变空；树中只剩 1、3。对照输出 1 并重排为根 3、左孩子 5。不得复制节点，DONE 后保持静止。
