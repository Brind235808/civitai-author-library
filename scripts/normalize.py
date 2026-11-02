"""Normalize scraped Civitai image pages into one row per image.

Usage: python normalize.py <author_dir>
Reads <author_dir>/raw/pages/*.json -> writes <author_dir>/images.jsonl + images.csv
"""
import csv
import glob
import hashlib
import json
import os
import re
import sys

LORA_RX = re.compile(r'<lora:([^:>]+)(?::(-?\d+(?:\.\d+)?))?>', re.I)
WEIGHT_RX = re.compile(r'\(([^()]+?)(?::\s*[\d.]+)?\)')
QUALITY = set('''masterpiece best quality extremely detailed ultra detailed high quality highres
absurdres very aesthetic amazing quality newest official art 8k 4k raw photo photorealistic
professional detailedcgc highly detailed ultra-detailed absurdest quality worst quality lowres
normal quality jpeg artifacts cropped blurry bad anatomy extra arms extra legs watermark signed
detailed score_9 score_8_up score_7_up score_6_up score_5_up score_4_up source_anime
source_film source_game source_comic generic latest nice amazing awful worst rating_safe
rating_questionable rating_explicit'''.split())


def clean_prompt(text):
    """Return (tokens, inline_loras) with weight syntax and inline <lora:> tags removed."""
    text = text or ''
    inline = [(m.group(1), m.group(2) or '1.0') for m in LORA_RX.finditer(text)]
    text = LORA_RX.sub(' ', text)
    prev = None
    while prev != text:
        prev = text
        text = WEIGHT_RX.sub(r'\1', text)
    text = re.sub(r'[{}\[\]]', '', text).replace('ADDCOMM', ' ')
    toks = [re.sub(r'\s+', ' ', t).strip().lower() for t in text.split(',')]
    return [t for t in toks if t], inline


def sig(vals):
    return hashlib.md5('|'.join(sorted(set(vals))).encode()).hexdigest()[:12]


def merge_loras(meta, item):
    """name -> weight, from inline prompt tags, A1111 `resources`, then ComfyUI `civitaiResources`."""
    out = {}
    for name, w in clean_prompt(meta.get('prompt'))[1]:
        out[name.lower()] = float(w)
    for r in (meta.get('resources') or []):
        if (r.get('type') or '').lower() == 'lora' and r.get('name'):
            out.setdefault(r['name'].lower(), r.get('weight'))
    cr = item.get('civitaiResources')
    if isinstance(cr, dict):
        for k, v in cr.items():
            v = v or {}
            if (v.get('type') or 'lora').lower() == 'lora':
                name = (v.get('modelName') or '').lower()
                if name:
                    out.setdefault(name, v.get('weight'))
    return out


def row(item):
    meta = item.get('meta') or {}
    toks, _ = clean_prompt(meta.get('prompt'))
    neg, _ = clean_prompt(meta.get('negativePrompt'))
    loras = merge_loras(meta, item)
    core = sorted(set(t for t in toks if t not in QUALITY))
    res = meta.get('resources') or []
    ckpt_res = [r.get('name') for r in res if (r.get('type') or '').lower() == 'model']
    lora_w = ';'.join('%s=%s' % (n, ('%g' % w) if isinstance(w, (int, float)) else w)
                      for n, w in sorted(loras.items()))
    return {
        'id': item.get('id'),
        'created': (item.get('createdAt') or '')[:10],
        'month': (item.get('createdAt') or '')[:7],
        'url': item.get('url') or '',
        'thumb': item.get('thumbnail') or '',
        'width': item.get('width'), 'height': item.get('height'),
        'nsfwLevel': item.get('nsfwLevel'), 'baseModel': item.get('baseModel') or '',
        'type': item.get('type') or 'image',
        'post_id': item.get('postId'),
        'checkpoint': (meta.get('Model') or (ckpt_res[0] if ckpt_res else '') or '').strip(),
        'ckpt_hash': (meta.get('Model hash') or '').strip(),
        'loras': sorted(loras),
        'lora_w': lora_w,
        'prompt': meta.get('prompt') or '',
        'negative': meta.get('negativePrompt') or '',
        'tokens': toks, 'core_tokens': core,
        'core_sig': sig(core),
        'steps': meta.get('steps'), 'cfgScale': meta.get('cfgScale'),
        'sampler': meta.get('sampler') or meta.get('samplingMethod') or '',
        'seed': meta.get('seed'),
        'size': meta.get('Size') or ('%sx%s' % (item.get('width'), item.get('height'))),
        'clip_skip': meta.get('clipSkip'),
        'hires_upscale': meta.get('Hires upscale'), 'hires_upscaler': meta.get('Hires upscaler'),
        'hires_denoise': meta.get('Denoising strength'),
        'adetailer_model': meta.get('ADetailer model'),
        'adetailer_denoise': meta.get('ADetailer denoising strength'),
        'adetailer_confidence': meta.get('ADetailer confidence'),
        'regional': bool(meta.get('RP Active')) or ('RP Ratios' in meta),
        'pipeline': 'A1111' if meta.get('Model hash') else ('ComfyUI' if item.get('civitaiResources') else 'unknown'),
        'extra_keys': sorted(k for k in meta if k not in
                             ('seed', 'prompt', 'negativePrompt', 'steps', 'cfgScale', 'sampler',
                              'Model', 'Model hash', 'hashes', 'Version', 'resources', 'Size',
                              'Denoising strength', 'Hires upscale', 'Hires upscaler')),
        'n_meta_keys': len(meta),
        'likes': (item.get('stats') or {}).get('heartCount'),
    }


def main():
    d = sys.argv[1]
    pages = sorted(glob.glob(os.path.join(d, 'raw', 'pages', 'page_*.json')))
    seen, rows = set(), []
    for p in pages:
        try:
            data = json.load(open(p, encoding='utf-8'))
        except Exception as e:
            print('BAD PAGE', p, e, flush=True)
            continue
        for it in data.get('items') or []:
            if it.get('id') in seen:
                continue
            seen.add(it['id'])
            rows.append(row(it))
    rows.sort(key=lambda r: (r['created'], r['id']))
    with open(os.path.join(d, 'images.jsonl'), 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    cols = ['id', 'created', 'checkpoint', 'ckpt_hash', 'baseModel', 'pipeline', 'sampler', 'steps',
            'cfgScale', 'seed', 'size', 'hires_upscale', 'hires_upscaler', 'hires_denoise',
            'adetailer_model', 'regional', 'clip_skip', 'core_sig', 'n_loras', 'lora_w', 'likes',
            'prompt']
    with open(os.path.join(d, 'images.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            r2 = dict(r)
            r2['n_loras'] = len(r['loras'])
            w.writerow([r2.get(c) for c in cols])
    have = sum(1 for r in rows if r['n_meta_keys'] > 2)
    print('pages=%d rows=%d with_meta=%d (%.1f%%)' % (len(pages), len(rows), have,
                                                      100.0 * have / max(1, len(rows))))


if __name__ == '__main__':
    main()
