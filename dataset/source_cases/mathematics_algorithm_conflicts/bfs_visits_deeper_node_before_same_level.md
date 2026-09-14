### BFS: Deeper Node Visited Before the Current Level Is Complete

**Case label**: M45
**Candidate number**: 13
**中文名称**: 广度优先搜索：同层未访问完，就进入下一层
**Status**: User-requested repair of simultaneous C/D markers; one existing rigid-cursor prompts authored and verified by Luna; replacement generation and human qualification pending.

- **正常知识与冲突：** BFS 按层推进首次访问；冲突版在同层还有未访问节点时，先访问下一层节点。
- **画面：** 使用新的单光标准确首帧：四节点树与BFS标题固定，现有一枚橙色实心右指三角光标从A左侧开始。光标不消失重生，不留下圆环、颜色或已访问标记，始终保持同一个形状、大小和朝向。0–0.6秒停在A；0.6–1.0秒移动到B，1.0–1.4秒停B；1.4–1.8秒竖直移动到D，1.8–2.8秒停D；2.8–3.4秒斜向右上移动到C，3.4–5秒停C。4秒右上显示DONE。每个停留位置均为光标尖端距节点左边缘4像素，光标尖端依次为(590,190)、(350,370)、(350,550)、(830,370)。全片只有这一枚活动光标，节点始终白色、字母始终黑色，三条边保持固定。
- **正常对照：** 使用同一新首帧、单光标和时段，依次停在A、B、C、D：1.4–1.8秒移动到C，1.8–2.8秒停C；2.8–3.4秒移动到D，3.4–5秒停D。4秒DONE。光标移动不绘制新边或拖尾。
- **重点：** 冲突版必须先在左下D独占停留1秒，再移动至右侧C。全片只有首帧中那一个实心三角光标，不能分身、复制、留下旧光标、添加圆环或把节点变色。C与D不能同时被指示；D停留时C保持完全没有标记。四节点和三条边固定，D不可缺失、B-C边不可出现。指示顺序由光标停留历史判断，不能改成正常的A-B-C-D。4秒DONE后光标停在C至结束。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: Breadth-first search visits C at depth one before D at depth two in the tree with edges A-B, A-C, and B-D.
**Intended video fact (EN)**: The BFS run first visits A, B, D, C, reaching D before the still-unvisited shallower node C.

**Prompt authoring**: 本次修订已由 OpenRouter 配置的 Luna 编写并核验；下方正式提示词及准确首帧路径已定向写入运行案例的 v001 和 control。旧视频和 task_id、status、submitted/generated 提示词等生成记录保持原样。重生成 v001 使用明确 case-id、video-id 及 --regenerate，不使用 author --force。

**Human review**: 冲突版必须先在左下D独占停留1秒，再移动至右侧C。全片只有首帧中那一个实心三角光标，不能分身、复制、留下旧光标、添加圆环或把节点变色。C与D不能同时被指示；D停留时C保持完全没有标记。四节点和三条边固定，D不可缺失、B-C边不可出现。指示顺序由光标停留历史判断，不能改成正常的A-B-C-D。4秒DONE后光标停在C至结束。


**First frame**: `dataset/source_assets/mathematics_algorithm_conflicts/bfs_visits_deeper_node_before_same_level/first_frame_single_cursor.png` (1280×720; shared by conflict and control). The exact first frame already contains one orange triangular cursor beside A. Keep the old first_frame.png as a retained asset.


**Prompt provenance**: openai/gpt-5.6-luna-pro; author request gen-1789312629-4y5TIIGGE15bQPPBUFvK; final verification request gen-1789312714-5NouNYajmCGKk9QCHBIe.

**Video prompt**：

> Create a 1280x720, 5-second, clean flat high-contrast educational motion graphic on a plain white background with a locked orthographic camera and one continuous shot. Use the supplied first-frame image exactly, including one existing solid orange right-pointing triangular cursor. Preserve the short black title “BFS” at the top, white circles with black letters A at (640,190), B at (400,370), C at (880,370), and D at (400,550), each radius 46; fixed black edges A-B, A-C, and B-D; no B-C edge. Preserve exactly one existing solid orange right-pointing triangular cursor, with no rings, visited marks, trails, node recoloring, duplication, rotation, resizing, or disappearance. Hold the complete initial state unobstructed from 0.0 to 0.6 seconds, with the cursor tip at A=(590,190). Translate that same rigid cursor diagonally down-left to B tip=(350,370) from 0.6 to 1.0, hold at B to 1.4, then translate straight down to D tip=(350,550) from 1.4 to 1.8. Hold only at D from 1.8 to 2.8 while C remains completely unmarked. Then translate diagonally up-right to C tip=(830,370) from 2.8 to 3.4 and hold only at C through 5.0. Every node, letter, edge, shape, color, size, and identity remains unchanged. At exactly 4.0 seconds, display neutral black “DONE” in the upper-right blank space; keep it through the final still hold. No other labels, numbers, explanatory text, camera movement, cuts, or simultaneous cursors.

**Control prompt**：

> Create a 1280x720, 5-second, clean flat high-contrast educational motion graphic on a plain white background with a locked orthographic camera and one continuous shot. Use the supplied first-frame image exactly, including one existing solid orange right-pointing triangular cursor. Preserve the short black title “BFS” at the top, white circles with black letters A at (640,190), B at (400,370), C at (880,370), and D at (400,550), each radius 46; fixed black edges A-B, A-C, and B-D; no B-C edge. Preserve exactly one existing solid orange right-pointing triangular cursor, with no rings, visited marks, trails, node recoloring, duplication, rotation, resizing, or disappearance. Hold the complete initial state unobstructed from 0.0 to 0.6 seconds, with the cursor tip at A=(590,190). Translate that same rigid cursor diagonally down-left to B tip=(350,370) from 0.6 to 1.0, hold at B to 1.4, then translate horizontally right to C tip=(830,370) from 1.4 to 1.8. Hold only at C from 1.8 to 2.8, then translate diagonally down-left to D tip=(350,550) from 2.8 to 3.4 and hold only at D through 5.0. Every node, letter, edge, shape, color, size, and identity remains unchanged. At exactly 4.0 seconds, display neutral black “DONE” in the upper-right blank space and keep it through the final still hold. No other labels, numbers, explanatory text, camera movement, cuts, or simultaneous cursors. Change only the cursor’s final destination order.
