"""Find single-variable comparison groups inside one author's image set.

Usage: python find_comparisons.py <author_dir> [--thresh 0.85]

Prompts are clustered fuzzily (the author rarely repeats a prompt verbatim), then inside each
cluster every group that differs in EXACTLY ONE generation axis is emitted as one case.
Kinds:
  A_<axis>    one generation axis swaps (checkpoint, LoRA, sampler, steps, CFG, size, hires, ...)
  I_pose      same checkpoint + same LoRA set, different pose words
  J_edit      prompts differ by a few tokens, same checkpoint
Writes comparisons.jsonl + comparison_summary.txt.
"""
import argparse
import collections
import itertools
import json
import os
import re

AXES = ['checkpoint', 'baseModel', 'lora_w', 'sampler', 'steps', 'cfgScale', 'size',
        'hires_upscale', 'hires_upscaler', 'hires_denoise', 'adetailer_model', 'regional',
        'clip_skip', 'pipeline', 'seed']
LABEL = {'checkpoint': '底模 checkpoint', 'baseModel': '底模谱系 baseModel',
         'lora_w': 'LoRA 组合+权重', 'sampler': '采样器', 'steps': '步数', 'cfgScale': 'CFG',
         'size': '分辨率', 'hires_upscale': 'Hires 放大倍率', 'hires_upscaler': 'Hires 放大模型',
         'hires_denoise': 'Hires 重绘幅度', 'adetailer_model': 'ADetailer 模型',
         'regional': '区域提示词(RP)', 'clip_skip': 'clip_skip', 'pipeline': '出图管线',
         'seed': '种子 seed'}
POSE_RX = re.compile(r'\b(standing|sitting|kneeling|lying|reclining|squatting|crouching|bent over|'
                     r'leaning forward|on all fours|all fours|straddling|riding|cowgirl|missionary|'
                     r'doggy|spooning|mating press|face sitting|on the bed|on the floor|on the couch|'
                     r'on my back|from behind|from side|from above|from below|view from above|'
                     r'view from below|view from side|view from front|pov|looking at viewer|'
                     r'looking back|looking up|looking down|upper body|full body|close-up|portrait|'
                     r'cowboy shot|dutch angle|spread legs|legs up|arched back|pushed up|holding|'
                     r'grabbing|pinning|tying|bound)')


def jaccard(a, b):
    return len(a & b) / max(1, len(a | b))


class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def rare_pairs(ordered_keys, max_block=120):
    """Blocking: candidate pairs from the 3 rarest prompt tokens of each row."""
    blocks = collections.defaultdict(list)
    for i, ks in enumerate(ordered_keys):
        for pair in itertools.combinations(ks[:3], 2):
            blocks[pair].append(i)
        if len(ks) == 1:
            blocks[(ks[0], ks[0])].append(i)
    return {k: v for k, v in blocks.items() if 1 < len(v) <= max_block}


def cluster(rows, thresh):
    tok = [frozenset(r['core_tokens']) for r in rows]
    freq = collections.Counter(t for s in tok for t in s)
    ordered = [sorted(s, key=lambda t: (freq[t], t)) for s in tok]
    dsu = DSU(len(rows))
    for _, idxs in rare_pairs(ordered).items():
        for i, j in itertools.combinations(idxs, 2):
            if tok[i] != tok[j] and jaccard(tok[i], tok[j]) >= thresh:
                dsu.union(i, j)
    groups = collections.defaultdict(list)
    for i, s in enumerate(tok):
        if s:
            groups[dsu.find(i)].append(rows[i])
    return {k: v for k, v in groups.items() if len(v) >= 2}


def hold_key(r, skip, free=('seed',)):
    """Fingerprint of every axis that must stay constant; `seed` is free because the author
    re-rolls it on every image, so it can never be a held variable."""
    return json.dumps({a: str(r.get(a)) for a in AXES if a != skip and a not in free}, sort_keys=True)


