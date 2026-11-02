"""Rank controlled-variable cases and build the download manifest.

Usage: python pick_cases.py <author_dir> [--max-images 1200]

Reads comparisons.jsonl + images.jsonl -> writes cases_selected.jsonl + download_manifest.json
Selection favours clean single-axis swaps on the Illustrious/NoobAI line (what the local rig runs)
over seed-variance repeats, and caps each kind so the wall stays browsable.
"""
import argparse
import collections
import json
import os

KIND_SCORE = {'A_checkpoint': 100, 'A_lora_w': 95, 'A_pipeline': 88, 'A_baseModel': 85,
              'A_sampler': 70, 'A_hires_denoise': 66, 'A_adetailer_model': 62,
              'A_hires_upscaler': 60, 'A_size': 58, 'A_cfgScale': 55, 'A_hires_upscale': 54,
              'A_regional': 64, 'A_clip_skip': 50, 'J_edit': 50, 'I_pose': 45, 'A_seed': 5}
KIND_CAP = {'A_checkpoint': 999, 'A_lora_w': 999, 'A_sampler': 999, 'A_baseModel': 999,
            'A_pipeline': 999, 'A_hires_denoise': 999, 'A_hires_upscaler': 999,
            'A_hires_upscale': 999, 'A_size': 999, 'A_cfgScale': 999, 'A_clip_skip': 999,
            'A_adetailer_model': 999, 'A_regional': 999, 'I_pose': 160, 'J_edit': 90, 'A_seed': 12}
HOT_BASE = {'Illustrious': 25, 'NoobAI': 22, 'SDXL': 12, 'Pony': 8, 'Anima': 10, 'SD 1.5': 0}


def score(c, byid):
    s = KIND_SCORE.get(c['kind'], 20)
    s += 8 * (c['n'] - 2)
    if len(c['created']) == 1:
        s += 12
    bases = {byid[i]['baseModel'] for i in c['ids'] if i in byid}
    s += max((HOT_BASE.get(b, 0) for b in bases), default=0)
    if max(c['created'] or ['']) >= '2025-01':
        s += 10
    likes = [byid[i]['likes'] or 0 for i in c['ids'] if i in byid]
    s += min(10, (sum(likes) / len(likes) / 40.0) if likes else 0)
    if c.get('seed_varies'):
        s -= 4
    return round(s, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir')
    ap.add_argument('--max-images', type=int, default=1200)
    a = ap.parse_args()
    d = a.dir
    rows = [json.loads(l) for l in open(os.path.join(d, 'images.jsonl'), encoding='utf-8')]
    byid = {r['id']: r for r in rows}
    cases = [json.loads(l) for l in open(os.path.join(d, 'comparisons.jsonl'), encoding='utf-8')]
    for c in cases:
        c['score'] = score(c, byid)
    cases.sort(key=lambda c: -c['score'])

    used_kinds = collections.Counter()
    picked, seen_ids = [], set()
    for c in cases:
        k = c['kind']
        if used_kinds[k] >= KIND_CAP.get(k, 30):
            continue
        fresh = [i for i in c['ids'] if i not in seen_ids]
        if len(fresh) < 2:
            continue
        if len(seen_ids) + len(fresh) > a.max_images:
            continue
        seen_ids.update(c['ids'])
        used_kinds[k] += 1
        c['imgs'] = [{'id': i, 'url': byid[i]['url'], 'thumb': byid[i]['thumb'],
                      'created': byid[i]['created'], 'checkpoint': byid[i]['checkpoint'],
                      'ckpt_hash': byid[i]['ckpt_hash'], 'baseModel': byid[i]['baseModel'],
                      'lora_w': byid[i]['lora_w'], 'sampler': byid[i]['sampler'],
                      'steps': byid[i]['steps'], 'cfgScale': byid[i]['cfgScale'],
                      'seed': byid[i]['seed'], 'size': byid[i]['size'],
                      'hires': '%s / %s / %s' % (byid[i]['hires_upscale'], byid[i]['hires_upscaler'],
                                                 byid[i]['hires_denoise']),
                      'adetailer': byid[i]['adetailer_model'], 'likes': byid[i]['likes'],
                      'prompt': byid[i]['prompt'], 'negative': byid[i]['negative']}
                     for i in c['ids'] if i in byid]
        picked.append(c)

    picked.sort(key=lambda c: (c['kind'], -c['score']))
    with open(os.path.join(d, 'cases_selected.jsonl'), 'w', encoding='utf-8') as f:
        for c in picked:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')

    manifest = {'author': os.path.basename(d.rstrip('\\/')), 'images': [], 'cases': len(picked)}
    for c in picked:
        for im in c['imgs']:
            manifest['images'].append({'id': im['id'], 'url': im['url'], 'thumb': im['thumb'],
                                       'case': c['case'], 'kind': c['kind']})
    uniq = {}
    for m in manifest['images']:
        uniq.setdefault(m['id'], m)
    manifest['images'] = sorted(uniq.values(), key=lambda m: m['id'])
    manifest['n_images'] = len(manifest['images'])
    json.dump(manifest, open(os.path.join(d, 'download_manifest.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    print('cases picked: %d | unique images: %d' % (len(picked), len(manifest['images'])))
    for k, n in sorted(used_kinds.items()):
        vals = [c['score'] for c in picked if c['kind'] == k]
        print('  %-20s %3d cases  score %s-%s' % (k, n, min(vals), max(vals)))
    print('  image ids:', len(manifest['images']))


if __name__ == '__main__':
    main()
