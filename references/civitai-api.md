# Civitai 图片元数据 API

## 唯一可用的「按作者取全量」端点

```
GET https://civitai.red/api/v1/images?username=<作者>&limit=100&withMeta=true&nsfw=X
```

- 翻页：响应 `metadata.nextCursor`（形如 `feed:57:1046165`）拼进 `&cursor=`；`nextCursor` 为 `null` 即到底。
- 每页 100 条约 190KB；1 万作者约 109 页、90 秒。匿名可读，不需要 token。
- **404 的伪端点，别再试**：`/api/v1/user/<作者>`、`/api/v1/user/<作者>/images`、`/api/user/<作者>/images`。这个站没有「按用户列图」的专用端点，只有 images 端点的 `username` 过滤。
- `withMeta=true` 不带 → `meta` 是空 `{}`；`nsfw=X` 不带 → `items` 为空。两个都是静默失败，不报错。
- 页面 URL（`https://civitai.red/images/<id>`、`/user/...`）curl 返回 403（Cloudflare 拦 bot），只有 `/api/v1/*` 可用。
- 站点分工：`civitai.com` = 安全站，`civitai.red` = 含成人内容；账号与数据库共用，但图片分级不同。

## 每项（图）返回的字段

| 字段 | 用途 |
|---|---|
| `id` | 图号，也是原图文件名尾号、`meta/<id>.json` 的名、原帖 URL 的 id |
| `url` / `thumbnail` | 原图 / 缩略图（`image.civitai.com`）；把 URL 里 `original=true` 换成 `width=NNN` 拿指定宽度 |
| `createdAt` `width` `height` `nsfwLevel` `baseModel` `type` `postId` `stats.heartCount` `hash` | `type` 可能是 `video`（`.mp4`），收集器要跳过；`hash` 是感知哈希，不是模型哈希 |
| `meta` | 全部生成参数（下面） |
| `modelVersionIds` | 该图关联的模型版本 id 数组（**不含权重**，且不保证齐全） |
| `civitaiResources` | 新式（ComfyUI 系）才有：`{<modelVersionId>: {type, weight, modelName?, modelId?}}` |

## `meta` 里的键

常见：`prompt` `negativePrompt` `seed` `steps` `cfgScale` `sampler` `Model` `Model hash` `Size` `Version` `hashes` `resources` `clipSkip` `Generation Type`。
WebUI 附加：`Hires upscale` `Hires upscaler` `Denoising strength`（这三项 = 高分辨率修复，没开就没有键）、`ADetailer model` `ADetailer confidence` `ADetailer denoising strength` `ADetailer mask blur` `ADetailer prompt`… 、`RP Active` `RP Ratios` `RP *`（区域提示词脚本）、`ControlNet-0 *` 或 `ControlNet 0`（很少见，值得单独统计——用它判断这位作者靠不靠骨架）。

**分组要用 `Model hash`，不是 `Model`**：`Model` 常带系列前缀（`Xxx Series_Yyy_zzz_v12`）不稳定；哈希才唯一对应一个 checkpoint 文件。但哈希也会因不同发布而分裂，必要时两个都看。

## LoRA 有三个来源，必须合并（`normalize.py` 的 `merge_loras`）

1. **提示词里的内联标签** `<lora:name:0.85>` —— WebUI 时代权重主要在这。
2. `meta.resources[]` 里 `type == "lora"` 的 `weight` —— **同一个数组里 `type == "model"` 那条是底模自己**，别混进 LoRA 列表。
3. `civitaiResources`（ComfyUI 系图）—— 只有 `modelVersionId` + `weight`，模型名要另查 `GET /api/v1/model-versions/<id>`。

`meta.resources` 的条目**没有 `modelVersionId`**（A1111 风格），且可能缺 `weight`（此时按 1.0 处理并标注）。个别老图（万张里几十个）本来就没生成参数：`meta` 键数 ≤2，留空即可，不要当抓取失败反复重试。

## 提示词归一化规则（做聚类的关键）

1. 删掉所有 `<lora:...>`（它们已被单独收集）。
2. 反复解包权重括号：`(masterpiece:1.2)` → `masterpiece`，嵌套要 while 循环到不变。
3. 去掉 `{}` `[]`。
4. **删掉 `ADDCOMM`** —— 站方插入的分隔噪音，不是作者的词。
5. 逗号切词、压缩空白、转小写。
6. 再产出一个「核心词」集合：剔除画质类停用词（`masterpiece` `best quality` `absurdres` `score_9` 等，见 `normalize.py` 的 `QUALITY`）。
7. 指纹 `core_sig = md5(sorted(核心词))[:12]` —— 只用于判「实质相同」；**比较不同方案要用模糊聚类（Jaccard≥0.85）而不是这个逐字指纹**，否则万张作者只能挖出几十个案例。

## 下载证据图

- 图片 CDN `image.civitai.com` 与 API 主机、模型 CDN（`b2.civitai.com`）**路由互相独立**：可能 API 通而图片超时，或反之。脚本要「代理优先、直连兜底」，并把图片下载与元数据抓取解耦（元数据先齐，图可后补）。
- 单图 100–400KB，瓶颈是 TLS 握手（新连接 4 秒 / 复用 0.25 秒），所以**连接复用比加线程数重要**。
- 断点续传：`.part` 写完 `os.replace` 原子改名；已存在且 >2000 字节就跳过，因此重跑只补差额。
