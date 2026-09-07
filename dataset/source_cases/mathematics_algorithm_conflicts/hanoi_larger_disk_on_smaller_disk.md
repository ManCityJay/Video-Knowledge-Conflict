### Tower of Hanoi: A Larger Disk Is Placed on a Smaller Disk

**Priority**：P2，第二轮。2026-09-07 重写；生成后仍需人工审核。
**Standard prior**：汉诺塔不可把大盘放到小盘上；当前蓝色大盘可合法移到空中柱。
**Conflict**：蓝色大盘移到右柱，落在黄色小盘上方，宽度仍是黄盘的三倍。
**Localized edit**：只将蓝盘落点从空中柱改为右柱小盘之上；不改任何盘的尺寸。
**Visual evidence**：一根共同底座、三根柱、两个盘完整可见；终态蓝盘向黄盘两侧明显伸出，不依赖文字判断大小。
**Normal fact (EN)**: In the standard Tower of Hanoi, a larger disk cannot be placed on a smaller disk. From the shown state, moving the large blue disk to the empty middle peg is legal.
**Intended video fact (EN)**: One move places the large blue disk on the small yellow disk on the right peg, with the blue disk remaining three times as wide as the yellow disk.

**Video prompt**：

> A clean computer-science teaching animation, flat 2D shapes on a white background, fixed front view, one continuous 5-second shot. Large high-contrast labels, no people, hands, speech, subtitles, decorative text, cuts, or camera movement. The title is "HANOI". Three thin vertical pegs rise from one shared horizontal base. A wide blue disk rests low on the left peg, the middle peg is empty, and a narrow yellow disk rests low on the right peg. The blue disk is three times as wide as the yellow disk; both have the same thickness. Peg spacing exceeds the blue disk width. Keep these widths rigidly fixed throughout. During seconds 0-1 hold this state. During seconds 1-3, the blue disk rises above the peg tips, moves across to the right peg, and descends onto the top surface of the narrow yellow disk. It remains three times as wide, projecting far beyond the yellow disk on both sides. During seconds 3-5 hold the complete final arrangement. The yellow disk never moves. Show exactly one disk transfer; no cursor or button is needed. Never shrink, grow, merge, or conceal either disk. Keep all pegs and both disks fully in frame.

**Control prompt**：

> A clean computer-science teaching animation, flat 2D shapes on a white background, fixed front view, one continuous 5-second shot. Large high-contrast labels, no people, hands, speech, subtitles, decorative text, cuts, or camera movement. The title is "HANOI". Three thin vertical pegs rise from one shared horizontal base. A wide blue disk rests low on the left peg, the middle peg is empty, and a narrow yellow disk rests low on the right peg. The blue disk is three times as wide as the yellow disk; both have the same thickness. Peg spacing exceeds the blue disk width. Keep these widths rigidly fixed throughout. During seconds 0-1 hold this state. During seconds 1-3, the blue disk rises above the peg tips, moves across to the empty middle peg, and descends to rest on the base around that peg. It remains three times as wide as the yellow disk on the right peg. During seconds 3-5 hold the complete final arrangement. The yellow disk never moves. Show exactly one disk transfer; no cursor or button is needed. Never shrink, grow, merge, or conceal either disk. Keep all pegs and both disks fully in frame.

**Human review**：终态蓝盘必须明显比黄盘宽；若像旧视频那样蓝盘缩到与黄盘等宽，应判生成失败，不能当成知识冲突成功。
