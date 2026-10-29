#!/usr/bin/env python3
"""claude_crab を配信するローカルサーバー（バナー付き）。使い方: python3 serve.py [port]"""
import http.server
import os
import socketserver
import sys
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


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)


class Server(socketserver.TCPServer):
    allow_reuse_address = True


def main():
    print(f"{G}{BANNER}{CRAB}{R}")
    print(f"{G}  🦀 Claude Crab ダッシュボード用 ローカルサーバー{R}")
    print(f"{D}  配信元: {ROOT}{R}")
    print(f"  開く → {G}{URL}{R}")
    print(f"{D}  停止: Ctrl+C{R}\n")
    with Server(("", PORT), Handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print(f"\n{G}  🦀 停止した{R}")


if __name__ == "__main__":
    main()
