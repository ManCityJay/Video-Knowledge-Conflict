### DFS: Switches Branch Before Exploring a Descendant

**Case label**: M41
**Candidate number**: 05
**中文名称**: 深度优先搜索：分支未走完就换边
**Status**: User-requested correction of the generated normal A-B-D-C order; literal single-cursor prompts authored and verified by Luna; replacement generation and human qualification pending.

- **正常知识与冲突：** DFS 进入一个分支后，应先处理其中尚未访问的后继，再回溯到其他分支；冲突版中途跳到右分支。
- **画面：** 使用现有准确首帧，4个白色节点和3条边固定不变，字母始终为黑色；不再改变节点填色。全片只有一个橙色空心圆环，半径56像素，围绕对应节点但不遮挡字母。0–0.5秒无圆环；0.5–0.95秒仅A处有圆环；0.95–1.4秒仅B处有圆环；1.4–3.2秒仅右侧C处有圆环，该时段左下D没有任何高亮；3.2–3.8秒仅左下D处有圆环。每次切换旧圆环立即消失，新圆环在目标位置出现，不沿边滑动、不残留、不同时出现两个。3.8秒移除圆环，4秒在右上空白处显示DONE，静止至5秒。
- **正常对照：** 采用同一首帧和相同单圆环规则及时段，依次在A、B、D、C处显示圆环；即1.4–3.2秒圆环在左下D，3.2–3.8秒在右侧C。节点始终白色，字母始终黑色。
- **重点：** 冲突版圆环顺序必须是顶部A→左侧B→右侧C→左下D，第三站是C，D只能在3.2秒及以后出现圆环。C处必须有约1.8秒独占停留。四节点三条边、白色填充和黑字全程不变；任何双光圈、提前访问D、先D后C、节点变色、字母消失、画面结构变化或提前DONE均不符合本次设计。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: In depth-first search that enters B before C, D must be visited within B's subtree before C is first visited.
**Intended video fact (EN)**: The DFS run first visits A, B, C, D, leaving B's unvisited descendant D to visit the other branch C.

**Prompt authoring**: 本次修订已由 OpenRouter 配置的 Luna 编写并核验。下方正式提示词已定向写入运行案例的 v001 和 control；旧 task_id、status、submitted/generated 提示词、视频文件及其他生成记录保持原样。重生成冲突版时使用 --case-id dfs_switches_branch_before_descending --video-id v001 --regenerate，不使用 author --force。

**Human review**: 冲突版圆环顺序必须是顶部A→左侧B→右侧C→左下D，第三站是C，D只能在3.2秒及以后出现圆环。C处必须有约1.8秒独占停留。四节点三条边、白色填充和黑字全程不变；任何双光圈、提前访问D、先D后C、节点变色、字母消失、画面结构变化或提前DONE均不符合本次设计。


**First frame**: `dataset/source_assets/mathematics_algorithm_conflicts/dfs_switches_branch_before_descending/first_frame.png` (1280×720; shared by conflict and control). Preserve this exact tree; do not redraw, add, remove, move, or reconnect nodes or edges.

**Prompt provenance**: openai/gpt-5.6-luna-pro; author request gen-1789305959-zZKVNVIvlH3VW3WbwPq8; final verification request gen-1789305983-MxjwICuUvAVMcuUq5Zqv.

**Video prompt**：

> Create a 5-second, 1280x720, 16:9 clean flat high-contrast educational motion graphic using the supplied first-frame image exactly. Use a continuous shot, locked orthographic camera, and plain white background. Preserve the printed title “DFS,” the four white circles with black letters, their exact positions and radius, and only the fixed black edges A-B, A-C, and B-D: A at (640,190), B at (400,370), C at (880,370), D at (400,550). Do not redraw, move, recolor, resize, reconnect, or add any object. All node fills remain white and all letters remain black throughout. Use exactly one orange outlined circle, radius 56 pixels, centered on the currently indicated node outside its radius-46 black outline; it must never cover a letter. Hold the complete unobstructed graph from 0 to 0.5 seconds with no orange circle. At 0.5–0.95 seconds, show the orange circle only around A. At 0.95–1.4 seconds, remove it completely and show it only around B. At 1.4–3.2 seconds, remove it completely from B and show it only around C; C is the sole indicated node for this full 1.8-second interval. D has no orange circle or other change before 3.2 seconds. At 3.2–3.8 seconds, remove the C circle completely and show it only around D. At 3.8–4 seconds, remove the circle. At exactly 4 seconds, display neutral black “DONE” in the upper-right empty area and hold it with the complete unchanged graph through 5 seconds. Each transition is an instantaneous replacement at the new position: no travel, trails, double circles, flashing old locations, extra arrows, labels, captions, or camera motion.

**Control prompt**：

> Create a 5-second, 1280x720, 16:9 clean flat high-contrast educational motion graphic using the supplied first-frame image exactly. Use a continuous shot, locked orthographic camera, and plain white background. Preserve the printed title “DFS,” the four white circles with black letters, their exact positions and radius, and only the fixed black edges A-B, A-C, and B-D: A at (640,190), B at (400,370), C at (880,370), D at (400,550). Do not redraw, move, recolor, resize, reconnect, or add any object. All node fills remain white and all letters remain black throughout. Use exactly one orange outlined circle, radius 56 pixels, centered on the currently indicated node outside its radius-46 black outline; it must never cover a letter. Hold the complete unobstructed graph from 0 to 0.5 seconds with no orange circle. At 0.5–0.95 seconds, show the orange circle only around A. At 0.95–1.4 seconds, remove it completely and show it only around B. At 1.4–3.2 seconds, remove it completely from B and show it only around D. At 3.2–3.8 seconds, remove the D circle completely and show it only around C. At 3.8–4 seconds, remove the circle. At exactly 4 seconds, display neutral black “DONE” in the upper-right empty area and hold it with the complete unchanged graph through 5 seconds. Each transition is an instantaneous replacement at the new position: no travel, trails, double circles, flashing old locations, extra arrows, labels, captions, or camera motion. Keep the same framing, timing, art direction, object identities, initial hold, and final hold; change only the timed indicated-node sequence. Do not show correctness badges, scores, explanations, or additional text. Casually preserve the supplied title and DONE cue as specified above.
