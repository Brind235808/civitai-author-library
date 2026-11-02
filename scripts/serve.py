"""Static file server for the local walls (pose wall + author experience library).

usage: python serve.py [port] [root]        defaults: 8899, current working directory

Why not node: Node on Windows aborts the whole process (exit 0xC0000409) when many clients
abandon connections mid-response, which is what a wall with 1,400 lazy <img> tags does while
scrolling. ThreadingHTTPServer survives that. Binds to 127.0.0.1 only; path traversal is
refused by SimpleHTTPRequestHandler.translate_path.
"""
import http.server
import os
import socketserver
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
ROOT = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serve.log')

EXT_TYPE = {
    '.html': 'text/html; charset=utf-8', '.htm': 'text/html; charset=utf-8',
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp',
    '.gif': 'image/gif', '.svg': 'image/svg+xml', '.json': 'application/json; charset=utf-8',
    '.txt': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8',
    '.csv': 'text/csv; charset=utf-8', '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8', '.py': 'text/plain; charset=utf-8',
}


def note(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write('%s serve.py %s\n' % (self_ts(), msg))
    except Exception:
        pass


def self_ts():
    import datetime
    return datetime.datetime.now().isoformat(timespec='seconds')


def cache_for(path):
    ext = os.path.splitext(path.split('?')[0])[1].lower()
    if ext in ('.html', '.htm'):
        return 'no-cache'
    if ext in ('.json', '.csv', '.txt', '.md'):
        return 'public, max-age=300'
    return 'public, max-age=86400'


class Handler(http.server.SimpleHTTPRequestHandler):
    server_root = ROOT
    protocol_version = 'HTTP/1.1'          # keep-alive: localhost serving 1,400 imgs per page

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=self.server_root, **kwargs)

    def guess_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        return EXT_TYPE.get(ext) or super().guess_type(path)

    def end_headers(self):
        self.send_header('Cache-Control', cache_for(self.path))
        super().end_headers()

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError):
            # a wall with 1,400 lazy <img> tags abandons off-screen requests constantly; not an error
            self.close_connection = True
        except OSError as e:
            if getattr(e, 'winerror', 0) in (10053, 10054):
                self.close_connection = True
            else:
                note('socket error: %r' % (e,))
                self.close_connection = True
        except Exception as e:
            note('request error: %r' % (e,))
            self.close_connection = True

    def log_message(self, fmt, *args):
        pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    # socketserver defaults this to 5, which makes a page asking for 1,400 images look "dead"
    request_queue_size = 256

    def verify_request(self, request, client_address):
        return True

    def handle_error(self, request, client_address):
        import traceback
        note('handler error: ' + traceback.format_exc().splitlines()[-1])


if __name__ == '__main__':
    if not os.path.isdir(ROOT):
        sys.exit('root not a directory: %s' % ROOT)
    http.server.SimpleHTTPRequestHandler.extensions_map.update(EXT_TYPE)
    with Server(('127.0.0.1', PORT), Handler) as httpd:
        note('serving %s at http://127.0.0.1:%d/' % (ROOT, PORT))
        print('serving %s at http://127.0.0.1:%d/' % (ROOT, PORT), flush=True)
        httpd.serve_forever()
