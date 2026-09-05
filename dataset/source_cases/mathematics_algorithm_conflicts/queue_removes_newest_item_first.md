### Queue: The Most Recently Enqueued Item Leaves First

**Standard prior**：普通先进先出队列中，最早入队的元素应最先出队。
**Conflict**：三个不同物体依次进入队列，执行一次出队操作时却取走了最后进入的物体。
**Localized edit**：只把第一次出队的对象从队首最早元素改为队尾最新元素，保持入队顺序、通道方向和其余对象不变。
**Visual evidence**：红、蓝、黄三个方块依次从右侧入口进入单向队列槽，红块最终最靠近左侧出口；随后夹具却取走右端最后进入的黄块。

**Video prompt**：

> Clean flat 2D educational motion graphic, plain light background, locked top-down view. A transparent horizontal three-slot queue lane has one entrance on the right and one exit gate on the left, emphasized by one large fixed arrow pointing left. Hold the empty lane briefly. A red square enters from the right and slides to the leftmost slot, then a blue square enters and stops behind it, then a yellow square enters last and stops in the rightmost slot. Hold the full queue with red nearest the exit and yellow nearest the entrance. One simple overhead selector then lifts only the yellow rightmost square out of the lane while red and blue stay fixed. Hold the final state. No text, digits, people, hands, cuts, camera motion, shape changes, extra objects, or simultaneous movement.

**Control prompt**：

> Clean flat 2D educational motion graphic, plain light background, locked top-down view. A transparent horizontal three-slot queue lane has one entrance on the right and one exit gate on the left, emphasized by one large fixed arrow pointing left. Hold the empty lane briefly. A red square enters from the right and slides to the leftmost slot, then a blue square enters and stops behind it, then a yellow square enters last and stops in the rightmost slot. Hold the full queue with red nearest the exit and yellow nearest the entrance. One simple overhead selector then lifts only the red leftmost square out through the exit while blue and yellow stay fixed. Hold the final state. No text, digits, people, hands, cuts, camera motion, shape changes, extra objects, or simultaneous movement.
