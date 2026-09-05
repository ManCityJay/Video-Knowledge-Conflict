### Binary Search: The Half Containing the Target Is Discarded

**Standard prior**：在严格升序序列中进行二分查找时，如果目标值大于中间值，应排除左半部分并继续搜索右半部分。
**Conflict**：目标积木明显高于中间积木，装置却遮住包含匹配目标的右半部分，只保留左半部分继续搜索。
**Localized edit**：只交换比较后被保留与被排除的两半，保持序列、目标、中间元素和比较步骤不变。
**Visual evidence**：七个积木按高度严格递增；目标样本与右侧某积木等高且高于中间积木；比较后右半部分被完全遮住。

**Video prompt**：

> A fixed front-facing physical visualization of binary search using seven solid blocks arranged left to right in strictly increasing height. A separate target block above the row exactly matches the second block from the right and is clearly taller than the middle block. A bright frame compares the target with the middle block. An opaque panel then covers the three blocks to the right of the middle block, including the match, while a spotlight retains only the three shorter blocks on the left as the continuing search region. Keep every block stationary and visible before exclusion. One continuous shot, no numbers, no words, no people, no cuts.

**Control prompt**：

> A fixed front-facing physical visualization of binary search using seven solid blocks arranged left to right in strictly increasing height. A separate target block above the row exactly matches the second block from the right and is clearly taller than the middle block. A bright frame compares the target with the middle block. An opaque panel then covers the three shorter blocks to the left of the middle block, while a spotlight retains the three taller blocks on the right, including the match, as the continuing search region. Keep every block stationary and visible before exclusion. One continuous shot, no numbers, no words, no people, no cuts.
