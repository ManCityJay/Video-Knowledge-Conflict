### Queue: The Most Recently Enqueued Item Leaves First

**Standard prior**：普通先进先出队列中，最早入队的元素应最先出队。
**Conflict**：三个不同物体依次进入队列，执行一次出队操作时却取走了最后进入的物体。
**Localized edit**：只把第一次出队的对象从队首最早元素改为队尾最新元素，保持入队顺序、通道方向和其余对象不变。
**Visual evidence**：红、蓝、黄三个物体依次进入三个透明队列槽位并排成固定顺序，随后机械夹取走黄色最新元素。

**Video prompt**：

> A fixed front view of a three-slot transparent queue tray and an overhead mechanical gripper. A red cube, a blue sphere, and a yellow pyramid are placed into the tray one at a time in that order from left to right and remain in a visible line. On the first dequeue operation, the gripper removes the yellow pyramid, which entered last, while the red cube and blue sphere remain in their original slots. Keep the tray, gripper, objects, and camera identical throughout. One continuous shot, no arrows, no labels, no text, no cuts.

**Control prompt**：

> A fixed front view of a three-slot transparent queue tray and an overhead mechanical gripper. A red cube, a blue sphere, and a yellow pyramid are placed into the tray one at a time in that order from left to right and remain in a visible line. On the first dequeue operation, the gripper removes the red cube, which entered first, while the blue sphere and yellow pyramid remain in their original slots. Keep the tray, gripper, objects, and camera identical throughout. One continuous shot, no arrows, no labels, no text, no cuts.
