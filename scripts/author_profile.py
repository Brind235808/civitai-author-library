"""Author profile: which models an author actually reaches for, and how their workflow changed.

Usage: python author_profile.py <author_dir>
Reads images.jsonl -> writes profile.json + profile.md
"""
import collections
import json
import os
import re
import sys

POSE_HINT = re.compile(r'(missionary|cowgirl|doggy|straddl|all fours|riding|lying|sitting|kneel|'
                       r'standing|squat|bent over|on the bed|on the floor|from behind|view from|'
                       r'pov|spread legs|position|pose)', re.I)

POSE_WORDS = ['pose', 'position', 'missionary', 'cowgirl', 'doggy', 'rider', 'riding', 'straddle',
              'oral', 'fellatio', 'cunnilingus', 'creampie', 'bukkake', 'cumshot', 'cum', 'spitrode',
              'masturbat', 'hump', 'titfuck', 'paizuri', 'anal', 'blowjob', 'handjob', 'footjob',
              'titsjob', 'shibari', 'bound', 'lotus', 'amazon', 'deepthroat', 'gokkun', 'squat',
              'kneel', 'lying', 'onback', 'on_back', 'pin', 'spread', 'wheelbarrow', 'instant',
              'press', 'mount', 'lap', 'sitting', 'standing', 'sex', 'fuck', 'npc', 'midis',
              'torso', 'ntrface', 'upskirt', 'present', 'grab', 'hold', 'pov', '69', 'doggystyle',
              'reverse', 'frontal', 'frombehind', 'onbed', 'humping', 'facesitting', 'legs']
DETAIL_WORDS = ['detail', 'incrs', 'sharpen', 'more_details', 'xl_more', 'enhance', 'slider']
STYLE_WORDS = ['style', 'mix', 'ilxl', 'illu', 'pony', 'noob', 'dark', 'light', 'brush', 'thicc',
               'blush', 'bruise', 'lowlight', 'thick', 'glow', 'render', 'anime', 'realistic',
               'pencil', 'marker', 'cel', 'liner', 'coloring', 'lighting', 'shadow']


def lora_kind(name):
    n = name.lower()
    if any(w in n for w in DETAIL_WORDS):
        return '细节增强'
    if any(w in n for w in POSE_WORDS):
        return '姿势/动作'
    if any(w in n for w in STYLE_WORDS):
        return '画风'
    return '角色/其他'


def pct(part, whole):
    return '%.1f%%' % (100.0 * part / max(1, whole))


def dist(rows, field, top=12):
    c = collections.Counter(str(r.get(field)) for r in rows)
    return c.most_common(top)


def family_recipe(rows):
    """Per base-model family: the resolution/steps/CFG he settles on."""
    out = {}
    for b in ['SD 1.5', 'SD 1.4', 'Other', 'Pony', 'SDXL', 'Illustrious', 'NoobAI', 'Anima']:
        g = [r for r in rows if r['baseModel'] == b]
        if len(g) < 20:
            continue
        out[b] = {'n': len(g),
                  'size': [a for a, _ in collections.Counter(r['size'] for r in g).most_common(3)],
                  'steps': [a for a, _ in collections.Counter(str(r['steps']) for r in g).most_common(3)],
                  'cfg': [a for a, _ in collections.Counter(str(r['cfgScale']) for r in g).most_common(3)],
                  'sampler': [a for a, _ in collections.Counter(r['sampler'] for r in g).most_common(3)],
                  'clip_skip': [a for a, _ in collections.Counter(str(r['clip_skip']) for r in g).most_common(2)]}
    return out


def lora_weight_profile(rows):
    """What weight he uses per LoRA role — the number that normally costs a test batch to find."""
    vals = collections.defaultdict(list)
    for r in rows:
        for part in (r['lora_w'] or '').split(';'):
            if '=' in part:
                name, w = part.rsplit('=', 1)
                try:
                    vals[lora_kind(name)].append(float(w))
                except ValueError:
                    pass
    out = {}
    for kind, v in vals.items():
        v = sorted(v)
        q = lambda p: v[int(p * (len(v) - 1))]
        out[kind] = {'n': len(v), 'p25': q(.25), 'median': q(.5), 'p75': q(.75),
                     'common': [a for a, _ in collections.Counter('%g' % x for x in v).most_common(5)]}
    return out


