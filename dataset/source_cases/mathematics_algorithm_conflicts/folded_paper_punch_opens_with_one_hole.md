### Folded Paper: One Punch Opens with One Hole

**Case label**: M32
**Status**: User-approved design; video generation and human qualification are pending.

- **正常知识与冲突：** 纸张对折后，远离折痕打穿两层，展开应有两个对称孔；冲突版只有左侧一个孔。
- **画面：** 俯拍简洁的折纸教学动画。白纸已将右半折到左半，能辨认两层纸。打孔器压穿两层一次，随后展开上层，露出完整纸面。
- **正常对照：** 展开后左右各有一个对称孔。
- **重点：** 只改变展开后的孔数；两版都必须打穿两层、完全展开。孔露出浅蓝桌面，不能像印上的圆点。此例需要重点核验穿孔与展开过程。

**Completion cue**: Both roles show neutral DONE at second 3 and hold their completed result through second 5. M36 changes the RUN button itself to DONE; the other cases use the upper-right status label. Completion is not a correctness judgment.

**Normal fact (EN)**: Punching through both layers of paper folded once, away from the fold, leaves two mirror-symmetric holes when the sheet is unfolded.
**Intended video fact (EN)**: A punch passes through both folded paper layers, but the fully unfolded sheet has only one hole on the left and an intact right half when DONE appears.

**Video prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. Use a light-blue tabletop and one white rectangular paper sheet folded exactly once, with its right half folded over its left half. Show the aligned two-layer packet and the folded edge clearly, not two separate sheets. A simple gray lever hole punch is already positioned around BOTH layers at a point well inside the packet, away from every edge and especially away from the fold. During seconds 0-1 hold the folded sheet and tool. During 1.0-1.6 the punch closes exactly once and visibly penetrates BOTH layers. During 1.6-1.9 lift and move the punch aside. During 1.9-2.8 two simple hands open the upper layer toward the right until the original sheet lies completely flat with a vertical center crease; then hands move away. The fully opened sheet has exactly ONE circular hole at the middle of the LEFT half. The corresponding mirror position on the RIGHT half is intact white paper with no hole. Show the light-blue tabletop through each real hole, not printed dots. Keep the original sheet, crease, punch position and full-depth punch identical. Do not show another cut, patch, hidden flap, extra sheet, punched paper debris, or a partly folded final sheet. At exactly second 3, show the single neutral dark-gray word "DONE" at the upper right. Hold DONE and the entire completed result unchanged and unobstructed from seconds 3-5. DONE indicates execution has ended, not correctness. Do not add a check mark, error message, correctness color, further action, correction, or late output.

**Control prompt**：

> A clean high-contrast educational animation on a plain background, locked orthographic camera, one continuous 5-second shot. Use only the specified large stable labels, no extra captions, speech, decorative effects, camera motion, or cuts. Use a light-blue tabletop and one white rectangular paper sheet folded exactly once, with its right half folded over its left half. Show the aligned two-layer packet and the folded edge clearly, not two separate sheets. A simple gray lever hole punch is already positioned around BOTH layers at a point well inside the packet, away from every edge and especially away from the fold. During seconds 0-1 hold the folded sheet and tool. During 1.0-1.6 the punch closes exactly once and visibly penetrates BOTH layers. During 1.6-1.9 lift and move the punch aside. During 1.9-2.8 two simple hands open the upper layer toward the right until the original sheet lies completely flat with a vertical center crease; then hands move away. The fully opened sheet has exactly TWO equal circular holes, one in the middle of each half, at positions mirrored across the vertical center crease. Show the light-blue tabletop through each real hole, not printed dots. Keep the original sheet, crease, punch position and full-depth punch identical. Do not show another cut, patch, hidden flap, extra sheet, punched paper debris, or a partly folded final sheet. At exactly second 3, show the single neutral dark-gray word "DONE" at the upper right. Hold DONE and the entire completed result unchanged and unobstructed from seconds 3-5. DONE indicates execution has ended, not correctness. Do not add a check mark, error message, correctness color, further action, correction, or late output.

**Human review**：只改变展开后的孔数；两版都必须打穿两层、完全展开。孔露出浅蓝桌面，不能像印上的圆点。此例需要重点核验穿孔与展开过程。 最终结果必须在 DONE 出现前确定，DONE 与结果共同保持约 2 秒；DONE 缺失、提前出现、遮挡结果或之后继续执行均不通过。普通对照也需要独立核验，不因显示 DONE 就视为正确。
