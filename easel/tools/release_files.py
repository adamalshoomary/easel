#!/usr/bin/env python3
"""Stage the files that an easel release carries, and serve them the way GitHub does.

A release holds its files flat: VERSION, SKILL.md, easel.py, scrape.js, viewer.js, install.sh
and install.ps1. The release workflow uploads them. CI serves them on 127.0.0.1, then installs
easel from that address the same way a student installs it from GitHub.

    python easel/tools/release_files.py OUT_DIR
    python easel/tools/release_files.py OUT_DIR --serve PORT

The server answers like github.com/<repo>/releases/latest/download/<name>: a redirect, then
the file as application/octet-stream. Point EASEL_FROM at http://127.0.0.1:PORT/latest/download.
"""
import argparse
import shutil
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

EASEL = Path(__file__).resolve().parent.parent
KIT = EASEL / "skills" / "easel"
FILES = {
    "VERSION": KIT / "VERSION",
    "SKILL.md": KIT / "SKILL.md",
    "easel.py": KIT / "scripts" / "easel.py",
    "scrape.js": KIT / "scripts" / "scrape.js",
    "viewer.js": KIT / "scripts" / "viewer.js",
    "install.sh": EASEL / "install.sh",
    "install.ps1": EASEL / "install.ps1",
}


def stage(out):
    out.mkdir(parents=True, exist_ok=True)
    for name, src in FILES.items():
        shutil.copyfile(src, out / name)
    return out


def server(folder, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            name = self.path.rsplit("/", 1)[-1]
            if self.path == "/latest/download/" + name and (folder / name).is_file():
                self.send_response(302)
                self.send_header("Location", "/assets/" + name)
                self.end_headers()
            elif self.path == "/assets/" + name and (folder / name).is_file():
                data = (folder / name).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename=" + name)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404)

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--serve", type=int, metavar="PORT")
    a = ap.parse_args()
    out = stage(Path(a.out))
    print(f"staged {len(FILES)} files in {out}", flush=True)
    if a.serve:
        httpd = server(out, a.serve)
        print(f"serving on http://127.0.0.1:{a.serve}/latest/download", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            sys.exit(0)


if __name__ == "__main__":
    main()
