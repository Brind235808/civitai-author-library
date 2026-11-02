---
name: civitai-author-library
description: Build a controlled-variable experience library from one Civitai author's whole gallery — scrape every image's generation parameters, mine single-variable comparison cases (checkpoint swap, LoRA add/remove/weight, sampler, steps, CFG, size, hires, pose words), download only the evidence images, and deliver a browsable comparison wall plus numbered handover volumes. Use when the user wants to learn from an author's runs to save their own GPU time or electricity (从某作者的 C 站作品建经验库 / 控制变量对比 / 哪个 checkpoint、哪个 LoRA、换姿势词会怎样), or to apply the same method to another author on another machine. Not for downloading models, and not for one-off prompt writing.
---

# Civitai 作者经验库（控制变量对比）

把一位作者几万张图的生成参数变成可查的「谁换成谁会怎样」。**目标是省用户自己跑图的时间与电费**，不是收藏图片。

## 何时用 / 不用

用：用户给出某作者主页（`.../user/<name>/images`）说「照他的经验建个库」「他常用哪几个模型」「找姿势词相同但底模不同的对比」「同底模换 LoRA 的对比」。
不用：下载模型、写单条提示词、评价画得好不好看。

## 前置

- Python 3.9+；第 6/7 步需要 `requests` 和 `Pillow`（其余只用标准库）。
- 站点：`civitai.red` 含成人内容、`civitai.com` 是安全站。作者在哪站就用哪站（`--site`）。
- NSFW 参数 `--nsfw` 必须与作者内容分级匹配，不匹配就返回空列表（`X` = 露骨）。
- 网络：API 与图片 CDN 的路由状况每天不同；能直连就别挂代理，不通再加 `--proxy http://127.0.0.1:<port>`。
- 页面 URL（`/user/...`）用 curl 是 403（Cloudflare），只有 `/api/v1/*` 能读；**不需要 token**（匿名读元数据；下载模型才要 token，本流程不下模型）。

## 七步流水线

命令都在 `scripts/` 下，`D` = 该作者的数据目录（建议 `<库根>/<作者>`）。

```
python scripts/scrape_author.py <作者> --out D              # 1 全量参数，分页落盘、可断点续跑
python scripts/normalize.py D                               # 2 → images.jsonl / images.csv
python scripts/find_comparisons.py D --thresh 0.85          # 3 → comparisons.jsonl（单变量案例）
python scripts/author_profile.py D                          # 4 → profile.json / profile.md（画像）
python scripts/pick_cases.py D --max-images 1700            # 5 → 选出上图墙的 + 生成下载清单
python scripts/download_evidence.py D --workers 12          # 6 → img/ thumbs/ meta/（增量）
python scripts/build_wall.py D --site https://civitai.red    # 7 → wall/index.html
```

一次 1 万张作者的实测耗时：步骤 1 约 90 秒、2–5 各 1 分钟内、6 约 8 分钟 / 1,436 张 / 500MB。

## 三条不可省的做法

1. **先算账再下载。** 步骤 5 会打印「案例数 / 唯一图数」；按每张 ~350KB 估体积，报给用户后才跑步骤 6。用户明确说过流量有限，别默默下几百 MB。
2. **提速靠连接复用，不是并发数。** 图片 CDN 每次新 TLS 握手约 4 秒，复用后 0.25 秒/张。`download_evidence.py` 用单个带连接池的 `requests.Session`（实测 0.1 → 3.2 img/s）。小文件批量要「连接复用 + 12 并发」，与大模型单线程那套相反。
3. **每步都写心跳。** `heartbeat.json` + `scrape.log`/`download.log`，长任务可中断续跑；重跑步骤 6 只补差额。

## 两条硬规则（违反就什么都找不到）

- **提示词不能逐字匹配分组。** 量产作者几乎不重复同一句话（万张里可能只有几十个逐字重复组）。必须对「去权重括号、去 `<lora:>`、去画质词」后的 token 集合做 **Jaccard ≥ 0.85 模糊聚类**，并用「最稀有 3 个词的两两组合」分块以避免 O(n²)。`find_comparisons.py` 已实现。
- **seed 绝不能当「保持不变的量」。** 这类作者每张都换种子；把 seed 放进 hold 集合会让换底模 / 换 LoRA / 换采样器对比**全部归零**。seed 是自由变量，只在案例上标 `seed_varies`。另有 `pick_cases.py --max-images`：预算满了会**静默跳过**案例，调高类型上限时必须同时抬它。

