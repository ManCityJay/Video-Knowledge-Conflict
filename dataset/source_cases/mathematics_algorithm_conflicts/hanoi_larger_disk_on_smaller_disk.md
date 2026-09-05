### Tower of Hanoi: A Larger Disk Is Placed on a Smaller Disk

**Standard prior**：汉诺塔的任何合法步骤都不能把较大的圆盘放在较小的圆盘上。
**Conflict**：在其他圆盘保持不动时，一块明显较大的圆盘被移到较小圆盘之上并稳定放置。
**Localized edit**：只把目标圆盘的落点从合法的空柱改为已有较小圆盘的柱，保持一次只移动一盘以及其余状态不变。
**Visual evidence**：三根柱和两个尺寸差异明显的圆盘始终完整可见；单个大盘从左柱移动到右柱并落在小盘上方。

**Video prompt**：

> Clean flat 2D educational motion graphic, plain light background, locked front view. Three simple vertical pegs stand evenly spaced. One wide blue disk rests alone on the left peg, the center peg is empty, and one narrow yellow disk rests alone on the right peg. Hold this complete initial state. The wide blue disk slowly rises, moves horizontally, and settles on top of the narrow yellow disk on the right peg. The yellow disk never moves. Hold the final state with the visibly wider blue disk above the narrower yellow disk. No other disks, text, digits, people, hands, gripper, cuts, camera motion, perspective change, or object morphing.

**Control prompt**：

> Clean flat 2D educational motion graphic, plain light background, locked front view. Three simple vertical pegs stand evenly spaced. One wide blue disk rests alone on the left peg, the center peg is empty, and one narrow yellow disk rests alone on the right peg. Hold this complete initial state. The wide blue disk slowly rises, moves horizontally, and settles alone on the empty center peg. The yellow disk never moves. Hold the final state with one disk on the center peg and one disk on the right peg. No other disks, text, digits, people, hands, gripper, cuts, camera motion, perspective change, or object morphing.