def main():
    d = sys.argv[1]
    rows = [json.loads(l) for l in open(os.path.join(d, 'images.jsonl'), encoding='utf-8')]
    withp = [r for r in rows if r['prompt']]
    years = collections.Counter(r['created'][:4] for r in rows)
    months = sorted({r['month'] for r in rows if r['month']})

    ck = collections.defaultdict(list)
    for r in withp:
        if r['checkpoint']:
            ck[r['checkpoint']].append(r)
    ck_rows = []
    for name, g in ck.items():
        ck_rows.append({'checkpoint': name, 'n': len(g),
                        'baseModel': collections.Counter(x['baseModel'] for x in g).most_common(1)[0][0],
                        'first': min(x['created'] for x in g), 'last': max(x['created'] for x in g),
                        'avg_likes': round(sum(x['likes'] or 0 for x in g) / len(g), 1),
                        'top_loras': [k for k, _ in collections.Counter(
                            l for x in g for l in x['loras']).most_common(3)],
                        'samplers': [k for k, _ in collections.Counter(x['sampler'] for x in g).most_common(2)]})
    ck_rows.sort(key=lambda x: -x['n'])

    lora_n = collections.Counter(l for r in withp for l in r['loras'])
    lora_kind_map = {}
    for name in lora_n:
        lora_kind_map[name] = lora_kind(name)
    by_kind = collections.defaultdict(list)
    for name, n in lora_n.items():
        by_kind[lora_kind_map[name]].append((name, n))
    for k in by_kind:
        by_kind[k].sort(key=lambda x: -x[1])

    monthly_ck = {}
    for m in months:
        g = [r for r in withp if r['month'] == m]
        top = collections.Counter(r['checkpoint'] for r in g if r['checkpoint']).most_common(3)
        if top:
            monthly_ck[m] = {'n': len(g), 'top': top}

    trend = {}
    for f in ['sampler', 'baseModel', 'pipeline']:
        trend[f] = {}
        for m in months:
            g = [r for r in withp if r['month'] == m]
            trend[f][m] = collections.Counter(str(r.get(f)) for r in g).most_common(3)

    combos = collections.Counter()
    for r in withp:
        if r['checkpoint'] and r['loras']:
            for l in r['loras']:
                combos[(r['checkpoint'], l)] += 1

    hot = sorted(withp, key=lambda r: -(r['likes'] or 0))[:20]

    ck_all = collections.Counter(r['checkpoint'] for r in withp if r['checkpoint'])
    tot_ck = sum(ck_all.values()) or 1
    top_ck = ck_all.most_common()
    pose_lora_imgs = [r for r in withp if any(lora_kind(l) == '姿势/动作' for l in r['loras'])]
    pose_word_too = [r for r in pose_lora_imgs if POSE_HINT.search((r['prompt'] or '').lower())]
    nloras = collections.Counter(len(r['loras']) for r in withp)

    prof = {'total': len(rows), 'with_prompt': len(withp), 'years': dict(years),
            'first': min(r['created'] for r in rows), 'last': max(r['created'] for r in rows),
            'defaults': {f: (collections.Counter(str(r.get(f)) for r in withp).most_common(3))
                         for f in ['sampler', 'steps', 'cfgScale', 'size', 'hires_upscaler',
                                   'adetailer_model', 'clip_skip']},
            'family_recipe': family_recipe(withp),
            'lora_weight_profile': lora_weight_profile(withp),
            'breadth': {'checkpoints': len(ck_all), 'loras': len(lora_n),
                        'top5_share': round(100.0 * sum(c for _, c in top_ck[:5]) / tot_ck, 1),
                        'top20_share': round(100.0 * sum(c for _, c in top_ck[:20]) / tot_ck, 1),
                        'used_once': sum(1 for c in ck_all.values() if c == 1),
                        'lora_per_image_median': sorted(nloras.elements())[len(withp) // 2],
                        'lora_per_image': dict(sorted(nloras.items())),
                        'pose_lora_images': len(pose_lora_imgs),
                        'pose_lora_and_word': len(pose_word_too)},
            'top_checkpoints': ck_rows[:40],
            'lora_total_distinct': len(lora_n),
            'lora_by_kind': {k: v[:40] for k, v in by_kind.items()},
            'lora_kind_counts': {k: len(v) for k, v in by_kind.items()},
            'lora_kind_usage': {k: sum(c for _, c in v) for k, v in by_kind.items()},
            'monthly_top_checkpoint': monthly_ck,
            'param_dist': {f: dist(withp, f) for f in
                           ['sampler', 'steps', 'cfgScale', 'size', 'baseModel', 'pipeline',
                            'hires_upscaler', 'adetailer_model', 'clip_skip']},
            'flags': {'hires_on': sum(1 for r in withp if r['hires_upscaler']),
                      'adetailer_on': sum(1 for r in withp if r['adetailer_model']),
                      'regional_on': sum(1 for r in withp if r['regional']),
                      'with_lora': sum(1 for r in withp if r['loras'])},
            'top_combos': [{'checkpoint': a, 'lora': b, 'n': n} for (a, b), n in combos.most_common(30)],
            'trend': trend,
            'hot_images': [{'id': r['id'], 'likes': r['likes'], 'checkpoint': r['checkpoint'],
                            'created': r['created'], 'prompt_head': r['prompt'][:120].replace('\n', ' ')}
                           for r in hot]}
    json.dump(prof, open(os.path.join(d, 'profile.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    L = ['# 作者画像 · %s' % os.path.basename(d.rstrip('\\/')), '']
    L.append('- 图片 %d 张，带提示词 %d 张；时间跨度 %s → %s' %
             (prof['total'], prof['with_prompt'], prof['first'], prof['last']))
    L.append('- 按年：%s' % ' '.join('%s:%d' % (k, v) for k, v in sorted(years.items())))
    f = prof['flags']
    L.append('- 开过 Hires %s / ADetailer %s / 区域提示词 %s / 挂过 LoRA %s（占比 %s）' %
             (f['hires_on'], f['adetailer_on'], f['regional_on'], f['with_lora'],
              pct(f['with_lora'], prof['with_prompt'])))
    L.append('')
    L.append('## 常用底模 Top 25')
    L.append('| # | checkpoint | 张数 | 谱系 | 首用 | 末用 | 均赞 | 常配 LoRA | 采样器 |')
    L.append('|---|---|---|---|---|---|---|---|---|')
    for i, c in enumerate(ck_rows[:25], 1):
        L.append('| %d | %s | %d | %s | %s | %s | %s | %s | %s |' %
                 (i, c['checkpoint'][:52], c['n'], c['baseModel'], c['first'], c['last'],
                  c['avg_likes'], ', '.join(x[:22] for x in c['top_loras']),
                  ', '.join(x[:16] for x in c['samplers'])))
    L.append('')
    L.append('## LoRA 用途分布（共 %d 个不同 LoRA）' % prof['lora_total_distinct'])
    for kind in ['姿势/动作', '画风', '细节增强', '角色/其他']:
        lst = prof['lora_by_kind'].get(kind, [])
        L.append('### %s（共 %d 个 / 挂图 %d 次，Top 12）' %
                 (kind, prof['lora_kind_counts'].get(kind, 0), prof['lora_kind_usage'].get(kind, 0)))
        L.append('  ' + ' · '.join('%s(%d)' % (n[:30], c) for n, c in lst[:12]))
    L.append('')
    L.append('## 参数偏好')
    for k, v in prof['param_dist'].items():
        L.append('- %s：%s' % (k, ', '.join('%s=%d' % (a, b) for a, b in v[:8])))
    L.append('')
    L.append('## 每个谱系他落成的默认配方')
    L.append('| 谱系 | 张数 | 分辨率 | 步数 | CFG | 采样器 | clip_skip |')
    L.append('|---|---|---|---|---|---|---|')
    for b, v in prof['family_recipe'].items():
        L.append('| %s | %d | %s | %s | %s | %s | %s |' %
                 (b, v['n'], ', '.join(v['size']), ', '.join(v['steps']), ', '.join(v['cfg']),
                  ', '.join(v['sampler']), ', '.join(v['clip_skip'])))
    L.append('')
    L.append('## LoRA 权重按用途（他实际压的数）')
    for kind, v in sorted(prof['lora_weight_profile'].items(), key=lambda x: -x[1]['n']):
        L.append('- %s：中位 %g（四分位 %g~%g），常用 %s，样本 %d' %
                 (kind, v['median'], v['p25'], v['p75'], ', '.join(v['common']), v['n']))
    L.append('')
    b = prof['breadth']
    L.append('## 试模广度')
    L.append('- 试过 %d 个 checkpoint / %d 个不同 LoRA；Top5 底模占 %s%%，Top20 占 %s%%，只用过一次的只有 %d 个' %
             (b['checkpoints'], b['loras'], b['top5_share'], b['top20_share'], b['used_once']))
    L.append('- 每张图挂 LoRA 数：中位 %d，分布 %s' % (b['lora_per_image_median'], b['lora_per_image']))
    L.append('- 挂了姿势 LoRA 的 %d 张里，%d 张（%.0f%%）同时把姿势写进提示词 → 双保险' %
             (b['pose_lora_images'], b['pose_lora_and_word'],
              100.0 * b['pose_lora_and_word'] / max(1, b['pose_lora_images'])))
    L.append('')
    L.append('## 每月主力底模')
    for m in sorted(monthly_ck):
        L.append('- %s（%d 张）：%s' % (m, monthly_ck[m]['n'],
                   ', '.join('%s×%d' % (a[:34], b) for a, b in monthly_ck[m]['top'])))
    L.append('')
    L.append('## 高频底模 × LoRA 组合 Top 20')
    for c in prof['top_combos'][:20]:
        L.append('- %d×  %s  +  %s' % (c['n'], c['checkpoint'][:46], c['lora'][:40]))
    L.append('')
    L.append('## 点赞最高 10 张')
    for r in prof['hot_images'][:10]:
        L.append('- %s ❤%s %s (%s) %s' % (r['id'], r['likes'], r['created'], r['checkpoint'][:34], r['prompt_head'][:80]))
    open(os.path.join(d, 'profile.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L[:28]))
    print('...\nprofile.md + profile.json written to', d)


if __name__ == '__main__':
    main()