def spread(g, axis, limit):
    """One exemplar image per distinct value of `axis` inside group g."""
    vals = sorted({str(r.get(axis)) for r in g},
                  key=lambda v: -sum(1 for r in g if str(r.get(axis)) == v))
    pick, seen = [], set()
    for v in vals:
        it = next(r for r in g if str(r.get(axis)) == v)
        if it['id'] not in seen:
            pick.append(it)
            seen.add(it['id'])
    return pick[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir')
    ap.add_argument('--thresh', type=float, default=0.85)
    ap.add_argument('--max-j', type=int, default=300)
    a = ap.parse_args()
    d = a.dir
    rows = [json.loads(l) for l in open(os.path.join(d, 'images.jsonl'), encoding='utf-8')
            if json.loads(l)['prompt']]
    print('rows=%d' % len(rows), flush=True)
    clusters = cluster(rows, a.thresh)
    print('clusters>=2: %d covering %d images' % (len(clusters), sum(len(v) for v in clusters.values())), flush=True)

    cases = []

    def add(kind, axis, items, note='', values=None, label=None):
        vals = values if values is not None else ([str(i.get(axis)) for i in items] if axis else [str(i['id']) for i in items])
        if len(set(map(str, vals))) < 2:
            return
        cases.append({'case': '%s-%03d' % (kind, len(cases) + 1), 'kind': kind, 'axis': axis,
                      'axis_label': label or LABEL.get(axis, '提示词差异'),
                      'values': vals, 'n': len(vals),
                      'held': {k: str(items[0].get(k)) for k in AXES
                               if k != axis and k != 'seed' and str(items[0].get(k)) not in ('None', '')},
                      'seed_varies': len({str(i['seed']) for i in items}) > 1,
                      'held_note': note, 'ids': [i['id'] for i in items],
                      'created': sorted({i['created'] for i in items}),
                      'checkpoint': items[0]['checkpoint'], 'lora_w': items[0]['lora_w'],
                      'prompt_head': items[0]['prompt'][:220].replace('\n', ' ')})

    # --- A: one generation axis swapped inside a prompt cluster ---
    for cid, members in sorted(clusters.items(), key=lambda x: -len(x[1])):
        for axis in AXES:
            if axis == 'seed':
                continue
            buckets = collections.defaultdict(list)
            for r in members:
                buckets[hold_key(r, axis)].append(r)
            for _, g in buckets.items():
                if len({str(r.get(axis)) for r in g}) >= 2:
                    pick = spread(g, axis, 5)
                    if len(pick) >= 2:
                        add('A_' + axis, axis, pick,
                            note='提示词簇 %d（%d 张）内只换这一项' % (cid, len(members)))

    # --- A_seed: full-parameter repeats, only the seed moved ---
    buckets = collections.defaultdict(list)
    for r in rows:
        buckets[hold_key(r, 'seed')].append(r)
    for _, g in buckets.items():
        if len({r['core_sig'] for r in g}) == 1 and len({str(r['seed']) for r in g}) >= 2:
            pick = spread(g, 'seed', 4)
            if len(pick) >= 2:
                add('A_seed', 'seed', pick, note='全参数相同只换种子：看这个模型的方差，不是有效对比')

    # --- I: same checkpoint + same LoRA weights + same sampler/steps/CFG, different pose words ---
    bystyle = collections.defaultdict(dict)
    for r in rows:
        pw = tuple(sorted(set(POSE_RX.findall((r['prompt'] or '').lower()))))
        if pw:
            style = ((r['ckpt_hash'] or r['checkpoint']).lower(), r['lora_w'],
                     r['sampler'], str(r['steps']), str(r['cfgScale']))
            bystyle[style].setdefault(pw, r)
    for style, first in sorted(bystyle.items(), key=lambda x: -len(x[1])):
        if len(first) >= 3:
            items = sorted(first.values(), key=lambda r: r['id'])[:6]
            add('I_pose', 'pose_words', items,
                note='同一底模 %s + 同一 LoRA 权重 + 同采样参数，只换姿势词' % (style[0] or '同底模'),
                values=['|'.join(sorted(set(POSE_RX.findall((i['prompt'] or '').lower())))) for i in items],
                label='姿势提示词')

    # --- J: smallest prompt edits, everything else held (ckpt/LoRA weights/sampler/steps/CFG/size) ---
    tok = {r['id']: frozenset(r['core_tokens']) for r in rows}
    freq = collections.Counter(t for r in rows for t in r['core_tokens'])
    blocks = collections.defaultdict(list)
    for i, r in enumerate(rows):
        held = ((r['ckpt_hash'] or r['checkpoint']).lower(), r['lora_w'], r['sampler'],
                str(r['steps']), str(r['cfgScale']), str(r['size']))
        ordered = sorted(r['core_tokens'], key=lambda t: (freq[t], t))
        for pair in itertools.combinations(ordered[:3], 2):
            blocks[held + (pair,)].append(i)
    near = []
    for _, idxs in blocks.items():
        for i, j in itertools.combinations(idxs, 2):
            x, y = rows[i], rows[j]
            if x['core_sig'] != y['core_sig']:
                v = jaccard(tok[x['id']], tok[y['id']])
                if v >= 0.72:
                    near.append((v, len(tok[x['id']] ^ tok[y['id']]), x, y))
    near.sort(key=lambda t: (-t[0], t[1]))
    used = set()
    for v, n, x, y in near:
        if x['id'] in used or y['id'] in used:
            continue
        used.update((x['id'], y['id']))
        add('J_edit', 'prompt', [x, y],
            note='提示词只差 %d 个词（相似度 %.2f）：%s' % (n, v, sorted(tok[x['id']] ^ tok[y['id']])),
            values=[x['prompt'][:220].replace('\n', ' '), y['prompt'][:220].replace('\n', ' ')])
        if len(used) >= a.max_j:
            break

    with open(os.path.join(d, 'comparisons.jsonl'), 'w', encoding='utf-8') as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')
    lines = ['rows=%d clusters=%d cases=%d' % (len(rows), len(clusters), len(cases))]
    for k, n in sorted(collections.Counter(c['kind'] for c in cases).items()):
        sub = [c for c in cases if c['kind'] == k]
        lines.append('%-22s %3d  sizes=%s' % (k, n, dict(sorted(collections.Counter(c['n'] for c in sub).items()))))
        for c in sorted(sub, key=lambda x: -x['n'])[:2]:
            lines.append('    %s n=%d ids=%s vals=%s' % (c['case'], c['n'], c['ids'],
                         json.dumps(c['values'], ensure_ascii=False)[:240]))
    txt = '\n'.join(lines)
    open(os.path.join(d, 'comparison_summary.txt'), 'w', encoding='utf-8').write(txt + '\n')
    print(txt)


if __name__ == '__main__':
    main()
