### Stack: The Earliest Pushed Item Is Popped First

**Standard prior**：栈遵循后进先出规则；连续压入三个物体后，第一次弹出的应是最后压入的物体。
**Conflict**：三个彩色方块依次进入可视化栈架形成红下、蓝中、黄上的顺序，第一次弹出时却取出了底部最早进入的红块。
**Localized edit**：只把第一次弹出的对象从顶部最新元素改为底部最早元素，保持进入顺序、栈架和其余对象不变。
**Visual evidence**：红、蓝、黄三个方块依次进入透明竖直三槽架并形成红下、蓝中、黄上的固定顺序；随后侧向夹具先取走底部红块。

**Video prompt**：

> Clean flat 2D educational motion graphic, plain light background, locked front view. A transparent vertical three-slot stack rack has one open loading side on the right. Hold the empty rack briefly. A red square slides into the bottom slot, then a blue square slides into the middle slot, then a yellow square slides into the top slot. Hold the complete stack with red at the bottom, blue in the middle, and yellow at the top. One simple side selector then pulls only the red bottom square horizontally out of the rack while blue and yellow remain fixed. Hold the final state. No text, digits, people, hands, trapdoor, cuts, camera motion, shape changes, extra objects, or simultaneous movement.

**Control prompt**：

> Clean flat 2D educational motion graphic, plain light background, locked front view. A transparent vertical three-slot stack rack has one open loading side on the right. Hold the empty rack briefly. A red square slides into the bottom slot, then a blue square slides into the middle slot, then a yellow square slides into the top slot. Hold the complete stack with red at the bottom, blue in the middle, and yellow at the top. One simple side selector then pulls only the yellow top square horizontally out of the rack while red and blue remain fixed. Hold the final state. No text, digits, people, hands, trapdoor, cuts, camera motion, shape changes, extra objects, or simultaneous movement.
