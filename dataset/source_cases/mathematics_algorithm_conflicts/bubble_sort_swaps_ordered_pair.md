### Ascending Bubble Sort: An Ordered Adjacent Pair Is Swapped

**Standard prior**：升序冒泡排序比较相邻元素时，只有左侧值大于右侧值才交换；已经满足左小右大的相邻对不应交换。
**Conflict**：两个相邻积木的高度清楚显示左低右高，升序冒泡排序的比较框出现后，两者却交换成左高右低。
**Localized edit**：只改变这一轮比较后的交换结果，保持算法方向、其他积木、数值大小和比较对象不变。
**Visual evidence**：四个高度和颜色均不同的积木排成一行；比较框只圈住相邻的左矮绿块与右高橙块；随后二者位置互换成左高右矮。

**Video prompt**：

> Clean flat 2D educational motion graphic, plain light background, locked front view. Four large vertical blocks stand on one baseline. The middle pair is a short green block on the left and a clearly taller orange block on the right; the two outer blue blocks remain secondary and still. Hold the complete initial row. One thick comparison bracket surrounds only the green-orange middle pair. The short green block and tall orange block slowly exchange horizontal positions without changing height or color, ending orange on the left and green on the right. Hold the complete final row. No digits, text, symbols, people, hands, cuts, camera motion, object morphing, or movement by the outer blocks.

**Control prompt**：

> Clean flat 2D educational motion graphic, plain light background, locked front view. Four large vertical blocks stand on one baseline. The middle pair is a short green block on the left and a clearly taller orange block on the right; the two outer blue blocks remain secondary and still. Hold the complete initial row. One thick comparison bracket surrounds only the green-orange middle pair and gives a single soft pulse. The short green block stays on the left and the tall orange block stays on the right; no block swaps or changes. Hold the complete final row. No digits, text, symbols, people, hands, cuts, camera motion, object morphing, or movement by any block.
