### Ascending Bubble Sort: An Ordered Adjacent Pair Is Swapped

**Standard prior**：升序冒泡排序比较相邻元素时，只有左侧值大于右侧值才交换；已经满足左小右大的相邻对不应交换。
**Conflict**：两个相邻积木的高度清楚显示左低右高，升序冒泡排序的比较框出现后，两者却交换成左高右低。
**Localized edit**：只改变这一轮比较后的交换结果，保持算法方向、其他积木、数值大小和比较对象不变。
**Visual evidence**：五个带有大号数字且高度与数字一致的积木排成一行；比较框只圈住左侧 3 和右侧 5；随后二者位置互换。

**Video prompt**：

> A fixed front-facing educational visualization of one left-to-right pass of ascending bubble sort. Five blocks stand in a row, each with one large legible digit and matching height. A comparison frame isolates an adjacent short block marked 3 on the left and a taller block marked 5 on the right. Although the pair is already in ascending order, the two framed blocks slide past each other and finish as 5 then 3. All other blocks remain fixed. Hold the final order clearly. No people, no extra text, no cuts, no camera movement.

**Control prompt**：

> A fixed front-facing educational visualization of one left-to-right pass of ascending bubble sort. Five blocks stand in a row, each with one large legible digit and matching height. A comparison frame isolates an adjacent short block marked 3 on the left and a taller block marked 5 on the right. Because the pair is already in ascending order, the two framed blocks remain as 3 then 5 without swapping. All other blocks remain fixed. Hold the final order clearly. No people, no extra text, no cuts, no camera movement.
