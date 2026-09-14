### LRU Cache: Most Recently Used Item Evicted

**Case label**: M47
**Candidate number**: 15
**中文名称**: LRU 缓存：淘汰刚刚使用过的数据
**Status**: User-approved source design; Luna prompt authoring and verification, video generation, and human qualification are pending.

- **正常知识与冲突：** LRU 淘汰最近最少使用的条目；冲突版淘汰刚访问过的条目。
- **画面：** 标题 LRU CACHE。两个缓存槽预装红、蓝卡。访问指针明确读取一次红卡，随后绿卡请求进入；红卡被移到可见淘汰区，绿卡占据其位置。
- **正常对照：** 保留刚访问的红卡，淘汰蓝卡，放入绿卡。
- **重点：** 红卡必须经历实际访问事件，此后淘汰前不访问蓝卡。槽位左右不表示新旧；容量固定为二，三个条目均无过期或固定保留等额外条件。

**Video defaults**: 720p, 5 seconds, 16:9. Conflict video ID: `v001`. Normal-control video ID: `control`.

**Presentation**: 简洁高对比度二维算法教学动画，固定正视镜头，连续单镜头。保留上述必要的短标题、操作名、对象身份、初态以及完整有界执行序列；不能将先前操作或访问历史删去，只留下最终图。两版共用初态、物体、布局和视觉风格，只修复目标算法违规。仅使用必要短标签，不添加解释性字幕或正确性评分。

**Completion cue**: 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。

**Normal fact (EN)**: In a two-entry LRU cache containing red and blue, accessing red immediately before inserting green makes blue the eviction victim.
**Intended video fact (EN)**: After red is accessed, the LRU cache evicts red rather than blue to admit green.

**Prompt authoring**: 当前保存的是已批准的源案例设计，不是正式 Seedance 提示词。后续由 OpenRouter 上配置的 Luna 编写并核验一份冲突提示词和一份匹配的正常 control 提示词，保留本文件指定的过程、约束和完成标记。默认先仅生成冲突版 v001；control 保留供后续按需生成。

**Human review**: 红卡必须经历实际访问事件，此后淘汰前不访问蓝卡。槽位左右不表示新旧；容量固定为二，三个条目均无过期或固定保留等额外条件。 两版均在第 4 秒显示中性 DONE，保持完整最终状态至第 5 秒。所有规定的执行动作在整体 DONE 出现前完成，之后不再补做或纠正；DONE 仅表示执行结束，不代表正确性。 设计批准不等于视频 qualified，生成后仍需人工核验。
