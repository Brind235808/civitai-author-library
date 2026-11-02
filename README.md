# civitai-author-library

一个 [Qoder](https://qoder.com) agent skill：把某位 Civitai 作者的全站作品（上万张图的生成参数）变成一个**控制变量对比经验库**——只下载能做对比的证据图，配一个可浏览的对比墙和编号交接分册。

目的很实际：**别人已经跑过一万次，你不必再用自己的显卡重跑。**

## 它会产出什么

| 产出 | 内容 |
|---|---|
| `images.jsonl` | 该作者每张图的完整参数（底模哈希、LoRA+权重、采样器、步数、CFG、分辨率、hires、ADetailer、seed、提示词） |
| `comparisons.jsonl` | 单变量对比案例：只换底模 / 只加或减一个 LoRA / 只改权重 / 只换采样器 / 只换分辨率 / 只换重绘幅度 / 同风格换姿势词 / 提示词只差一两个词 |
| `profile.json` `profile.md` | 作者画像：常用底模 Top、**每个谱系的默认参数配方**、**LoRA 权重按用途的四分位**、试模广度、按年代的工作流变化 |
| `wall/index.html` | 对比墙：一个案例一张卡，图片并排，被换掉的变量标红，保持不变的量列在旁边，每张图链到本地源参数 |
| `00_INDEX.md` + `01`–`04` | 编号分册交接：新会话只读索引即可接手 |

实测一位 10,873 张图的作者：抓取约 90 秒，找到 1,424 个单变量案例，选出 510 例上图墙，下载 1,436 张证据图约 500MB / 8 分钟，0 失败。

## 安装

把仓库整个目录放到用户级 skills 下，重启会话或 `/skills reload`：

```
Windows:  %USERPROFILE%\.qoder-cn\skills\civitai-author-library
macOS/Linux: ~/.qoder-cn/skills/civitai-author-library
```

调用：`/civitai-author-library <作者名>`，或直接对 agent 说「照这位作者的 C 站作品建个经验库」并给出主页链接。

## 依赖

- Python 3.9+；抓取、归一化、找对比、画像、选案例只用标准库。
- 下载证据图与生成缩略图需要 `requests` 和 `Pillow`：`pip install requests pillow`。
- 不需要 C 站 token（元数据匿名可读；本 skill 不下载模型文件）。
- 网络不通时加 `--proxy http://127.0.0.1:<port>`。

## 手动跑（agent 也是按这个顺序跑）

```bat
python scripts\scrape_author.py <作者> --out <库根>\<作者>
python scripts\normalize.py            <库根>\<作者>
python scripts\find_comparisons.py     <库根>\<作者> --thresh 0.85
python scripts\author_profile.py       <库根>\<作者>
python scripts\pick_cases.py           <库根>\<作者> --max-images 1700
python scripts\download_evidence.py    <库根>\<作者> --workers 12
python scripts\build_wall.py           <库根>\<作者>
python scripts\serve_guard.py 8899 <库根>      :: 浏览图墙
```

## 两个设计要点

- **提示词必须模糊聚类。** 量产作者几乎不逐字重复同一句提示词，按字面分组只能挖出几十例；按去权重/去 `<lora:>` 后的 token 集合做 Jaccard≥0.85 聚类才有上千例。
- **seed 不是不变量。** 这类作者每张都换种子，把它当"保持相同"会让所有换模/换 LoRA 对比归零。种子只在案例上标注，不参与分组。

结论的**时代核对**也写进了 skill：一位作者的换底模对照可能全部集中在他早已弃用的旧谱系上，方法可抄、结论不可跨谱系搬。

## 注意

- 仓库只含代码与文档，**不含任何图片或作者数据**。抓取内容取决于你选的站点与分级参数（`civitai.red` 含成人内容）。请自行遵守站点服务条款与当地法规，控制抓取与下载量。
- MIT License，见 `LICENSE`。
