"""Download the evidence for the selected comparison cases: original image + its source metadata.

Usage: python download_evidence.py <author_dir> [--workers 12] [--limit N] [--probe N]

One pooled requests.Session is the whole point: image.civitai.com costs ~4s per fresh TLS
handshake but only ~0.25s per file once the connection is reused, so keep-alive turns 0.1 img/s
into 3.5 img/s. Proxy first, direct fallback (either route can be dead on a given day).
Resume-safe: existing non-trivial files are skipped. Progress -> heartbeat.json.
  img/<id>.jpg    original file as hosted by Civitai
  thumbs/<id>.jpg wall preview
  meta/<id>.json  the generation parameters this author published with that image
"""
import argparse
import concurrent.futures
import json
import os
import time

import requests
from requests.adapters import HTTPAdapter


def make_session(proxy, workers):
    s = requests.Session()
    if proxy:
        s.proxies = {'http': proxy, 'https': proxy}
    s.headers['User-Agent'] = 'Mozilla/5.0'
    s.mount('https://', HTTPAdapter(pool_connections=workers, pool_maxsize=workers * 2))
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir')
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--probe', type=int, default=0)
    ap.add_argument('--proxy', default=os.environ.get('CIVITAI_PROXY', ''),
                    help='e.g. http://127.0.0.1:1080 ; default $CIVITAI_PROXY, empty = direct only')
    a = ap.parse_args()
    d = a.dir
    for sub in ('img', 'thumbs', 'meta'):
        os.makedirs(os.path.join(d, sub), exist_ok=True)

    rows = {}
    for line in open(os.path.join(d, 'images.jsonl'), encoding='utf-8'):
        r = json.loads(line)
        rows[r['id']] = r
    man = json.load(open(os.path.join(d, 'download_manifest.json'), encoding='utf-8'))
    todo = man['images']
    if a.probe:
        todo = todo[:a.probe]
    elif a.limit:
        todo = todo[:a.limit]

    for im in todo:
        p = os.path.join(d, 'meta', '%s.json' % im['id'])
        if not os.path.exists(p) and im['id'] in rows:
            json.dump(rows[im['id']], open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    routes = [('proxy', make_session(a.proxy, a.workers)), ('direct', make_session(None, a.workers))]
    if not a.proxy:
        routes = routes[1:]
    else:
        routes = (routes[0], routes[0], routes[1])      # proxy twice before falling back

    def get_one(im):
        iid = im['id']
        jpg = os.path.join(d, 'img', '%s.jpg' % iid)
        if os.path.exists(jpg) and os.path.getsize(jpg) > 2000:
            return (iid, 'skip', 0)
        data, last = None, ''
        for tag, sess in routes:
            try:
                r = sess.get(im['url'], timeout=45)
                if r.status_code == 200 and len(r.content) > 1000:
                    data = r.content
                    break
                last = '%s http%s' % (tag, r.status_code)
            except Exception as e:
                last = '%s %s' % (tag, type(e).__name__)
                time.sleep(0.5)
        if data is None:
            return (iid, 'FAIL:' + last, 0)
        open(jpg + '.part', 'wb').write(data)
        os.replace(jpg + '.part', jpg)
        try:
            from PIL import Image
            th = os.path.join(d, 'thumbs', '%s.jpg' % iid)
            im2 = Image.open(jpg).convert('RGB')
            im2.thumbnail((250, 750))
            im2.save(th, 'JPEG', quality=74)
        except Exception:
            pass
        return (iid, 'new', len(data))

    t0 = time.time()
    counts = {'new': 0, 'skip': 0}
    fails, bytes_ = [], 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        done = 0
        for iid, st, sz in ex.map(get_one, todo):
            done += 1
            if st == 'new':
                counts['new'] += 1
                bytes_ += sz
            elif st == 'skip':
                counts['skip'] += 1
            else:
                fails.append((iid, st))
            if done % 25 == 0 or done == len(todo):
                el = time.time() - t0
                json.dump({'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'status': 'downloading',
                           'done': done, 'total': len(todo), 'new': counts['new'],
                           'fail': len(fails), 'mb': round(bytes_ / 1e6, 1),
                           'rate': round(done / max(1, el), 2)},
                          open(os.path.join(d, 'heartbeat.json'), 'w', encoding='utf-8'),
                          ensure_ascii=False)
                print('%d/%d new=%d skip=%d fail=%d %.1fMB %.2f img/s eta%.0fm' %
                      (done, len(todo), counts['new'], counts['skip'], len(fails),
                       bytes_ / 1e6, done / max(1, el),
                       (len(todo) - done) / max(0.01, done / max(1, el)) / 60), flush=True)
    el = time.time() - t0
    if fails:
        with open(os.path.join(d, 'download_fail.txt'), 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (time.strftime('%F %T'), json.dumps(fails, ensure_ascii=False)))
    json.dump({'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'status': 'done', 'total': len(todo),
               'new': counts['new'], 'skip': counts['skip'], 'fail': len(fails),
               'mb': round(bytes_ / 1e6, 1)},
              open(os.path.join(d, 'heartbeat.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print('DONE new=%d skip=%d fail=%d %.1fMB in %.0fs (%.2f img/s)' %
          (counts['new'], counts['skip'], len(fails), bytes_ / 1e6, el, len(todo) / max(1, el)))


if __name__ == '__main__':
    main()
