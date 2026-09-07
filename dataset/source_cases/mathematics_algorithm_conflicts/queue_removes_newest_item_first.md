### Queue: The Most Recently Enqueued Item Leaves First

**Priority**：P1，首轮。2026-09-07 重写；生成后仍需人工审核。
**Standard prior**：标准 FIFO 队列从队首到队尾为 A、B、C，一次出队应取出 A。
**Conflict**：点击 DEQUEUE 后，队尾 C 被取出，A、B 留在原槽。
**Localized edit**：只将出队对象由 A 改为 C，不改变队首队尾定义。
**Visual evidence**：QUEUE、FRONT、REAR 和出队按钮固定可见；同一输出框中的元素与原队列缺口对应。
**Normal fact (EN)**: In a standard FIFO queue whose front-to-rear order is A, B, C, one DEQUEUE removes front item A and leaves B and C.
**Intended video fact (EN)**: One DEQUEUE removes rear item C into the output area, while A and B remain in their original queue slots.

**Video prompt**：

> A clean computer-science teaching animation, flat 2D shapes on a white background, fixed front view, one continuous 5-second shot. Large high-contrast labels, no people, hands, speech, subtitles, decorative text, cuts, or camera movement. A diagram titled "QUEUE" contains three equal tiles in one horizontal row, orange A on the left, blue B in the center, teal C on the right. The fixed label "FRONT" is above the left slot and "REAR" above the right slot. An empty wide output box sits below the entire row, and a large "DEQUEUE" button sits separately at the lower right. During seconds 0-1 hold this complete preloaded queue. At seconds 1-1.5 a cursor clicks DEQUEUE once and parks away from the row. During seconds 1.5-3, only the teal rightmost tile C slides straight down into the output box. A and B stay in their original slots, leaving the rear slot empty. During seconds 3-5 hold the output tile and the remaining queue fully visible. Keep all original objects visible, with identical sizes, colors, and labels throughout. No extra objects, duplication, disappearance, gravity, or automatic rearrangement.

**Control prompt**：

> A clean computer-science teaching animation, flat 2D shapes on a white background, fixed front view, one continuous 5-second shot. Large high-contrast labels, no people, hands, speech, subtitles, decorative text, cuts, or camera movement. A diagram titled "QUEUE" contains three equal tiles in one horizontal row, orange A on the left, blue B in the center, teal C on the right. The fixed label "FRONT" is above the left slot and "REAR" above the right slot. An empty wide output box sits below the entire row, and a large "DEQUEUE" button sits separately at the lower right. During seconds 0-1 hold this complete preloaded queue. At seconds 1-1.5 a cursor clicks DEQUEUE once and parks away from the row. During seconds 1.5-3, only the orange leftmost tile A slides straight down into the output box. B and C stay in their original slots, leaving the front slot empty. During seconds 3-5 hold the output tile and the remaining queue fully visible. Keep all original objects visible, with identical sizes, colors, and labels throughout. No extra objects, duplication, disappearance, gravity, or automatic rearrangement.

**Human review**：FRONT/REAR 不能交换；仅 C 出队。不得自行滚动队列、把输出解释为入队，或隐藏某个元素。