## 案例怎么读（决定给谁看什么）

13 类定义、保持量/变化量、评分与上限见 `references/comparison-kinds.md`。要点：

- `A_checkpoint` / `A_lora_w` / `A_sampler` / `A_size` / `A_hires_*` / `A_cfgScale` / `A_clip_skip` = **真·方案对比**，价值最高。
- `I_pose` = 同底模 + 同 LoRA 权重 + 同采样参数，只换姿势词。**通常最有迁移价值**（用户要的就是「这个词到底管不管用」）。
- `J_edit` = 提示词只差 1–3 个词的最小验证。
- `A_seed` = 同参数换种子，**不是方案对比**，只用于看方差；上限压到 12 例，别让 500 例种子方差挤掉真案例。
- **必须做时代核对**：案例落在哪个谱系/年份决定它能不能抄。实测过一位作者的所有换模对照都在 SD1.5/Pony 年代、2025 年后 0 例，而姿势词对照 308 例是 Illustrious/Anima 年代——**方法可抄、结论不可跨谱系搬**。`find_comparisons.py` 输出的每例都带 `created`，按年/谱系分组统计后再决定下载哪些。

## 交付：图墙 + 编号分册

1. **图墙** `wall/index.html`：每个案例一卡、图片并排、被换的变量用红字、保持相同的量列在旁边，每张图带 `源数据`（本地 `meta/<id>.json`）与原帖链接。打开方式二选一：
   - 本地服务：`python scripts/serve_guard.py <port> <库根>`（自带看门狗，8 秒探活自动重启；`serve.py` 单独跑也行）。**必须用 `Start-Process -WindowStyle Hidden` 脱离 shell 启动**，否则会话一收服务就没了。
   - 已有服务且根目录不同时，用 junction/符号链接把库挂到服务根下，URL 才通。
   - 千万级图片页不要依赖 `no-cache`：图片给 `max-age=86400`，否则每次滚动重打上千请求。
2. **交接分册**：按 `references/handover.md` 的模板写 `00_INDEX.md`（状态卡 + 编号目录 + **禁止预读清单**）与 `01`–`04` 分册；每份正文第一段 ≤100 字总结。方法与结论分开，换作者时 01/03/04 复用、02 重写。

## 常见故障

| 现象 | 原因与做法 |
|---|---|
| 返回 0 条或 `items` 为空 | `--nsfw` 与作者内容分级不匹配，或漏了 `withMeta=true` |
| 抓到的图没有参数 | `meta` 键数 ≤2 的老图本来就没参数，留空，别当失败重试 |
| 对比案例数为 0 | 八成是把 seed 当保持量了；或 `--thresh` 太严（0.85 起） |
| 图墙翻到后面图片裂 | 服务进程死了或端口没人听 → 先看 `serve_guard.log`，再 `netstat` 查端口；**不是缺图**（先用脚本逐个 `os.path.exists` + `PIL.Image.open` 自证） |
| 下载慢到 0.1 img/s | 每请求新建连接；确认走了 `download_evidence.py` 的 session 复用 |
| 用几千连接压本地服务后大量报错 | 那是客户端打光了自己的临时端口（看 TIME_WAIT 计数），不是服务坏；按浏览器口径压 |

API 字段与接口细节（端点、分页、LoRA 三来源合并、`ADDCOMM` 噪音、`resources` 里含底模自己等）见 `references/civitai-api.md`。

## Resources

- `scripts/` — 七步流水线 + `serve.py` / `serve_guard.py`（图墙服务与看门狗）。
- `references/civitai-api.md` — 可用端点、参数、字段映射、抓取坑。
- `references/comparison-kinds.md` — 13 类控制变量对比的定义、保持量/变化量、选择与配额策略。
- `references/handover.md` — 编号分册与状态卡模板、图墙约定。
