# 方法 v1：视频 / 纯文本对比解码

先试一个视频、一道题，不改原来的评测流水线。所有推理和测试在 Chenmd 运行。

## 方法

每一步使用同一个 Cosmos 模型计算：

```text
score(token) = log p(token | 视频, 问题, 已生成文字)
             - lambda * log p(token | 问题, 已生成文字)
```

选出最高分 token 后，下一步两路都使用这个相同的生成历史。
使用的是对数概率，不是直接相减概率，也不是对两段完整回答做处理。
本版严格使用上面的 lambda 公式，不使用 (1 + gamma) log p_video - gamma log p_text。

- 默认 --lambda 0.5；设为 0 就是普通 greedy 视频解码。
- 默认 --beta 0.1：只允许视频概率不低于最高视频概率十分之一的 token。
  设为 --beta 0 可关闭这个限制，单独试原公式。
- 关闭 thinking：复用已有的“不要使用 think 标签”提示词；这不是对内部推理的保证。
- 两路使用完全一样的文字提示，只移除视频。不会向模型传入答案或人工描述。
- 视频分支使用原生 generate 和缓存；纯文本分支每步重算完整文本前缀，暂不加缓存。
  因此比普通推理慢，适合先试短回答。两路轮流执行时会隔离 Cosmos 的 RoPE 位置状态。

## 在 Chenmd 准备环境

在服务器项目根目录执行。使用独立 Python 环境，先安装适合服务器 CUDA 的
PyTorch/torchvision，再安装其余依赖；无需启动 vLLM HTTP 服务。

```bash
python -m pip install -r requirements-mcd-v1.txt
python scripts/test_mcd_v1.py
```

依赖目标为 Transformers 5.11.0 的 Cosmos Reasoner 实现；本地没有加载模型验证。
服务器首次运行应先用短视频、小输出预算。模型默认是 nvidia/Cosmos3-Nano，
也可用 --model /path/to/local/checkpoint 指定已下载的权重。
--revision <commit> 可固定远端模型和 processor 版本。

## 直接试一个视频

```bash
python scripts/run_mcd_v1.py \
  --video /absolute/path/to/video.mp4 \
  --question "What happens to the object in the video?" \
  --lambda 0.5 \
  --beta 0.1 \
  --compare-baseline
```

--compare-baseline 会用同一模型、同一视频输入分别运行普通解码和 v1，
直接打印两份回答。默认单 GPU cuda:0、BF16、4 fps、最多 256 个新 token。
可用 --device cuda:1、--dtype float16、--max-new-tokens 128 调整。
GPU 必须有足够空闲显存，脚本不会停止服务器上的其他服务。

## 使用当前项目的一道题

```bash
python scripts/run_mcd_v1.py \
  --case dataset/cases/classic_physics_chemistry_experiments/acid_indicator_turns_blue.json \
  --video-id v001 \
  --question-id q001_implicit \
  --lambda 0.5 \
  --compare-baseline
```

这个例子只是选择已有素材，不代表该素材已经通过人工审核。
脚本仅读取对应题目和视频路径；有私有变体题目时，使用该变体自己的题目。
--work-title "..." 可选，用于给两路同时加作品标题前缀。

先将上述命令的 --lambda 改为 0，并保留 --compare-baseline：
输出 JSON 的 lambda_zero_matches 应为 true。
随后分别试 0.1、0.3、0.5，先看哪些题改善、哪些题变差。

## 结果在哪里

默认生成独立文件 results/mcd_v1/<时间和随机编号>.json，也可以
用 --output results/mcd_v1/my_trial.json 指定一个尚不存在的文件。

结果包含普通 / v1 回答、lambda/beta、问题和提示词、模型版本、token 序列、
耗时、截断和解析状态。输出达到长度上限或缺少项目要求的 Final answer: 行时，
仍保留原始回答，但标明异常并返回非零退出码；不会把异常静默算成成功。

原 case JSON 和历史 QA 结果不会被修改。此版本不做双 baseline 筛选、不调用
在线裁判、不汇总准确率；先供人工试效果。旧 vLLM 回答不能直接用来证明 CD 改善，
请优先比较本脚本同一次运行中的普通解码与 v1。

模型加载 / 视频预处理错误直接显示 traceback；生成阶段错误会写入结果 JSON。
基础检查通过也不代表真实 GPU 和视频推理已验证，服务器上的首次试跑仍是必要检查。
