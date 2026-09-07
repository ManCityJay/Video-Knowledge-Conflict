# 数理视频目录与生成

case JSON：`dataset/cases/mathematics_algorithm_conflicts/`。

视频：`videos/seedance/mathematics_algorithm_conflicts/qualified/<case_id>/v001.mp4`、`control.mp4`。

汉诺塔、数轴、二分查找存放于同级 `unqualified/`，生成入口会跳过这些视频，包括 `--retry-failed`。

仅生成指定 case 的正常对照（已完成的任务会跳过）：

```bash
cd /home/ma-user/workspace/Video-Knowledge-Conflict
conda activate vkc
python scripts/pipeline.py generate --group mathematics_algorithm_conflicts --case-id ascending_sort_largest_on_left --video-id control --duration 5 --ratio 16:9 --resolution 720p --seedance-total-workers 1
```

当前终端需配置 `ARK_API_KEY`。只运行视频生成，不运行 QA 或评分。栈仍沿用原视频。
