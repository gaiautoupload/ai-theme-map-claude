"""本機預覽：只聽 127.0.0.1，提供 site/ 靜態檔。python web_server.py [port]"""
from __future__ import annotations

import functools
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from pipeline import config


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # 預覽時程式或資料一改就看得到
        super().end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8890
    srv = ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=str(config.SITE)))
    print(f"題材地圖預覽：http://127.0.0.1:{port}/", flush=True)
    srv.serve_forever()
