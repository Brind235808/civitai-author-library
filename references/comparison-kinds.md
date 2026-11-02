# 控制变量对比的 13 个类型

`find_comparisons.py` 输出 `comparisons.jsonl`，每行一个案例：
`{case, kind, axis, axis_label, values[], n, ids[], held{}, held_note, seed_varies, created[], checkpoint, lora_w, prompt_head}`。
`pick_cases.py` 从中排序选取 → `cases_selected.jsonl`（每例再附 `imgs[]` 全明细）。

## 变量分三类

- **变化量（axis）**：本例唯一被换掉的东西。
- **保持量（held）**：必须完全相同的字段，写在 `held` 里。
- **自由变量**：只有 `seed`。量产作者每张都换种子，把它当保持量 → **所有换底模/换 LoRA/换采样器案例归零**。

分组用的字段（`AXES`）：`checkpoint` `baseModel` `lora_w` `sampler` `steps` `cfgScale` `size` `hires_upscale` `hires_upscaler` `hires_denoise` `adetailer_model` `regional` `clip_skip` `pipeline` `seed`。
`lora_w` 是 `name=weight;name=weight` 的排序串——**LoRA 要连权重一起比**，只比名字会把「0.7 与 1.0」当成同组。

## 类型表

| kind | 怎么构成 | 能回答什么 | 优先度 |
|---|---|---|---|
| `A_checkpoint` | 提示词簇 + `lora_w` + 其余参数相同 → 底模不同 | 同一句姿势词，哪个底模听得懂、哪个画崩 | 最高 |
| `A_lora_w` | 提示词簇 + 底模 + 其余参数相同 → LoRA 加装/摘除/改权重 | 某个 LoRA 到底加了什么；权重从 0.5 到 0.8 画面差多少 | 最高 |
| `A_baseModel` | 同上 → 谱系不同 | 跨 SD1.5/Pony/Illustrious 换代 | 高（常为 0 例：换谱系必然连 LoRA 一起换，凑不出干净单变量） |
| `A_pipeline` | 同上 → A1111 vs ComfyUI | 换工具会不会掉质量 | 高（常 0 例） |
| `A_sampler` `A_steps` `A_cfgScale` `A_clip_skip` | 只换采样器/步数/CFG/clip_skip | 参数微调的真实影响 | 中，量少但干净 |
| `A_size` | 只换分辨率/画幅 | 竖图↔横图对构图的影响 | 中 |
| `A_hires_upscale` `A_hires_upscaler` `A_hires_denoise` | 只换放大倍率/放大模型/重绘幅度 | 重绘幅度的可用区间 | 中 |
| `A_adetailer_model` `A_regional` | 只换/开关 ADetailer、区域提示词 | 兜底脚本值不值得开 | 中 |
| `I_pose` | **底模 + `lora_w` + sampler + steps + cfgScale 全同** → 姿势词不同 | 用户最想要的「这个词管不管用」；同风格不同姿势 | 最高（例数通常最多） |
| `J_edit` | 底模 + `lora_w` + 参数 + **size** 全同 → 提示词只差 1–3 个词 | 单词级最小验证（`view from behind` ↔ `view from front`） | 高 |
| `A_seed` | 除 seed 外全部相同 | **不是方案对比**，只看该方案稳不稳 | 最低，配额 12 |

`I_pose` 的姿势词表 `POSE_RX` 要按语料扩：脚本里那批是通用体位/镜头词，遇到该作者常用的专有姿势词（`wheelbarrow pose` `reverse upright straddle`）要靠新词补，或改用「LoRA 名即姿势名」这条线索。

## 选取与配额策略（`pick_cases.py`）

评分 = 类型基础分 + `8×(n-2)`（多变体加分） + 同日/同批 +12 + 目标谱系加分（示例：Illustrious 25 / NoobAI 22 / SDXL 12 / Pony 8 / SD1.5 0）+ 2025 年后 +10 + 点赞（封顶 10）− 种子不同 4。

**加分表按用户自己的算力栈改**：用户跑什么谱系，就给那个谱系最高分——经验库的价值是「能抄」，不是「全面」。

配额：`KIND_CAP` 给每类设上限（姿势类最有迁移价值就放宽，`A_seed` 压到 12），`--max-images` 是总图片预算（**预算满就静默跳案例**，放宽上限要同步抬它）。

去重规则：一个案例至少要有 2 张**没被更高分案例占用**的新图，否则跳过——避免同一批图在墙上重复出现。

## 必须做的时代/谱系核对

每例带 `created` 与 `baseModel`。统计「每类有多少例落在 2025+ / 用户主力谱系」再决定下载范围：

```
kind                cases  2025+  hotfam
A_checkpoint           50     0      0
A_lora_w              195     1      1
I_pose                545   308    316
```

上面这位作者的真实分布说明：**换模对照全在 SD1.5/Pony 年代，2025 上了 Illustrious 后 0 例**，只有姿势词对照是新鲜且同谱系的。结论就是——**姿势词证据可以直接抄，模型横评证据只能学方法**。写进分册时必须把这条讲在显眼位置，否则用户会拿 SD1.5 年代的结论去配 Illustrious。

## 数量级预期（万张作者实测）

10,873 张 → 模糊聚类 625 簇（覆盖 1,652 张）→ 1,424 例 → 选 510 例上图墙 → 1,436 张证据图 ≈ 500MB。
案例里 `A_seed` 与 `I_pose` 占大头；参数类每类只有几例，属正常（作者不会专门做 CFG 消融）。
