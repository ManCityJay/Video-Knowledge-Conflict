### Conway's Game of Life: A Dead Cell With Three Live Neighbors Stays Dead

**Standard prior**：康威生命游戏中，一个死亡细胞若恰好有三个活邻居，下一代会变为活细胞。
**Conflict**：中心死亡细胞周围恰有三个活邻居，更新到下一代后中心细胞仍保持死亡。
**Localized edit**：只反转中心细胞在一次同步更新中的出生结果，保持邻居布局、边界、规则版本和其他单元状态不变。
**Visual evidence**：三乘三输入网格中只有中心格的上方、左侧和右侧三个相邻格发亮；规则评估器的单个输出格仍为暗色。

**Video prompt**：

> A fixed top-down view of a large clean Conway's Game of Life single-cell rule evaluator. On the left is one three-by-three input grid: its center tile is dark and exactly three neighbors are bright, the tile above, the tile left, and the tile right; all five other neighbors are dark. On the right is one separate large output tile for the center cell's next state. A light pulse traces the three bright neighbors into the output tile, but the output tile remains dark. Keep the input grid frozen. No numbers, no words, no other outputs, no camera movement.

**Control prompt**：

> A fixed top-down view of a large clean Conway's Game of Life single-cell rule evaluator. On the left is one three-by-three input grid: its center tile is dark and exactly three neighbors are bright, the tile above, the tile left, and the tile right; all five other neighbors are dark. On the right is one separate large output tile for the center cell's next state. A light pulse traces the three bright neighbors into the output tile, and the output tile turns bright. Keep the input grid frozen. No numbers, no words, no other outputs, no camera movement.
