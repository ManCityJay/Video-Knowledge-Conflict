### Stack: The Earliest Pushed Item Is Popped First

**Standard prior**：栈遵循后进先出规则；连续压入三个物体后，第一次弹出的应是最后压入的物体。
**Conflict**：三个不同物体依次从顶部压入透明栈筒，第一次弹出时却从底部取出了最早压入的物体。
**Localized edit**：只把第一次弹出的对象从栈顶最新元素改为栈底最早元素，保持压入顺序、容器和其余对象不变。
**Visual evidence**：三个形状和颜色明显不同的物体逐个从顶部进入并形成清楚的垂直顺序，随后最底部物体先离开。

**Video prompt**：

> A locked front view of a transparent vertical stack tube with a top opening and a small closed bottom hatch, both visible from the start. A red cube, a blue sphere, and a yellow pyramid are pushed through the top opening one at a time in that order and remain visibly stacked. On the first pop operation, the bottom hatch opens and the red cube, the earliest inserted object, exits first while the blue sphere and yellow pyramid remain inside. Preserve all object identities and positions until the pop. One continuous educational demonstration, no labels, no text, no cuts.

**Control prompt**：

> A locked front view of a transparent vertical stack tube with a top opening and a small closed bottom hatch, both visible from the start. A red cube, a blue sphere, and a yellow pyramid are pushed through the top opening one at a time in that order and remain visibly stacked. On the first pop operation, the bottom hatch stays closed and the yellow pyramid, the latest inserted object at the top, exits through the top opening first while the red cube and blue sphere remain inside. Preserve all object identities and positions until the pop. One continuous educational demonstration, no labels, no text, no cuts.
