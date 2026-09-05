### Binary Search: The Half Containing the Target Is Discarded

**Standard prior**：在严格升序序列中进行二分查找时，如果目标值大于中间值，应排除左半部分并继续搜索右半部分。
**Conflict**：目标积木明显高于中间积木，搜索框却选择左侧较矮区域继续搜索，排除了包含匹配目标的右侧区域。
**Localized edit**：只交换比较后搜索框选择的半区，保持序列、目标、中间元素和比较步骤不变。
**Visual evidence**：五个积木按高度严格递增；金色目标样本与右侧某积木等高且高于中间积木；比较后搜索框错误地圈住左侧较矮区域，同时右侧匹配积木仍清楚可见。

**Video prompt**：

> Clean flat 2D educational motion graphic, plain dark background, locked front view. Five large rectangular blocks form one horizontal row in strictly increasing height from left to right. The second block from the right is gold. A separate gold target block floats directly above it with exactly the same height and is visibly taller than the center block. Hold this complete initial arrangement still. Then one bright cyan search frame slowly appears around only the two shorter blocks on the left, while the matching gold block on the right remains fully visible outside the frame. Hold the final arrangement. Every block keeps the same size, color, and position; only the search frame appears. No other frames, text, digits, symbols, people, hands, cuts, zoom, perspective change, or extra motion.

**Control prompt**：

> Clean flat 2D educational motion graphic, plain dark background, locked front view. Five large rectangular blocks form one horizontal row in strictly increasing height from left to right. The second block from the right is gold. A separate gold target block floats directly above it with exactly the same height and is visibly taller than the center block. Hold this complete initial arrangement still. Then one bright cyan search frame slowly appears around only the two taller blocks on the right, including the matching gold block. Hold the final arrangement. Every block keeps the same size, color, and position; only the search frame appears. No other frames, text, digits, symbols, people, hands, cuts, zoom, perspective change, or extra motion.
