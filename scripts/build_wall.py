"""Build the browsable experience-library wall for one author.

Usage: python build_wall.py <author_dir> [--site https://civitai.red]
Writes <author_dir>/wall/index.html — one card per controlled-variable case, images side by
side, the swapped variable highlighted, everything else shown as held constant. Open it through
serve.py / serve_guard.py (see scripts) or any static server whose root contains this directory.
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from find_comparisons import POSE_RX

GROUP_ORDER = ['A_checkpoint', 'A_baseModel', 'A_lora_w', 'A_sampler', 'A_steps', 'A_cfgScale',
               'A_size', 'A_hires_upscale', 'A_hires_upscaler', 'A_hires_denoise',
               'A_adetailer_model', 'A_regional', 'A_clip_skip', 'A_pipeline',
               'I_pose', 'J_edit', 'A_seed']
GROUP_TITLE = {
    'A_checkpoint': '① 同一提示词 + 同一 LoRA，只换底模',
    'A_baseModel': '①b 同一提示词，跨底模谱系（SD1.5 / Pony / Illustrious …）',
    'A_lora_w': '② 同一提示词 + 同一底模 + 同采样参数，只动 LoRA（加装 / 摘掉 / 改权重）',
    'A_sampler': '③ 只换采样器',
    'A_steps': '③b 只换步数',
    'A_cfgScale': '④ 只换 CFG',
    'A_size': '⑤ 只换分辨率',
    'A_hires_upscale': '⑥a 只换 Hires 放大倍率',
    'A_hires_upscaler': '⑥b 只换 Hires 放大模型',
    'A_hires_denoise': '⑥c 只换 Hires 重绘幅度',
    'A_adetailer_model': '⑦ 只换 ADetailer 模型',
    'A_regional': '⑧ 只开关区域提示词',
    'A_clip_skip': '⑨ 只换 clip_skip',
    'A_pipeline': '⑩ 只换出图管线（A1111 / ComfyUI）',
    'I_pose': '⑪ 同一底模 + 同一 LoRA 权重 + 同采样参数，只换姿势词',
    'J_edit': '⑫ 提示词只差几个词（姿势/服装/镜头的最小改动）',
    'A_seed': '⑬ 全参数相同只换种子（模型方差，不是有效对比，留作参照）'}
NOTE = {
    'A_checkpoint': '看同一个姿势词在不同底模上谁更能听懂、谁画崩',
    'A_lora_w': '看他加/减哪个 LoRA、权重从多少调到多少，画面上到底有没有变化',
    'I_pose': '画风完全固定，只有姿势提示词在变——这是姿势词效果最干净的一批证据',
    'J_edit': '只差 1-3 个词，用来验证某个姿势词到底管不管用',
    'A_seed': '同参数不同种子只能看稳定性，不能用来比较方案'}


def esc(x):
    return (str(x) if x is not None else '').replace('&', '&amp;').replace('<', '&lt;') \
        .replace('>', '&gt;').replace('"', '&quot;')


def im_val(axis, im):
    if axis == 'pose_words':
        return ' '.join(sorted(set(POSE_RX.findall((im['prompt'] or '').lower())))) or '(无姿势词)'
    if axis == 'prompt':
        return ' '.join((im['prompt'] or '').split())[:90]
    if axis in ('hires_upscale', 'hires_upscaler', 'hires_denoise', 'regional'):
        return im['hires'] or '(不用 Hires)'
    return str(im.get({'checkpoint': 'checkpoint', 'lora_w': 'lora_w', 'sampler': 'sampler',
                       'steps': 'steps', 'cfgScale': 'cfgScale', 'size': 'size', 'seed': 'seed',
                       'baseModel': 'baseModel', 'pipeline': 'size', 'clip_skip': 'clip_skip',
                       'adetailer_model': 'adetailer'}.get(axis, 'checkpoint'), ''))


def shortname(s, n=46):
    s = (s or '').strip()
    return s if len(s) <= n else s[:n - 1] + '…'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir')
    ap.add_argument('--site', default='https://civitai.red', help='author host, used for per-image links')
    args = ap.parse_args()
    d, SITE = args.dir.rstrip('\\/'), args.site
    cases = [json.loads(l) for l in open(os.path.join(d, 'cases_selected.jsonl'), encoding='utf-8')]
    prof = json.load(open(os.path.join(d, 'profile.json'), encoding='utf-8'))
    wall = os.path.join(d, 'wall')
    os.makedirs(wall, exist_ok=True)
    have = set()
    for f in (os.listdir(os.path.join(d, 'img')) if os.path.isdir(os.path.join(d, 'img')) else []):
        if f.endswith('.jpg'):
            have.add(f[:-4])
    n_img = sum(1 for c in cases for im in c['imgs'] if str(im['id']) in have)

    H = ['<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">',
         '<title>作者经验库 · %s · 控制变量对比墙</title><style>' % esc(os.path.basename(d.rstrip('\/'))),
         'body{background:#101216;color:#dfe3e8;font-family:"Microsoft YaHei",sans-serif;margin:16px}',
         'h1{font-size:20px;margin:0 0 4px}',
         '.sub{color:#8b949e;font-size:12px;margin-bottom:10px}',
         '.bar{position:sticky;top:0;background:#101216;padding:9px 0;border-bottom:1px solid #262b32;z-index:20;font-size:13px}',
         'input{width:420px;padding:6px 9px;border-radius:6px;border:1px solid #345;background:#181c22;color:#eee;font-size:13px}',
         'h2{font-size:15px;color:#7fd1ff;border-bottom:1px solid #262b32;padding:4px 0;position:sticky;top:56px;background:#101216;z-index:15;margin:20px 0 8px}',
         'h2 small{color:#8b949e;font-weight:400;font-size:11px}',
         '.case{background:#161a20;border:1px solid #232830;border-left:3px solid #2f81f7;border-radius:8px;padding:8px 10px;margin:0 0 10px}',
         '.ch{font-size:12px;color:#9ce0b0;margin-bottom:6px;word-break:break-all}',
         '.ch b{color:#ffd479}',
         '.row{display:flex;flex-wrap:wrap;gap:8px}',
         '.cell{width:196px;background:#1b2027;border:1px solid #2a3038;border-radius:6px;padding:5px;font-size:11px;line-height:1.4}',
         '.cell img{width:100%;height:230px;object-fit:cover;border-radius:4px;display:block;cursor:zoom-in}',
         '.v{color:#ff9d9d;font-weight:700;margin:3px 0;word-break:break-all}',
         '.kv{color:#8b949e}.kv i{color:#c9d1d9;font-style:normal}',
         'a{color:#7fd1ff;text-decoration:none}',
         '.miss{opacity:.45}',
         'table{border-collapse:collapse;font-size:12px;margin:6px 0}',
         'td,th{border:1px solid #262b32;padding:3px 7px;text-align:left}',
         'th{background:#181c22;color:#7fd1ff}',
         '.tag{display:inline-block;background:#1f2937;border-radius:4px;padding:1px 6px;font-size:11px;color:#9ce0b0;margin-right:6px}',
         '#stat{color:#9ce0b0}</style></head><body>']

    H.append('<h1>作者经验库 · %s · 控制变量对比墙</h1>' % esc(os.path.basename(d.rstrip('\\/'))))
    H.append('<div class="sub">%s → %s · 共 %s 张图（带参数 %s）· 选出 %d 个单变量对比案例 %d 张证据图（本地已下 %d）'
             '· 顶栏 <span style="color:#ff9d9d">红字</span> 是被换掉的那个变量，灰字是保持相同的量'
             ' · 点图开原图，[源数据] 是这张图发布的完整生成参数</div>' % (
                 esc(prof['first']), esc(prof['last']), prof['total'], prof['with_prompt'],
                 len(cases), sum(len(c['imgs']) for c in cases), n_img))

    H.append('<div class="bar">📊 常用底模 Top：%s</div>' % ' · '.join(
        '<span class="tag">%s ×%d</span>' % (esc(shortname(c['checkpoint'], 30)), c['n'])
        for c in prof['top_checkpoints'][:8]))
    H.append('<div class="bar">过滤 <input id="q" placeholder="底模名 / LoRA名 / 姿势词 / 案例号，例如 hassaku 或 missionary"> '
             '<b id="stat">%d</b> 个案例</div>' % len(cases))

    # author profile tables
    H.append('<h2>作者画像 · 他最常落的几个模型</h2><table><tr><th>#</th><th>checkpoint</th>'
             '<th>张数</th><th>谱系</th><th>首用</th><th>末用</th><th>均赞</th><th>常配 LoRA</th></tr>')
    for i, c in enumerate(prof['top_checkpoints'][:20], 1):
        H.append('<tr><td>%d</td><td>%s</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                 '<td>%s</td></tr>' % (i, esc(shortname(c['checkpoint'], 44)), c['n'], esc(c['baseModel']),
                 c['first'], c['last'], c['avg_likes'],
                 esc(', '.join(shortname(x, 20) for x in c['top_loras']))))
    H.append('</table>')
    H.append('<div class="sub">LoRA 用途：%s</div>' % ' | '.join(
        '<b>%s</b> 共 %d 个 / 挂图 %d 次（%s）' % (k, prof.get('lora_kind_counts', {}).get(k, len(v)),
                                            prof.get('lora_kind_usage', {}).get(k, 0),
                                            esc(', '.join('%s×%d' % (shortname(n, 22), c) for n, c in v[:6])))
        for k, v in sorted(prof['lora_by_kind'].items(), key=lambda x: -sum(c for _, c in x[1]))))
    f = prof['flags']
    H.append('<div class="sub">管线开关使用量：Hires %d · ADetailer %d · 区域提示词 %d · 挂 LoRA %d / %d</div>'
             % (f['hires_on'], f['adetailer_on'], f['regional_on'], f['with_lora'], prof['with_prompt']))

    if prof.get('family_recipe'):
        H.append('<h2>每个谱系他落成的默认配方 <small>· 这套数字是他上千张图收敛出来的，可以直接当起点</small></h2>'
                 '<table><tr><th>谱系</th><th>张数</th><th>分辨率</th><th>步数</th><th>CFG</th>'
                 '<th>采样器</th><th>clip_skip</th></tr>')
        for b, v in prof['family_recipe'].items():
            H.append('<tr><td>%s</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                     % (esc(b), v['n'], esc(', '.join(v['size'])), esc(', '.join(v['steps'])),
                        esc(', '.join(v['cfg'])), esc(', '.join(v['sampler'])), esc(', '.join(v['clip_skip']))))
        H.append('</table>')
    if prof.get('lora_weight_profile'):
        H.append('<h2>LoRA 权重按用途 <small>· 他实际压的数（四分位 + 常用值），省掉自己扫权重</small></h2><table>'
                 '<tr><th>用途</th><th>样本</th><th>0.25 分位</th><th>中位</th><th>0.75 分位</th><th>常用值</th></tr>')
        for k, v in sorted(prof['lora_weight_profile'].items(), key=lambda x: -x[1]['n']):
            H.append('<tr><td>%s</td><td>%d</td><td>%g</td><td><b>%g</b></td><td>%g</td><td>%s</td></tr>'
                     % (esc(k), v['n'], v['p25'], v['median'], v['p75'], esc(', '.join(v['common']))))
        H.append('</table>')
    bd = prof.get('breadth')
    if bd:
        H.append('<h2>试模广度与姿势控制习惯</h2><div class="sub">'
                 '试过 %s 个 checkpoint / %s 个不同 LoRA；Top5 底模占 %s%%、Top20 占 %s%%，只用过一次的仅 %s 个 '
                 '· 每张图挂 LoRA 中位 %s 个（分布 %s） '
                 '· 挂了姿势 LoRA 的 %s 张里有 %s 张（%.0f%%）同时把姿势写进提示词 → 他是「LoRA + 词」双保险，不是只靠 LoRA'
                 '</div>' % (bd['checkpoints'], bd['loras'], bd['top5_share'], bd['top20_share'],
                             bd['used_once'], bd['lora_per_image_median'],
                             esc(json.dumps(bd['lora_per_image'])), bd['pose_lora_images'],
                             bd['pose_lora_and_word'],
                             100.0 * bd['pose_lora_and_word'] / max(1, bd['pose_lora_images'])))

    by_kind = collections.defaultdict(list)
    for c in cases:
        by_kind[c['kind']].append(c)

    for kind in GROUP_ORDER + sorted(set(by_kind) - set(GROUP_ORDER)):
        sub = by_kind.get(kind)
        if not sub:
            continue
        H.append('<h2>%s <small>· %d 个案例 · %s</small></h2>' % (esc(GROUP_TITLE.get(kind, kind)),
                 len(sub), esc(NOTE.get(kind, ''))))
        for c in sorted(sub, key=lambda x: (x['created'][0] if x['created'] else '', x['case'])):
            held = c.get('held') or {}
            held_txt = ' · '.join('%s=<i>%s</i>' % (esc(k), esc(shortname(v, 34))) for k, v in list(held.items())[:6])
            search = ' '.join([c['case'], str(c['values']), c['checkpoint'], c['lora_w'],
                               c['prompt_head'], ' '.join(im['prompt'] for im in c['imgs'])])
            H.append('<div class="case" data-s="%s"><div class="ch"><b>%s</b> %s ｜ 变的量：<span style="color:#ff9d9d">%s</span>'
                     ' ｜ <span style="color:#8b949e">相同：%s</span>%s</div><div class="row">' % (
                         esc(search[:900]), esc(c['case']), esc(c['held_note']),
                         esc(c['axis_label']), held_txt,
                         ' ｜ 种子也不同' if c.get('seed_varies') else ''))
            for im in c['imgs']:
                val = im_val(c['axis'], im)
                got = str(im['id']) in have
                th = '../thumbs/%s.jpg' % im['id']
                og = '../img/%s.jpg' % im['id']
                H.append('<div class="cell%s"><a href="%s" target="_blank"><img loading="lazy" src="%s"></a>'
                         '<div class="v">%s</div>'
                         '<div class="kv">底模 <i>%s</i><br>LoRA <i>%s</i><br>'
                         '%s·%s·CFG<i>%s</i> <i>%s</i><br>seed <i>%s</i> 赞 <i>%s</i> %s</div>'
                         '<div class="kv">%s</div></div>' % (
                             ' miss' if not got else '', og, th if got else og,
                             esc(shortname(val, 60)), esc(shortname(im['checkpoint'], 34)),
                             esc(shortname(im['lora_w'], 58) or '—'),
                             esc(im['sampler']), esc(im['steps']), esc(im['cfgScale']), esc(im['size']),
                             esc(im['seed']), esc(im['likes']),
                             'Hires <i>%s</i>' % esc(im['hires']) if 'None' not in im['hires'].replace(' ', '') else '',
                             '<a href="../meta/%s.json" target="_blank">源数据</a> · <a href="%s/images/%s" target="_blank">原帖</a>' % (im['id'], SITE, im['id'])))
            H.append('</div></div>')
    H.append('<script>const q=document.getElementById("q");q.oninput=()=>{const v=q.value.toLowerCase().trim();'
             'let n=0;document.querySelectorAll(".case").forEach(c=>{const ok=!v||c.dataset.s.toLowerCase().includes(v);'
             'c.style.display=ok?"":"none";if(ok)n++;});document.getElementById("stat").textContent=n;};</script>')
    H.append('</body></html>')
    out = os.path.join(wall, 'index.html')
    open(out, 'w', encoding='utf-8').write('\n'.join(H))
    print('cases=%d images(local)=%d -> %s (%.1f KB)' % (len(cases), n_img, out, os.path.getsize(out) / 1024))


if __name__ == '__main__':
    main()
