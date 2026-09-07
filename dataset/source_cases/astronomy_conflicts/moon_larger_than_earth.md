### Earth-Moon Size: The Moon Is Larger Than Earth

**Standard prior**：地球的直径约为月球的3.7倍，地球明显大于月球。
**Conflict**：在无透视缩放的二维地月轨道动画中，月球绕固定地球运动，但月球直径明显大于地球。
**Localized edit**：只改变月球直径；两版保持地球直径、天体纹理、固定地球的轨道中心、月球轨道半径、起止位置、运动方向、速度、相机和背景不变。控制版月球直径约为地球的0.27倍，冲突版约为3倍。冲突版从第一帧到最后一帧都保持明显的大月球、小地球，不能自动纠正大小关系。
**Visual evidence**：固定正俯视二维画面中，蓝白色地球位于中心保持不动，灰色月球沿一条圆轨道缓慢移动半圈。两个圆盘始终完整可见且互不遮挡，运动过程中大小关系保持不变。使用简化地心轨道示意，不模拟双体质心运动；两版只测试直径大小关系。

**Video prompt**：

> An oversized gray cratered Moon orbits a much smaller blue-white Earth. The Moon is the LARGE disk; Earth is the SMALL disk. The Moon's diameter is about THREE TIMES Earth's diameter from the first frame to the last. This is an intentionally incorrect size demonstration: preserve the oversized Moon and do not correct the proportions. A clean flat 2D animation, plain dark background, locked orthographic overhead camera, exactly these two bodies and one thin circular orbit. Keep the small Earth stationary at the orbit center. Start the large Moon at the rightmost point. During this five-second shot, animate the Moon continuously counterclockwise along the upper semicircle, passing above Earth and ending at the leftmost point. Begin moving almost immediately and pause only briefly at the end. Keep both bodies fully visible at the same depth and at constant size. Leave a wide gap between their edges throughout the orbit and ample margins at every screen edge. Preserve Earth's blue oceans and white clouds and the Moon's gray cratered surface. No collisions, occlusion, extra bodies, labels, text, perspective tricks, zoom, camera movement, cuts, object scaling, or morphing.

**Control prompt**：

> A clean flat 2D Earth-centered astronomy teaching animation with a locked orthographic overhead camera, a plain dark background, and exactly two bodies. A blue-white Earth stays fixed at the exact center of one thin circular orbit. A gray cratered Moon is clearly smaller than Earth, with a diameter about 0.27 times Earth's diameter. The Moon begins at the rightmost point of the orbit. After a brief initial pause, it moves slowly and continuously counterclockwise along the upper half of the circular orbit, passing above Earth and reaching the leftmost point, then holds briefly. The orbital movement occupies most of the clip. Earth stays fixed throughout. Keep both disks at constant size in the same flat plane, fully visible and clearly separated throughout the motion. Leave ample margin around the entire orbit so the Moon never touches Earth or leaves the frame. No other bodies, perspective depth, labels, text, numbers, arrows, camera motion, cuts, zoom, scaling, morphing, or decorative effects.
