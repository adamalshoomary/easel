#!/usr/bin/env python3
"""Build the self-contained easel prompt, for people who cannot reach GitHub.

The prompt carries the whole skill folder as one compressed, base64-encoded block with a
SHA-256 checksum. A pasted copy installs the skill without a download. Attach the output
to a GitHub release; it does not belong in the repository.

    python3 tools/build_offline_prompt.py        writes dist/easel-offline-prompt.md
"""
import base64
import hashlib
import json
import textwrap
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "easel"
FILES = ["SKILL.md", "VERSION", "scripts/easel.py", "scripts/scrape.js", "scripts/viewer.js"]

INSTALL = r'''python3 - "$@" <<'EOF'
import base64,hashlib,json,os,pathlib,re,sys,zlib
R=re.compile(r"EASEL-BLOB-BEGIN-SHA256-([0-9a-f]{64})(.+?)EASEL-BLOB-END",re.S)
def clean(t): return re.sub(r"[^A-Za-z0-9+/=]","",t)
src=[open(a,encoding="utf-8",errors="replace").read() for a in sys.argv[1:]]
logs=sorted((os.path.join(d,f) for d,x,n in os.walk(os.path.expanduser("~/.claude/projects")) for f in n if f.endswith(".jsonl")),key=os.path.getmtime,reverse=True)[:30]
src+=[l for f in logs for l in reversed(open(f,encoding="utf-8",errors="replace").read().splitlines()) if "EASEL-BLOB-BEGIN" in l]
blob=None
for t in src:
    t=t.replace("\\n"," ")
    for h,b in R.findall(t):
        b=clean(b)
        if hashlib.sha256(b.encode()).hexdigest()==h: blob=b;break
    if blob: break
if not blob: sys.exit("NOT FOUND")
files=json.loads(zlib.decompress(base64.b64decode(blob)).decode("utf-8"))
for root in ("~/.claude/skills/easel","~/.agents/skills/easel"):
    d=pathlib.Path(os.path.expanduser(root))
    for k,v in files.items():
        p=d/k; p.parent.mkdir(parents=True,exist_ok=True); open(p,"w",encoding="utf-8",newline="\n").write(v)
print("INSTALLED", ", ".join(sorted(files)))
EOF'''


def main():
    files = {f: (SKILL / f).read_text(encoding="utf-8") for f in FILES}
    version = files["VERSION"].split()[0]
    blob = base64.b64encode(zlib.compress(json.dumps(files, ensure_ascii=False).encode("utf-8"), 9)).decode("ascii")
    digest = hashlib.sha256(blob.encode()).hexdigest()
    body = "\n".join(textwrap.wrap(blob, 100))
    out = f"""Use easel {version} to copy my Canvas units into Markdown notes. This prompt carries easel itself, so it works without GitHub.

Canvas: https://canvas.your-university.edu
Units: ABC101 ABC102
Notes folder: this folder

1. If `~/.claude/skills/easel/SKILL.md` exists and its folder has `VERSION` {version} or newer, go to step 4.
2. Run the install command below with Bash. Use `python` in place of `python3` if `python3` fails.
3. If it prints `NOT FOUND`, write the block between EASEL-BLOB-BEGIN and EASEL-BLOB-END into `~/easel-blob.txt` with your file tool. Then run the install command again with `~/easel-blob.txt` after `python3 -`.
4. Read `~/.claude/skills/easel/SKILL.md`. In it, the kit is `~/.claude/skills/easel`.
5. Follow `SKILL.md` with the values above. If "Notes folder" says "this folder", leave out `--root`.

```bash
{INSTALL}
```

EASEL-BLOB-BEGIN-SHA256-{digest}
{body}
EASEL-BLOB-END
"""
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "easel-offline-prompt.md").write_text(out, encoding="utf-8")
    print(f"wrote dist/easel-offline-prompt.md: {len(out):,} characters, easel {version}")


if __name__ == "__main__":
    main()
