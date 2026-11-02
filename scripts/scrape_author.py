"""Scrape every Civitai image (with generation metadata) for one author.

Usage: python scrape_author.py <username> --out DIR [--page-size 100] [--max-pages N]
              [--site https://civitai.red] [--nsfw X] [--proxy http://127.0.0.1:1080]

Writes raw/pages/page_NNNN.json (resumable) and a combined images.jsonl + heartbeat.json.
`/api/v1/user/<name>/images` does not exist on this API — the username filter on the images
endpoint is the only way to list one author's whole gallery.
"""
import argparse
import json
import os
import time
import urllib.parse
import urllib.request

UA = 'Mozilla/5.0 (author-experience-library scraper)'
OPENER = None


def get(url, tries=5):
    last = None
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
            if OPENER is None:
                with urllib.request.urlopen(req, timeout=90) as r:
                    return json.load(r)
            with OPENER.open(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(2 + 4 * n)
    raise RuntimeError('%s -> %s' % (url, last))


def main():
    global OPENER
    ap = argparse.ArgumentParser()
    ap.add_argument('username')
    ap.add_argument('--out', required=True)
    ap.add_argument('--page-size', type=int, default=100)
    ap.add_argument('--max-pages', type=int, default=0)
    ap.add_argument('--nsfw', default='X', help='browsing level; X = include explicit, else R/S...')
    ap.add_argument('--site', default='https://civitai.red', help='civitai.red (explicit) or civitai.com (safe)')
    ap.add_argument('--proxy', default='', help='e.g. http://127.0.0.1:1080 ; empty = direct')
    a = ap.parse_args()

    if a.proxy:
        OPENER = urllib.request.build_opener(urllib.request.ProxyHandler(
            {'http': a.proxy, 'https': a.proxy}))
    base = a.site.rstrip('/') + '/api/v1/images'

    pdir = os.path.join(a.out, 'raw', 'pages')
    os.makedirs(pdir, exist_ok=True)
    hb = os.path.join(a.out, 'heartbeat.json')

    cursor = None
    page = 0
    total = 0
    while True:
        page += 1
        path = os.path.join(pdir, 'page_%04d.json' % page)
        if os.path.exists(path) and os.path.getsize(path) > 100:
            d = json.load(open(path, encoding='utf-8'))
        else:
            q = {'username': a.username, 'limit': a.page_size, 'withMeta': 'true', 'nsfw': a.nsfw}
            if cursor:
                q['cursor'] = cursor
            url = base + '?' + urllib.parse.urlencode(q)
            d = get(url)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False)
            time.sleep(0.4)
        items = d.get('items') or []
        total += len(items)
        cursor = (d.get('metadata') or {}).get('nextCursor')
        open(hb, 'w', encoding='utf-8').write(json.dumps(
            {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'pages': page, 'images': total,
             'status': 'running' if cursor else 'done'}, ensure_ascii=False))
        print('page %4d  items %3d  total %6d  cursor=%s' % (page, len(items), total, cursor), flush=True)
        if not items or not cursor:
            break
        if a.max_pages and page >= a.max_pages:
            print('stopped at max-pages', flush=True)
            break
    print('DONE pages=%d images=%d' % (page, total), flush=True)


if __name__ == '__main__':
    main()
