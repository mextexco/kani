#!/usr/bin/env python3
"""claude_crab を配信するローカルサーバー（バナー付き）。使い方: python3 serve.py [port]
Sarashina API(SB Intuitions)の中継も兼ねる: POST /api/sarashina/{chat/completions,translate}
 （ブラウザからは CORS で直接呼べないため。キーは環境変数 SARASHINA_API_KEY か secret.js の SARASHINA_KEY）"""
import http.server
import json
import os
import re
import socketserver
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
sys.stdout.reconfigure(line_buffering=True)

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
ROOT = os.path.dirname(os.path.abspath(__file__))
URL = f"http://localhost:{PORT}/claude_crab.html"

G, D, R = "\033[38;5;46m", "\033[2m", "\033[0m"

BANNER = r"""
   ____ _                 _        ____ ____      _    ____
  / ___| | __ _ _   _  __| | ___  / ___|  _ \    / \  | __ )
 | |   | |/ _` | | | |/ _` |/ _ \| |   | |_) |  / _ \ |  _ \
 | |___| | (_| | |_| | (_| |  __/| |___|  _ <  / ___ \| |_) |
  \____|_|\__,_|\__,_|\__,_|\___| \____|_| \_\/_/   \_\____/
"""

CRAB = r"""
      \\  (o)___(o)  //
       \\/  \___/  \//
        (  /  _  \  )
         \/_/ | \_\/
"""


SARASHINA_BASE = "https://api.sarashina.ai/v1/"
SARASHINA_PATHS = {"chat/completions", "translate"}


def sarashina_key():
    k = os.environ.get("SARASHINA_API_KEY", "").strip()
    if k:
        return k
    try:
        with open(os.path.join(ROOT, "secret.js"), encoding="utf-8") as f:
            m = re.search(r"SARASHINA_KEY\s*=\s*['\"]([^'\"]+)['\"]", f.read())
        return m.group(1) if m else ""
    except OSError:
        return ""


# RSS中継: ブラウザは多くのRSS元にCORSで直接アクセスできないため、サーバー側で取得して返す。
# 取得を許可するのは claude_crab.html の RSS_FEEDS に書かれた url:'...' だけ(任意URLの踏み台にしない)。
RSS_CACHE = {}          # url -> (取得時刻, ステータス, 本文)
RSS_CACHE_SEC = 300     # 同じ元には5分に1回しか取りに行かない
RSS_MAX_BYTES = 3 * 1024 * 1024


def rss_allowed():
    try:
        with open(os.path.join(ROOT, "claude_crab.html"), encoding="utf-8") as f:
            return set(re.findall(r"url:\s*'(https?://[^']+)'", f.read()))
    except OSError:
        return set()


def fetch_rss(url):
    hit = RSS_CACHE.get(url)
    if hit and time.time() - hit[0] < RSS_CACHE_SEC:
        return hit[1], hit[2]
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (claude-crab rss fetcher)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read(RSS_MAX_BYTES + 1)
            code = r.status
    except urllib.error.HTTPError as e:
        code, body = e.code, b""
    if len(body) > RSS_MAX_BYTES:
        return 502, b""
    if code == 200 and body:
        RSS_CACHE[url] = (time.time(), code, body)
    elif hit:  # 取得失敗時は期限切れでも前回分を返す
        return hit[1], hit[2]
    return code, body


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/rss?"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            url = (q.get("url") or [""])[0]
            if url not in rss_allowed():
                return self._json(403, {"error": "feed not allowed"})
            try:
                code, body = fetch_rss(url)
            except Exception as e:  # noqa: BLE001
                return self._json(502, {"error": str(e)})
            if code != 200:
                return self._json(502, {"error": f"upstream {code}"})
            self.send_response(200)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def do_POST(self):
        prefix = "/api/sarashina/"
        if not self.path.startswith(prefix):
            return self._json(404, {"error": "not found"})
        path = self.path[len(prefix):].split("?")[0]
        if path not in SARASHINA_PATHS:
            return self._json(404, {"error": "not found"})
        # 他サイトからのブラウザ経由の悪用を避ける: JSON以外は拒否(クロスオリジンはプリフライトで弾かれる)
        if not (self.headers.get("Content-Type", "").startswith("application/json")):
            return self._json(415, {"error": "json only"})
        key = sarashina_key()
        if not key:
            return self._json(503, {"error": "SARASHINA key not set"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        if n <= 0 or n > 65536:
            return self._json(413, {"error": "bad size"})
        req = urllib.request.Request(
            SARASHINA_BASE + path, self.rfile.read(n),
            {"Content-Type": "application/json", "Authorization": "Bearer " + key, "User-Agent": "claude-crab-proxy/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                code, body = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, body = e.code, e.read()
        except Exception as e:  # noqa: BLE001
            return self._json(502, {"error": str(e)})
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True  # RSS取得を並列にこなす（遅い元が他を塞がない）


def main():
    print(f"{G}{BANNER}{CRAB}{R}")
    print(f"{G}  🦀 Claude Crab ダッシュボード用 ローカルサーバー{R}")
    print(f"{D}  配信元: {ROOT}{R}")
    print(f"{D}  RSS中継: 有効（/api/rss・許可元 {len(rss_allowed())} 件）{R}")
    print(f"{D}  翻訳中継: Sarashina API {'キー検出 ✓' if sarashina_key() else 'キー未設定（secret.js に SARASHINA_KEY）'}{R}")
    print(f"  開く → {G}{URL}{R}")
    print(f"{D}  停止: Ctrl+C{R}\n")
    with Server(("127.0.0.1", PORT), Handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print(f"\n{G}  🦀 停止した{R}")


if __name__ == "__main__":
    main()
