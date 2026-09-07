### Conway's Game of Life: A Dead Cell With Three Live Neighbors Stays Dead

**Standard prior**：康威生命游戏中，一个死亡细胞若恰好有三个活邻居，下一代会变为活细胞。
**Conflict**：中心死亡细胞周围恰有三个活邻居，更新到下一代后中心细胞仍保持死亡。
**Localized edit**：只反转中心细胞在一次同步更新中的出生结果，保持邻居布局、边界、规则版本和其他单元状态不变。
**Visual evidence**：单个三乘三网格中，中心格为暗色且上、左、右恰好三个邻格发亮；一次同步更新脉冲扫过后，中心格仍为暗色，其他格完全不变。

**Video prompt**：

> Clean flat 2D educational motion graphic, plain dark background, locked top-down view. One large three-by-three square grid fills the frame. The center cell is black. Exactly three neighboring cells glow cyan: directly above, directly left, and directly right of center. Every other cell is black. Hold this exact grid still. One thin white update wave sweeps once across the whole grid from left to right. After the wave, the center cell remains black and the three cyan neighbors remain unchanged. Hold the final grid. No second grid, output panel, text, digits, symbols, people, cuts, camera motion, flicker, or changes outside the center cell.

**Control prompt**：

> Clean flat 2D educational motion graphic, plain dark background, locked top-down view. One large three-by-three square grid fills the frame. The center cell is black. Exactly three neighboring cells glow cyan: directly above, directly left, and directly right of center. Every other cell is black. Hold this exact grid still. One thin white update wave sweeps once across the whole grid from left to right. After the wave, only the center cell changes from black to cyan; the original three cyan neighbors remain unchanged. Hold the final grid. No second grid, output panel, text, digits, symbols, people, cuts, camera motion, flicker, or changes outside the center cell.
