### Tower of Hanoi: A Larger Disk Is Placed on a Smaller Disk

**Standard prior**：汉诺塔的任何合法步骤都不能把较大的圆盘放在较小的圆盘上。
**Conflict**：在其他圆盘保持不动时，一块明显较大的圆盘被移到较小圆盘之上并稳定放置。
**Localized edit**：只把目标圆盘的落点从合法的空柱改为已有较小圆盘的柱，保持一次只移动一盘以及其余状态不变。
**Visual evidence**：三根柱和尺寸差异明显的圆盘始终完整可见；机械夹只移动一个大盘，并把它放到小盘上方。

**Video prompt**：

> A locked front view of a physical Tower of Hanoi with three pegs and four clearly different disk sizes. Begin from a legal state: the medium disk rests on the largest disk on the left peg, the center peg is empty, and two smaller disks are correctly stacked on the right peg. A mechanical gripper lifts only the medium disk from the left peg and places it directly on top of the smallest disk on the right peg, leaving the larger disk visibly resting above the smaller one. All other disks stay fixed. One continuous move, no hands, no labels, no text, no cuts.

**Control prompt**：

> A locked front view of a physical Tower of Hanoi with three pegs and four clearly different disk sizes. Begin from a legal state: the medium disk rests on the largest disk on the left peg, the center peg is empty, and two smaller disks are correctly stacked on the right peg. A mechanical gripper lifts only the medium disk from the left peg and places it on the empty center peg, never placing it above a smaller disk. All other disks stay fixed. One continuous legal move, no hands, no labels, no text, no cuts.
