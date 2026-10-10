#!/usr/bin/env python3
# easel helper: copies Canvas units into Markdown notes.
"""easel helper.

The helper serves the browser script to a signed-in Canvas tab, receives the Canvas data
and files, plans the notes, writes them, and checks the result.

Commands:
  start UNITS --canvas URL [--root DIR] [--media] [--tidy] [--no-feedback] [--refresh-feedback]
  wait
  viewer-js
  scale --canvas URL --set "7:85,6:75,5:65,4:50"
  rebuild BUNDLE --target DIR
  version

Python 3.8 or newer, standard library only. Runs on macOS, Windows and Linux.
"""
from __future__ import annotations

import filecmp
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "4.1.0"
REPO = "adamalshoomary/easel"
# Updates come from the latest published release. EASEL_FROM points at another copy of the release files, for tests.
RELEASE = (os.environ.get("EASEL_FROM") or "https://github.com/" + REPO + "/releases/latest/download").rstrip("/") + "/"
# A release holds its files flat. This maps each release file to its place in the skill folder.
KIT_FILES = {"VERSION": "VERSION", "SKILL.md": "SKILL.md", "easel.py": "scripts/easel.py",
             "scrape.js": "scripts/scrape.js", "viewer.js": "scripts/viewer.js"}
HERE = Path(__file__).resolve().parent     # the scripts folder
KIT = HERE.parent                          # the skill folder: SKILL.md, VERSION, scripts/
STATE = Path(os.environ.get("EASEL_HOME") or (Path.home() / ".easel"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ORIGIN = "https://canvas.example.edu"      # replaced by --canvas or a unit's manifest
TZ = datetime.now().astimezone().tzinfo    # this computer's time zone
NOW = datetime.now(TZ)
TODAY = NOW.strftime("%Y-%m-%d")
MANAGED = ["1 Course Info", "2 Assessments", "3 Weeks", "Files"]
MANAGED_TOP = set(MANAGED) | {"INDEX.md", ".easel", ".canvas-manifest.json"}
WEEK_RE = re.compile(r"^\s*weeks?\s*0*(\d{1,2})(?:\s*(?:-|–|—|to|&|and)\s*0*(\d{1,2}))?(?!\d)\s*[:\-–—|.,]?\s*(.*)$", re.I)
ASSESS_RE = re.compile(r"assess|assignment|exam\b|portfolio", re.I)
UNIT_PREFIX = re.compile(r"^\s*[A-Z]{2,5}\d{3,5}[A-Z]?(?:_\d\w*)?\s*[:\-–|_]?\s*")
MAX_BYTES = 100 * 1024 * 1024
MY_NOTES = "## My notes"
MY_NOTES_HINT = "<!-- easel keeps everything under this heading when it updates the note. -->"
OWNED_FM = {"easel", "unit", "week", "kind", "canvas", "due", "points", "status", "score", "grade", "submitted",
            "graded", "weight", "group", "updated", "sections", "term", "estimate", "band", "source_folder", "pages", "scraped"}
WIN_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


# ---------------------------------------------------------------- small helpers
def clean_name(s):
    s = (s or "").strip()
    s = s.replace(":", " -").replace("/", "-").replace("\\", "-")
    s = re.sub(r'[*?"<>|#^\[\]\x00-\x1f]', "", s)
    s = re.sub(r"\s+", " ", s).strip(" .-")
    if s.upper() in WIN_RESERVED:
        s += " note"
    return s or "Untitled"


def short_name(title, limit=70):
    """File names stay readable: cut long titles at a word boundary. The heading keeps the full title."""
    if len(title) <= limit:
        return title
    head = title[:limit]
    seg = head.rfind(" - ", 12)
    cut = head[:seg] if seg > 0 else head.rsplit(" ", 1)[0]
    return cut.rstrip(" ,-–(") or head


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def parse_dt(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(TZ)
    except Exception:
        return None


def tzname(d):
    name = d.tzname() or ""
    if not name or " " in name or len(name) > 5:     # Windows gives "E. Australia Standard Time"
        z = d.strftime("%z")
        name = f"UTC{z[:3]}:{z[3:]}" if z else ""
    return name


def fmt_dt(iso):
    d = parse_dt(iso)
    return (d.strftime("%Y-%m-%d %H:%M ") + tzname(d)).strip() if d else (iso or None)


def fmt_day(iso):
    """Mon 15 Sep 2026, 23:59"""
    d = parse_dt(iso)
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b %Y')}, {d.strftime('%H:%M')}" if d else None


def fmt_date(iso):
    d = parse_dt(iso)
    return f"{d.day} {d.strftime('%b %Y')}" if d else None


def relative_days(iso):
    d = parse_dt(iso)
    if not d:
        return ""
    days = (d.date() - NOW.date()).days
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days == -1:
        return "yesterday"
    return f"in {days} days" if days > 0 else f"{-days} days ago"


def pts(x):
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return f"{x:g}" if isinstance(x, (int, float)) else str(x if x is not None else "")


def pct(x):
    return f"{x * 100:.1f}".rstrip("0").rstrip(".") + "%"


def demote(md):
    out, fence = [], False
    for line in md.split("\n"):
        if line.startswith("```"):
            fence = not fence
        elif not fence:
            m = re.match(r"^(#{1,6})(\s)", line)
            if m:
                line = ("#" * min(6, len(m.group(1)) + 1)) + line[len(m.group(1)):]
        out.append(line)
    return "\n".join(out)


def link_path(from_dir: Path, target: Path):
    rel = os.path.relpath(target, from_dir)
    return urllib.parse.quote(rel.replace(os.sep, "/"), safe="/-_.~").replace("(", "%28").replace(")", "%29")


def words(md):
    return len(re.findall(r"\w+", md))


def cell(s):
    return re.sub(r"\s*\n\s*", "<br>", str(s or "").strip()).replace("|", "\\|")


def lbl(s):
    """Link text with no square brackets, so the link stays one link."""
    return cell(s).replace("[", "(").replace("]", ")")


def normalize(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")


def sha(text):
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:16]


def raw_sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def file_sha(p: Path):
    h = hashlib.sha256()
    with open(lp(p), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def lp(p):
    """Windows needs the long-path prefix for paths over 260 characters."""
    s = str(p)
    if os.name == "nt" and len(s) > 240 and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.abspath(s)
    return s


def read_text(p: Path):
    with open(lp(p), "r", encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def write_text(p: Path, text: str):
    Path(lp(p.parent)).mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".easel-tmp")
    with open(lp(tmp), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(lp(tmp), lp(p))


def yaml_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return pts(v)
    s = str(v)
    if re.fullmatch(r"[A-Za-z][\w .,()/+%-]*", s) and s.lower() not in {"true", "false", "null", "yes", "no", "on", "off"} \
            and not re.search(r"\s-|: |\s#", s):
        return s
    return json.dumps(s, ensure_ascii=False)


def split_frontmatter(text):
    """Return (frontmatter lines or None, body)."""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    if t.startswith("---\n"):
        end = t.find("\n---\n", 3)
        if end < 0 and t.endswith("\n---"):
            end = len(t) - 4
        if end > 0:
            return t[4:end].split("\n"), t[end + 5:]
    return None, t


def fm_blocks(lines):
    """Top-level keys with their continuation lines, in order."""
    blocks = []
    for line in lines or []:
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:", line)
        if m and not line.startswith((" ", "\t", "-")):
            blocks.append([m.group(1), [line]])
        elif blocks:
            blocks[-1][1].append(line)
    return blocks


def fm_value(lines, key):
    for k, ls in fm_blocks(lines):
        if k == key:
            v = ls[0].split(":", 1)[1].strip()
            try:
                return json.loads(v) if v.startswith('"') else v
            except Exception:
                return v
    return None


def split_my_notes(body):
    """Return (generated part, student's part or None)."""
    i = body.find("\n" + MY_NOTES + "\n")
    if i < 0 and body.endswith("\n" + MY_NOTES):
        i = len(body) - len(MY_NOTES) - 1
    if i < 0:
        if body.startswith(MY_NOTES + "\n"):
            i = -1
        else:
            return body, None
    gen = body[:i + 1] if i >= 0 else ""
    rest = body[i + 1 + len(MY_NOTES):] if i >= 0 else body[len(MY_NOTES):]
    rest = rest.lstrip("\n")
    if rest.startswith(MY_NOTES_HINT):
        rest = rest[len(MY_NOTES_HINT):]
    return gen, rest.strip("\n")


def snapshot(paths):
    snap = {}
    for root in paths:
        root = Path(root)
        it = [root] if root.is_file() else root.rglob("*")
        for f in it:
            if f.is_file():
                try:
                    st = f.stat()
                    snap[str(f)] = (st.st_size, int(st.st_mtime))
                except OSError:
                    pass
    return snap


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", (v or "").split("(")[0])[:3]) or (0,)


# ---------------------------------------------------------------- config
def load_config():
    try:
        return json.loads((STATE / "config.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg):
    STATE.mkdir(parents=True, exist_ok=True)
    write_text(STATE / "config.json", json.dumps(cfg, indent=1, ensure_ascii=False))


def host_of(url):
    return urllib.parse.urlparse(url).netloc.lower()


# ---------------------------------------------------------------- target folder
def find_target(root: Path, unit: str):
    """The unit folder is a folder whose name starts with the unit code. Look in the root, up to
    4 levels below it, then beside it when the root is another unit's folder. Prefer folders with a manifest."""
    code = unit.upper()
    if root.name.upper().startswith(code):
        return root
    hits, stack = [], [(root, 0)]
    while stack:
        d, depth = stack.pop()
        try:
            kids = [k for k in d.iterdir() if k.is_dir() and not k.name.startswith(".")]
        except OSError:
            continue
        for k in kids:
            if k.name.upper().startswith(code):
                hits.append(k)
            elif depth < 4 and k.name not in MANAGED:
                stack.append((k, depth + 1))
    if not hits and re.match(r"^[A-Z]{2,5}\d{3,5}", root.name.upper()):
        hits = [d for d in root.parent.iterdir() if d.is_dir() and d.name.upper().startswith(code)]
    if not hits:
        return None

    def has_manifest(d):
        return (d / ".easel" / "manifest.json").exists() or (d / ".canvas-manifest.json").exists()
    hits.sort(key=lambda d: (has_manifest(d), d.stat().st_mtime), reverse=True)
    return hits[0]


def load_manifest(target: Path):
    """Return (manifest dict, manifest mtime, format) from .easel/manifest.json or a v3 .canvas-manifest.json."""
    for p, fmt in ((target / ".easel" / "manifest.json", 4), (target / ".canvas-manifest.json", 3)):
        if p.exists():
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
                for k in ("notes", "files"):
                    for x in m.get(k, []):
                        if isinstance(x.get("path"), str):
                            x["path"] = x["path"].replace("\\", "/")
                return m, p.stat().st_mtime, fmt
            except Exception:
                return {}, 0.0, fmt
    return {}, 0.0, 0


class Unit:
    def __init__(self, code, target, root: Path):
        self.code, self.root = code.upper(), root
        self.target = target
        self.old, self.manifest_mtime, self.old_format = load_manifest(target) if target else ({}, 0.0, 0)
        self.mode = "update" if target and all((target / d).is_dir() for d in MANAGED[:3]) else "full"
        self.bundle = None
        self.plan = None
        self.staging = Path(tempfile.mkdtemp(prefix=f"easel-{self.code}-"))
        self.received, self.failed = {}, {}
        self.done = False
        self.error = None
        self.report = ""
        self.summary = ""
        self.timing = {}
        self.media = False
        self.tidy = False
        self.feedback_enabled = True
        self.refresh_feedback = False
        self.reset_edited = False
        self.feedback_asg = set()
        self.viewer_keys = []
        self.result = {}

    def cfg(self):
        return {"unit": self.code, "course_id": self.old.get("course_id")}


def set_origin(url, units=()):
    global ORIGIN
    url = url or next((u.old.get("canvas") for u in units if u.old.get("canvas")), None)
    if not url:
        raise SystemExit("Give the Canvas address with --canvas https://<your canvas site>")
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    ORIGIN = urllib.parse.urlunparse(urllib.parse.urlparse(url)._replace(path="", params="", query="", fragment=""))


# ---------------------------------------------------------------- grades
def scheme_of(bundle):
    s = (bundle.get("course") or {}).get("grading_scheme")
    if s and s.get("data"):
        data = sorted(((str(n), float(v)) for n, v in s["data"]), key=lambda x: -x[1])
        return {"title": s.get("title") or "Canvas grading scheme", "data": data, "source": "Canvas"}
    cfg = load_config().get("hosts", {}).get(host_of(ORIGIN), {})
    if cfg.get("scale"):
        return {"title": cfg.get("scale_title") or "Your grade scale", "data": sorted(((str(n), float(v)) for n, v in cfg["scale"]), key=lambda x: -x[1]),
                "source": "you"}
    return None


def band_of(scheme, fraction):
    if not scheme or fraction is None:
        return None
    for name, v in scheme["data"]:
        if fraction + 1e-9 >= v:
            return name
    return scheme["data"][-1][0] if scheme["data"] else None


class Grades:
    """Canvas's grade arithmetic: group weights, points, drop rules, excused and omitted work.
    Canvas hides the unit total at some universities, so easel computes it and labels it as its own."""

    def __init__(self, bundle):
        b = bundle
        self.weighted = bool(b.get("group_weights") or (b.get("course") or {}).get("apply_group_weights"))
        self.groups = []
        by_group = {}
        for a in b.get("assignments") or []:
            if a.get("omit_from_final_grade") or a.get("published") is False:
                continue
            if a.get("grading_type") == "not_graded":
                continue
            p = a.get("points_possible")
            if not isinstance(p, (int, float)) or p <= 0:
                continue
            s = a.get("submission") or {}
            if s.get("excused"):
                continue
            score = s.get("score") if isinstance(s.get("score"), (int, float)) else None
            by_group.setdefault(a.get("assignment_group_id"), []).append({"a": a, "points": float(p), "score": score})
        for g in sorted(b.get("assignment_groups") or [], key=lambda g: g.get("position") or 0):
            items = by_group.pop(g["id"], [])
            w = g.get("group_weight") or 0
            if not items and not (self.weighted and w):
                continue
            self.groups.append({"g": g, "weight": float(w), "items": items, "rules": g.get("rules") or {}})
        if by_group:   # assignments whose group Canvas did not list
            items = [x for v in by_group.values() for x in v]
            self.groups.append({"g": {"id": None, "name": "Other"}, "weight": 0.0, "items": items, "rules": {}})

    def group_result(self, grp, fill):
        """(earned, possible) for a group. fill=None leaves unmarked work out; a number counts it at that fraction."""
        items = []
        for it in grp["items"]:
            if it["score"] is not None:
                items.append((it["score"], it["points"], it["a"]["id"]))
            elif fill is not None:
                items.append((fill * it["points"], it["points"], it["a"]["id"]))
        r = grp["rules"]
        never = set(r.get("never_drop") or [])
        droppable = sorted([x for x in items if x[2] not in never], key=lambda x: x[0] / x[1] if x[1] else 0)
        low, high = int(r.get("drop_lowest") or 0), int(r.get("drop_highest") or 0)
        if fill is not None:
            unmarked_total = sum(1 for it in grp["items"] if it["score"] is None)
            keep_room = len(grp["items"]) - unmarked_total
            low = min(low, max(0, len(droppable) - 1))
            _ = keep_room
        else:
            low = min(low, max(0, len(droppable) - 1))
        high = min(high, max(0, len(droppable) - low - 1))
        dropped = set(x[2] for x in droppable[:low]) | set(x[2] for x in droppable[len(droppable) - high:] if high)
        kept = [x for x in items if x[2] not in dropped]
        return sum(x[0] for x in kept), sum(x[1] for x in kept)

    def total(self, fill=None, empty_fill=None):
        """Unit percentage as a fraction. fill: fraction for unmarked work (None = leave it out).
        empty_fill: fraction for weighted groups with no Canvas assessments yet (None = leave them out)."""
        if self.weighted:
            num = den = 0.0
            for grp in self.groups:
                e, p = self.group_result(grp, fill)
                if p > 0:
                    num += grp["weight"] * e / p
                    den += grp["weight"]
                elif not grp["items"] and empty_fill is not None and grp["weight"]:
                    num += grp["weight"] * empty_fill
                    den += grp["weight"]
            return (num / den) if den else None
        e = p = 0.0
        for grp in self.groups:
            ge, gp = self.group_result(grp, fill)
            e, p = e + ge, p + gp
        return (e / p) if p else None

    def has_unmarked(self):
        return any(it["score"] is None for g in self.groups for it in g["items"]) or \
            any(not g["items"] and g["weight"] for g in self.groups if self.weighted)

    def need(self, threshold):
        """Fraction of the remaining work needed to finish at the threshold, or 'secured' / 'out of reach'."""
        lo_val = self.total(fill=0.0, empty_fill=0.0)
        hi_val = self.total(fill=1.0, empty_fill=1.0)
        if lo_val is None or hi_val is None:
            return None
        if lo_val + 1e-9 >= threshold:
            return "secured"
        if hi_val + 1e-9 < threshold:
            return "out of reach"
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if self.total(fill=mid, empty_fill=mid) >= threshold:
                hi = mid
            else:
                lo = mid
        return hi

    def weight_of(self, a):
        """The share of the unit one assessment carries, as a fraction, where Canvas makes it knowable."""
        for grp in self.groups:
            for it in grp["items"]:
                if it["a"]["id"] == a["id"]:
                    if self.weighted:
                        tot = sum(x["points"] for x in grp["items"])
                        wsum = sum(g["weight"] for g in self.groups if g["items"] or g["weight"])
                        return (grp["weight"] / wsum) * (it["points"] / tot) if tot and wsum else None
                    tot = sum(x["points"] for g in self.groups for x in g["items"])
                    return it["points"] / tot if tot else None
        return None


# ---------------------------------------------------------------- planning
class Planner:
    """Turns a bundle into notes (text with FILE:id and NOTE:key placeholders) and a file plan."""

    def __init__(self, unit: Unit, bundle):
        self.u, self.b = unit, bundle
        self.cid = bundle["course"]["id"]
        self.T = unit.target
        self.notes = []
        self.file_refs = {}
        self.fplan = {}
        self.feedback = {k: v for k, v in (unit.old.get("feedback") or {}).items()}
        self.asg = {a["id"]: a for a in bundle.get("assignments") or []}
        self.grades = Grades(bundle)
        self.scheme = scheme_of(bundle)
        self.asg_note = {}

    # ---- existing notes on disk
    def existing_notes(self):
        ex = []
        old_paths = {n.get("path") for n in self.u.old.get("notes", [])}
        for d in MANAGED[:3]:
            p = self.T / d
            if not p.is_dir():
                continue
            for f in sorted(p.glob("*.md")):
                try:
                    text = read_text(f)
                except Exception:
                    continue
                fm, _ = split_frontmatter(text)
                rel = f.relative_to(self.T).as_posix()
                ours = rel in old_paths or bool(fm and (fm_value(fm, "easel") or (fm_value(fm, "source_folder") is not None and fm_value(fm, "scraped"))))
                ex.append({"path": f, "dir": d, "fm": fm or [], "ours": ours, "text": text,
                           "slugs": set(re.findall(r"/pages/([^)\s#?]+)\)", text)), "used": False})
        return ex

    def module_key(self, m):
        name = (m["name"] or "").strip()
        name = re.sub(r"^\s*o[\s-]?week\b\s*[:\-–—|]?\s*", "Week 0 - O Week - ", name, flags=re.I)
        w = WEEK_RE.match(name)
        if w:
            a, b, topic = int(w.group(1)), w.group(2), clean_name(UNIT_PREFIX.sub("", w.group(3) or ""))
            key = f"Week {a:02d}" + (f"-{int(b):02d}" if b else "")
            title = key + (f" - {topic}" if topic and topic != "Untitled" else "")
            return {"key": key, "kind": "week", "dir": "3 Weeks", "title": title, "nums": (a, int(b) if b else None)}
        base = clean_name(UNIT_PREFIX.sub("", name))
        d = "2 Assessments" if ASSESS_RE.search(name) else "1 Course Info"
        return {"key": base, "kind": "module", "dir": d, "title": base}

    # ---- status of an assessment
    def status_of(self, a):
        s = a.get("submission") or {}
        types = a.get("submission_types") or []
        if s.get("excused"):
            return "excused", "Excused"
        if s.get("score") is not None and s.get("workflow_state") == "graded" or (s.get("score") is not None and s.get("posted_at")):
            return "marked", "Marked"
        if s.get("score") is not None:
            return "marked", "Marked"
        if s.get("missing"):
            return "missing", "Missing"
        counts = isinstance(a.get("points_possible"), (int, float)) and a["points_possible"] > 0
        if s.get("submitted_at"):
            return "submitted", ("Submitted, not marked yet" if counts else "Submitted") + (" (late)" if s.get("late") else "")
        if not types or types == ["none"] or types == ["on_paper"] or types == ["not_graded"]:
            return "no-submission", "Not marked yet" if counts else "Nothing to submit"
        d = parse_dt(a.get("due_at"))
        if d and d < NOW:
            return "overdue", "Not submitted, due date passed"
        return "todo", "Not submitted yet"

    # ---- section renderers
    def locked(self, it):
        if it.get("locked") or it.get("status") in (401, 403, 404):
            exp = it.get("lock_explanation") or ("not available (HTTP %s)" % it.get("status") if it.get("status") else "locked")
            exp = re.sub(r"<[^>]+>", "", str(exp)).strip()
            return f"*Locked on Canvas: {exp}*"
        return None

    @staticmethod
    def title_h2(title):
        t = (title or "Untitled").strip()
        return t + " (Canvas)" if t.lower() == "my notes" else t

    def sec_page(self, it):
        url = f"{ORIGIN}/courses/{self.cid}/pages/{it['page_url']}"
        body = self.locked(it) or demote(it.get("body_md") or "")
        return f"## {self.title_h2(it.get('title'))}\n*[View on Canvas]({url})*\n\n{body}".rstrip()

    def card(self, a, title=None):
        """A short entry in a week or module note that points to the assessment note."""
        code, label = self.status_of(a)
        s = a.get("submission") or {}
        bits = []
        if a.get("due_at"):
            bits.append("due " + fmt_day(a["due_at"]))
        if isinstance(a.get("points_possible"), (int, float)) and a["points_possible"] > 0:
            bits.append(f"{pts(a['points_possible'])} points")
        if code == "marked" and a.get("points_possible"):
            bits.append(f"marked {pts(s.get('score'))}/{pts(a['points_possible'])}")
        else:
            bits.append(label.lower() if code != "todo" else "not submitted yet")
        kind = {"marked": "success", "submitted": "info", "missing": "warning", "overdue": "warning", "excused": "note"}.get(code, "todo")
        return (f"## {self.title_h2(title or a['name'])}\n> [!{kind}] Assessment · " + " · ".join(bits) +
                f"\n> [Open the assessment note](NOTE:asg:{a['id']}) · [View on Canvas]({a['html_url']})")

    def replies_md(self, it):
        rp = it.get("replies") or {}
        ents = rp.get("entries") or []
        if not ents:
            return "" if rp.get("status") in (None, 200) else f"*Replies not visible to you on Canvas (HTTP {rp['status']}).*"
        out = [f"### Replies ({len(ents)})"]
        for e in ents:
            q = "> " * (e.get("depth", 0) + 1)
            head = f"**{e.get('author') or 'Unknown'}, {fmt_dt(e.get('created_at'))}**"
            txt = (e.get("message_md") or "").strip()
            out.append(q + head + ("\n" + "\n".join(q + ln if ln else q.rstrip() for ln in txt.split("\n")) if txt else ""))
        return "\n\n".join(out)

    def sec_quiz(self, it):
        q = it.get("quiz") or {}
        bits = []
        if q:
            bits.append(f"questions: {q.get('question_count', 'n/a')}")
            bits.append(f"points: {pts(q['points_possible'])}" if isinstance(q.get("points_possible"), (int, float)) else "points: n/a")
            for k in ("due_at", "unlock_at", "lock_at"):
                if q.get(k):
                    bits.append(f"{k[:-3].replace('_', ' ')}: {fmt_dt(q[k])}")
            if q.get("allowed_attempts") is not None:
                bits.append(f"allowed attempts: {'unlimited' if q['allowed_attempts'] == -1 else q['allowed_attempts']}")
            bits.append(f"time limit: {q['time_limit']} min" if q.get("time_limit") else "time limit: none")
        meta = ("**Quiz:** " + "  |  ".join(bits)) if bits else ""
        link = f"\n\n[Open the assessment note](NOTE:asg:{q['assignment_id']})" if q.get("assignment_id") in self.asg else ""
        body = self.locked(it) or demote(it.get("body_md") or "")
        return f"## {self.title_h2(it['title'])}\n*[View on Canvas]({it['html_url']})*\n\n{meta}{link}\n\n{body}".rstrip()

    def sec_discussion(self, it):
        head = []
        if it.get("posted_at"):
            head.append(f"**Posted:** {fmt_dt(it['posted_at'])}" + (f" by {it['author']}" if it.get("author") else ""))
        if it.get("assignment_id") in self.asg:
            head.append(f"[Open the assessment note](NOTE:asg:{it['assignment_id']})")
        att = "".join(f"\n- [](FILE:{f})" for f in it.get("attachments", []))
        body = self.locked(it) or demote(it.get("body_md") or "")
        rep = self.replies_md(it)
        return (f"## {self.title_h2(it['title'])}\n*[View on Canvas]({it['html_url']})*\n\n{'  '.join(head)}\n\n{body}"
                f"{chr(10) + chr(10) + '**Attachments:**' + att if att else ''}".rstrip() + (f"\n\n{rep}" if rep else ""))

    def sec_item(self, it):
        t = it["type"]
        if t == "Page":
            return self.sec_page(it)
        if t == "Assignment":
            a = self.asg.get(it.get("assignment_id") or it.get("content_id"))
            if a:
                return self.card(a, it["title"])
            return f"## {self.title_h2(it['title'])}\n*[View on Canvas]({it['html_url']})*\n\n*Not available (HTTP {it.get('status')})*"
        if t == "Quiz":
            return self.sec_quiz(it)
        if t == "Discussion":
            return self.sec_discussion(it)
        if t == "File":
            return f"## {self.title_h2(it['title'])}\n\n[](FILE:{it['file_id']})"
        if t == "ExternalUrl":
            u = (it.get("external_url") or "").replace(" ", "%20").replace("(", "%28").replace(")", "%29")
            return f"## {self.title_h2(it['title'])}\n\n[{it['title']}]({u})"
        if t == "ExternalTool":
            return f"## {self.title_h2(it['title'])}\n*[Open on Canvas]({it['html_url']})* (external tool)"
        return f"## {self.title_h2(it['title'])}\n*[View on Canvas]({it.get('html_url', '')})*"

    # ---- one assessment note
    def rubric_md(self, a):
        crit = a.get("rubric") or []
        if not crit:
            return ""
        rs = a.get("rubric_settings") or {}
        s = a.get("submission") or {}
        ra = s.get("rubric_assessment") or {}
        marked = bool(ra) and s.get("score") is not None
        total = rs.get("points_possible", sum(c.get("points") or 0 for c in crit))
        out = [f"## Rubric\n\n**{rs.get('title') or 'Rubric'}**: {len(crit)} {'criterion' if len(crit) == 1 else 'criteria'}, {pts(total)} points."]

        def reached(c):
            r = ra.get(c.get("id")) or {}
            rt = c.get("ratings") or []
            hit = next((x for x in rt if r.get("rating_id") and x.get("id") == r.get("rating_id")), None)
            if not hit and isinstance(r.get("points"), (int, float)) and rt:
                cand = [x for x in rt if isinstance(x.get("points"), (int, float))]
                cand.sort(key=lambda x: -x["points"])
                for j, x in enumerate(cand):     # ranges run from a rating's points down to the next rating's points
                    lower = cand[j + 1]["points"] if j + 1 < len(cand) else float("-inf")
                    if r["points"] <= x["points"] + 1e-9 and r["points"] > lower + 1e-9:
                        hit = x
                        break
            return r, hit

        rows = ["| Criterion | Points |" + (" Your level | Your points |" if marked else ""),
                "| --- | --- |" + (" --- | --- |" if marked else "")]
        got_total = 0.0
        for c in crit:
            line = f"| {cell(c.get('description'))} | {pts(c.get('points'))} |"
            if marked:
                r, hit = reached(c)
                line += f" {cell(hit.get('description') if hit else '')} | {pts(r.get('points'))} |"
                if isinstance(r.get("points"), (int, float)):
                    got_total += r["points"]
            rows.append(line)
        if marked:
            rows.append(f"| **Total** | **{pts(total)}** | | **{pts(got_total)}** |")
        out.append("\n".join(rows))
        for i, c in enumerate(crit, 1):
            part = [f"### {i}. {cell(c.get('description'))} ({pts(c.get('points'))} points)"]
            if c.get("long_description"):
                part.append(demote(demote(plain_rubric(c["long_description"]))))
            r, hit = reached(c) if marked else ({}, None)
            rt = c.get("ratings") or []
            if rt:
                rows = ["| Level | Points | Descriptor |", "| --- | --- | --- |"]
                for j, x in enumerate(rt):
                    p = x.get("points")
                    if c.get("use_range") and isinstance(p, (int, float)) and p > 0:
                        lo = rt[j + 1].get("points") if j + 1 < len(rt) else 0
                        p = f"{pts(p)} to >{pts(lo)}"
                    name, pp = cell(x.get("description")), pts(p)
                    if hit is x:
                        name, pp = f"**✓ {name}**", f"**{pp}**"
                    rows.append(f"| {name} | {pp} | {cell(plain_rubric(x.get('long_description')))} |")
                part.append("\n".join(rows))
            if marked and (r.get("points") is not None or r.get("comments")):
                line = f"> **Your mark:** {pts(r.get('points'))} / {pts(c.get('points'))}" + (f" ({hit['description']})" if hit else "")
                if r.get("comments"):
                    line += "\n> **Marker comment:** " + re.sub(r"\n", "\n> ", r["comments"].strip())
                part.append(line)
            out.append("\n\n".join(part))
        return "\n\n".join(out)

    def annotation_lines(self, fb):
        anns = fb.get("annotations") or []
        tops = [x for x in anns if not x.get("inreplyto")]
        replies = {}
        for x in anns:
            if x.get("inreplyto"):
                replies.setdefault(x["inreplyto"], []).append(x)
        lines = []
        for x in sorted(tops, key=lambda x: (x.get("page") or 0, x.get("created_at") or "")):
            page = x.get("page")
            label = {"text": "comment", "freetext": "text box", "highlight": "highlight", "strikeout": "strikeout",
                     "underline": "underline", "ink": "drawing", "area": "box", "point": "comment"}.get(x.get("type"), x.get("type") or "mark")
            txts = [t for t in [x.get("contents")] + [r.get("contents") for r in replies.get(x.get("id"), [])] if t]
            who = x.get("author") or "Marker"
            base = f"- Page {page + 1 if isinstance(page, int) else '?'} · {label} by {who}"
            lines.append(base + (": " + " / ".join(f"\"{t.strip()}\"" for t in txts) if txts else ""))
        return lines

    def assessment_secs(self, a):
        s = a.get("submission") or {}
        code, label = self.status_of(a)
        g = next((x["g"] for x in self.grades.groups for it in x["items"] if it["a"]["id"] == a["id"]), None)
        if g is None:
            g = next((x for x in self.b.get("assignment_groups") or [] if x["id"] == a.get("assignment_group_id")), None)
        w = self.grades.weight_of(a)
        info = []
        if a.get("due_at"):
            info.append(f"Due {fmt_day(a['due_at'])} ({relative_days(a['due_at'])})")
        else:
            info.append("No due date on Canvas")
        if isinstance(a.get("points_possible"), (int, float)):
            info.append(f"{pts(a['points_possible'])} points")
        if g:
            gw = f", {pts(g.get('group_weight'))}% of the unit" if self.grades.weighted and g.get("group_weight") else ""
            info.append(f"group: {g.get('name')}{gw}")
        if w is not None and self.grades.weighted:
            info.append(f"this task: about {pct(w)} of the unit")
        if a.get("lock_at"):
            info.append(f"closes {fmt_day(a['lock_at'])}")
        if a.get("allowed_attempts") not in (None, -1):
            info.append(f"{a['allowed_attempts']} attempt{'s' if a['allowed_attempts'] != 1 else ''} allowed")
        types = [t.replace("_", " ") for t in a.get("submission_types") or [] if t != "none"]
        if types:
            info.append("submit as: " + ", ".join(types))
        head = [f"> [!info] " + " · ".join(info) + f"\n> [View on Canvas]({a['html_url']})"]
        if code == "marked":
            p = a.get("points_possible")
            frac = (s["score"] / p) if isinstance(p, (int, float)) and p else None
            grade = f" · grade {s['grade']}" if s.get("grade") not in (None, "", str(s.get("score")), pts(s.get("score"))) else ""
            head.append(f"> [!success] Marked: **{pts(s['score'])} / {pts(p)}**" + (f" ({pct(frac)})" if frac is not None else "") + grade +
                        (f" · marked {fmt_date(s.get('graded_at'))}" if s.get("graded_at") else ""))
        elif code == "submitted":
            head.append(f"> [!info] Submitted {fmt_day(s.get('submitted_at'))}" + (" · late" if s.get("late") else "") + " · not marked yet")
        elif code in ("missing", "overdue"):
            head.append(f"> [!warning] {label}.")
        elif code == "excused":
            head.append("> [!note] Excused.")
        elif code == "todo":
            head.append(f"> [!todo] Not submitted yet" + (f" · due {relative_days(a['due_at'])}" if a.get("due_at") else ""))
        secs = ["\n\n".join(head)]
        lock = f"*Locked on Canvas: {re.sub(r'<[^>]+>', '', a['lock_explanation'])}*" if a.get("locked") and a.get("lock_explanation") else ""
        body = demote(a.get("description_md") or "").strip()
        secs.append("## Brief\n\n" + (lock + ("\n\n" if lock and body else "") + body if (lock or body) else "*No description on Canvas.*"))
        rub = self.rubric_md(a)
        if rub:
            secs.append(rub)
        sub = []
        if s.get("submitted_at"):
            sub.append(f"**Submitted:** {fmt_dt(s['submitted_at'])}" + (f" (attempt {s['attempt']})" if s.get("attempt") else "") +
                       (" · late" if s.get("late") else ""))
        for fid in s.get("files") or []:
            sub.append(f"- [](FILE:{fid})")
        if s.get("url"):
            sub.append(f"- Link submitted: <{s['url']}>")
        if s.get("body_md"):
            sub.append("**Text you submitted:**\n\n" + demote(s["body_md"]))
        for h in s.get("history") or []:
            sub.append(f"- Earlier attempt {h.get('attempt')}: {fmt_dt(h.get('submitted_at')) or 'no date'}" +
                       (": " + ", ".join(h.get("files") or []) if h.get("files") else ""))
        if sub:
            secs.append("## Your submission\n\n" + "\n".join(sub))
        fb = []
        cm = s.get("comments") or []
        if cm:
            fb.append("### Comments")
            for c in cm:
                who = c.get("author") or "Comment"
                txt = re.sub(r"\n", "\n> ", (c.get("comment") or "").strip())
                extra = "".join(f"\n> - [](FILE:{f})" for f in c.get("attachments") or [])
                media = f"\n> [Media comment]({c['media']['url']})" if (c.get("media") or {}).get("url") else ""
                fb.append(f"> **{who}** · {fmt_dt(c.get('created_at'))}\n> {txt}{extra}{media}".rstrip())
        for fid in s.get("files") or []:
            key = f"{s.get('id')}-{fid}"
            f = self.feedback.get(key)
            if not f:
                continue
            lines = self.annotation_lines(f)
            name = (self.b.get("files", {}).get(fid) or {}).get("display_name") or f"file {fid}"
            if lines or f.get("pdf"):
                fb.append(f"### Annotations on {name}")
                if f.get("pdf"):
                    fb.append(f"[Marked-up PDF](PATH:{urllib.parse.quote(f['pdf'])})")
                if lines:
                    fb.append("\n".join(lines))
        if fb:
            secs.append("## Feedback\n\n" + "\n\n".join(fb))
        return secs

    def assessment_parts(self, a):
        secs = self.assessment_secs(a)
        return [("lead", secs[0])] + [("part", x) for x in secs[1:]]

    # ---- build
    def build(self):
        b = self.b
        groups, order = {}, []
        for m in sorted(b.get("modules") or [], key=lambda m: m.get("position") or 0):
            k = self.module_key(m)
            gk = (k["dir"], k["key"])
            if gk not in groups:
                groups[gk] = {**k, "modules": []}
                order.append(gk)
            groups[gk]["modules"].append(m)
        n = 0
        for gk in order:
            g = groups[gk]
            if g["kind"] == "module":
                n += 1
                g["title_numbered"] = f"{n:02d} {g['title']}"
            secs, count, outline = [], 0, []
            for m in g["modules"]:
                for it in m["items"]:
                    if it["type"] == "SubHeader":
                        secs.append(("sub", f"> **{it['title'].strip()}**"))
                        continue
                    secs.append(("sec", self.sec_item(it)))
                    outline.append(it["title"].strip())
                    count += 1
            if len(outline) >= 4:
                lead = "In this week" if g["kind"] == "week" else "In this module"
                secs.insert(0, ("lead", f"> [!abstract] {lead}\n" + "\n".join(f"> - {cell(x)}" for x in outline)))
            self.notes.append({"key": g["key"], "kind": g["kind"], "dir": g["dir"],
                               "title": g["title"] if g["kind"] == "week" else g["title_numbered"],
                               "source": g["title"], "module_ids": [m["id"] for m in g["modules"]],
                               "slugs": {it["page_url"] for m in g["modules"] for it in m["items"] if it.get("page_url")},
                               "nums": g.get("nums"), "count": count, "secs": secs,
                               "fm": {"easel": g["kind"], "unit": self.u.code,
                                      **({"week": g["nums"][0]} if g["kind"] == "week" else {}),
                                      "canvas": f"{ORIGIN}/courses/{self.cid}/modules"}})

        c = b["course"]
        info = [f"**Course:** {c['name']}  |  **Code:** {c.get('course_code')}  |  **Canvas id:** {self.cid}"]
        if c.get("term"):
            info.append(f"**Term:** {c['term']}")
        ci = ["## Course\n*[View on Canvas](%s/courses/%s)*\n\n%s" % (ORIGIN, self.cid, "\n\n".join(info))]
        staff = b.get("staff")
        if staff:
            rows = ["| Name | Role |", "| --- | --- |"] + [f"| {cell(p['name'])} | {cell(', '.join(p.get('roles') or []))} |"
                                                         for p in sorted(staff, key=lambda p: (p.get('sortable_name') or p['name']).lower())]
            ci.append("## Teaching staff\n\nNames and roles from Canvas. Canvas does not show staff emails to students; "
                      "look for them on the unit's own pages.\n\n" + "\n".join(rows))
        elif c.get("teachers"):
            ci.append("## Teaching staff\n\n" + ", ".join(c["teachers"]))
        if b.get("groups"):
            ci.append("## Your groups\n\n" + "\n".join(f"- **{cell(g['name'])}**: " + (", ".join(g.get('members') or []) or "no members listed")
                                                     for g in b["groups"]))
        tools = [t for t in c.get("tabs") or [] if isinstance(t, dict) and t.get("type") == "external" and t.get("html_url")]
        if tools:
            ci.append("## Canvas tools\n\n" + " · ".join(f"[{t['label']}]({t['html_url']})" for t in tools))
        syl = b.get("syllabus_md") or ""
        if syl.strip():
            ci.append(f"## Syllabus\n*[View on Canvas]({ORIGIN}/courses/{self.cid}/assignments/syllabus)*\n\n{demote(syl)}".rstrip())
        self.special("course_info", "1 Course Info", "00 Course Info", ci, kind="part")

        anns = sorted(b.get("announcements") or [], key=lambda a: a.get("posted_at") or "", reverse=True)
        ann_secs = []
        for a in anns:
            att = "".join(f"\n- [](FILE:{f})" for f in a.get("attachments", []))
            ann_secs.append(f"## {self.title_h2(a['title'])}\n*Posted {fmt_dt(a['posted_at'])}" + (f" by {a['author']}" if a.get("author") else "")
                            + f"  |  [View on Canvas]({a['html_url']})*\n\n{demote(a.get('message_md') or '')}"
                            + (f"\n\n**Attachments:**{att}" if att else ""))
        self.special("announcements", "1 Course Info", "Announcements", ann_secs or ["*No announcements on Canvas.*"])

        inbox = sorted(b.get("inbox") or [], key=lambda c: c.get("last_at") or "", reverse=True)
        had_inbox = any(n.get("key") == "inbox" for n in self.u.old.get("notes", []))
        if inbox or had_inbox:
            secs = []
            for cv in inbox:
                msgs = []
                for m in cv.get("messages") or []:
                    txt = re.sub(r"\n", "\n> ", (m.get("body") or "").strip())
                    att = "".join(f"\n> - [](FILE:{f})" for f in m.get("attachments") or [])
                    msgs.append(f"> **{m.get('author') or 'Unknown'}**{' (staff)' if m.get('staff') else ''} · {fmt_dt(m.get('created_at'))}\n> {txt}{att}")
                secs.append(f"## {self.title_h2(cv.get('subject'))}\n\n" + "\n\n".join(msgs))
            self.special("inbox", "1 Course Info", "Inbox", secs or ["*No Inbox messages from teaching staff for this unit.*"],
                         lead="Canvas Inbox conversations for this unit that include a message from teaching staff. easel reads them without marking them as read.")

        xp = sorted(b.get("extra_pages") or [], key=lambda p: (not p.get("front_page"), (p.get("title") or "").lower()))
        if xp:
            self.special("other_pages", "1 Course Info", "Pages not in any module",
                         [self.sec_page(p) + ("\n\n*This is the course home page.*" if p.get("front_page") else "") for p in xp])
        xd = sorted(b.get("extra_discussions") or [], key=lambda d: d.get("posted_at") or "")
        if xd:
            self.special("other_discussions", "1 Course Info", "Discussions not in any module", [self.sec_discussion(d) for d in xd])
        xf = [f for f in (b.get("extra_files") or []) if f in b.get("files", {})]
        if xf:
            xf.sort(key=lambda f: (b["files"][f].get("display_name") or "").lower())
            self.special("course_files", "1 Course Info", "Course files not linked anywhere",
                         ["## Files\n\nThese files are in the course Files area on Canvas. No module, page or announcement links to them.\n"
                          + "".join(f"\n- [](FILE:{f})" for f in xf)])

        for a in sorted(b.get("assignments") or [], key=asg_order):
            if a.get("published") is False:
                continue
            s = a.get("submission") or {}
            code, _ = self.status_of(a)
            fm = {"easel": "assessment", "unit": self.u.code, "canvas": a["html_url"]}
            if a.get("due_at"):
                fm["due"] = (parse_dt(a["due_at"]) or NOW).strftime("%Y-%m-%d %H:%M")
            if isinstance(a.get("points_possible"), (int, float)):
                fm["points"] = a["points_possible"]
            fm["status"] = code
            if s.get("score") is not None:
                fm["score"] = s["score"]
            if s.get("submitted_at"):
                fm["submitted"] = (parse_dt(s["submitted_at"]) or NOW).strftime("%Y-%m-%d %H:%M")
            note = {"key": f"asg:{a['id']}", "kind": "assessment", "dir": "2 Assessments", "asg_id": a["id"],
                    "title": a["name"].strip(), "source": a["name"].strip(), "module_ids": [], "slugs": set(), "nums": None,
                    "count": 1, "secs": self.assessment_parts(a), "fm": fm,
                    "file_name": clean_name(UNIT_PREFIX.sub("", a["name"]).strip() or a["name"])}
            self.asg_note[a["id"]] = note
            self.notes.append(note)

        self.special("grades", "2 Assessments", "Grades", self.grades_secs(), fm_extra=self.grades_fm(), kind="part")
        return self

    def special(self, key, d, title, secs, lead=None, fm_extra=None, kind="sec"):
        body = [("lead", lead)] if lead else []
        self.notes.append({"key": key, "kind": "special", "dir": d, "title": title, "source": title, "module_ids": [],
                           "slugs": set(), "nums": None, "count": len(secs),
                           "secs": body + [(kind, s) for s in secs],
                           "fm": {"easel": key.replace("_", "-"), "unit": self.u.code, **(fm_extra or {})}})

    # ---- the Grades note
    def grades_fm(self):
        cur = self.grades.total()
        fm = {}
        if cur is not None:
            fm["estimate"] = pct(cur)
            band = band_of(self.scheme, cur)
            if band:
                fm["band"] = band
        return fm

    def grades_secs(self):
        G, sc = self.grades, self.scheme
        hidden = (self.b.get("course") or {}).get("hide_final_grades")
        cur = G.total()
        floor = G.total(fill=0.0, empty_fill=0.0)
        ceil = G.total(fill=1.0, empty_fill=1.0)
        out = []
        note = ("Canvas hides the unit total from students in this unit. " if hidden else "") + \
            ("The figures below are easel's calculation from your released marks and the weights on the Canvas Grades tab, "
             "including drop rules. Canvas and your unit outline decide your real result.")
        head = [f"> [!note] {note}"]
        if cur is not None:
            band = band_of(sc, cur)
            head.append(f"> [!success] Average on marked work so far: **{pct(cur)}**" + (f" · {band}" if band else ""))
        else:
            head.append("> [!info] No marks released yet.")
        out.append("\n\n".join(head))
        if floor is not None and ceil is not None and G.has_unmarked():
            out.append(f"## Where you stand\n\n- Secured already, if you score zero on everything left: **{pct(floor)}**\n"
                       f"- Highest still possible: **{pct(ceil)}**")
        if sc and G.has_unmarked() and floor is not None:
            rows = ["| Grade | Needs | You need on the remaining work |", "| --- | --- | --- |"]
            for name, v in sc["data"]:
                if v <= 0:
                    continue
                n = G.need(v)
                txt = "already secured" if n == "secured" else "out of reach" if n == "out of reach" else (f"about {pct(n)}" if n is not None else "n/a")
                rows.append(f"| {cell(name)} | {pct(v)} | {txt} |")
            out.append(f"## What you need\n\nGrade scale: {sc['title']} (from {sc['source']}). \"You need\" assumes the same score on every remaining task.\n\n" + "\n".join(rows))
        elif not sc:
            out.append("## What you need\n\nCanvas does not show this unit's grade scale. Tell easel your university's scale once and this section fills in.")
        rows = ["| Group | Weight | Marked | Your marks | Counted | Group average |", "| --- | --- | --- | --- | --- | --- |"]
        for grp in G.groups:
            e, p = G.group_result(grp, None)
            marked = sum(1 for it in grp["items"] if it["score"] is not None)
            raw_e = sum(it["score"] for it in grp["items"] if it["score"] is not None)
            raw_p = sum(it["points"] for it in grp["items"] if it["score"] is not None)
            rule = []
            r = grp["rules"]
            if r.get("drop_lowest"):
                rule.append(f"drops lowest {r['drop_lowest']}")
            if r.get("drop_highest"):
                rule.append(f"drops highest {r['drop_highest']}")
            name = cell(grp["g"].get("name")) + (f" ({', '.join(rule)})" if rule else "")
            weight = f"{pts(grp['weight'])}%" if G.weighted else "by points"
            counted = f"{pts(e)} / {pts(p)}" if (e, p) != (raw_e, raw_p) else "all"
            rows.append(f"| {name} | {weight} | {marked} of {len(grp['items'])} | {pts(raw_e)} / {pts(raw_p)} | {counted} | {pct(e / p) if p else '-'} |")
        out.append("## By group\n\n" + ("Canvas weights the unit total by group." if G.weighted else "Canvas adds up points across all assessments.") + "\n\n" + "\n".join(rows))
        checks = []
        for a in sorted(self.b.get("assignments") or [], key=asg_order):
            m = re.search(r"\((\d+(?:\.\d+)?)\s*%\)", a.get("name") or "")
            w = G.weight_of(a)
            if m and w is not None and abs(float(m.group(1)) / 100 - w) > 0.01:
                checks.append(f"| [{lbl(a['name'])}](NOTE:asg:{a['id']}) | {m.group(1)}% | {pct(w)} |")
        if checks:
            out.append("## Check the weights\n\nThese names state a weight that differs from the weight Canvas calculates from points and group "
                       "weights. easel's figures above follow Canvas. Your unit outline decides which one counts.\n\n"
                       "| Assessment | Name says | Canvas counts it as |\n| --- | --- | --- |\n" + "\n".join(checks))
        rows = ["| Assessment | Due | Status | Mark | % |", "| --- | --- | --- | --- | --- |"]
        for a in sorted(self.b.get("assignments") or [], key=asg_order):
            if a.get("published") is False:
                continue
            s = a.get("submission") or {}
            code, label = self.status_of(a)
            p = a.get("points_possible")
            mark = mark_text(a)
            frac = pct(s["score"] / p) if s.get("score") is not None and isinstance(p, (int, float)) and p else ""
            rows.append(f"| [{lbl(a['name'])}](NOTE:asg:{a['id']}) | {fmt_date(a.get('due_at')) or 'no date'} | {label} | {mark} | {frac} |")
        out.append("## Every assessment\n\n" + "\n".join(rows))
        return out

    # ---- choose paths (keep existing names)
    def assign_paths(self):
        self.tidy_delete = []
        ex = self.existing_notes() if self.T else []
        self.ex_by_path = {str(e["path"]): e for e in ex}
        old_by_key = {}
        for nt in self.u.old.get("notes", []):
            for mid in nt.get("module_ids", []):
                old_by_key[mid] = nt.get("path")
            if nt.get("key"):
                old_by_key[nt["key"]] = nt.get("path")

        def take(e):
            e["used"] = True
            return e["path"]

        def match(note):
            ours = [e for e in ex if e["ours"] and not e["used"]]
            for mid in note["module_ids"] or [note["key"]]:
                p = old_by_key.get(mid)
                if p:
                    for e in ours:
                        if e["path"].relative_to(self.T).as_posix() == p:
                            return take(e)
            if note["kind"] == "assessment":
                return None
            if note["kind"] == "week":
                a, b = note["nums"]
                for e in ours:
                    m = WEEK_RE.match(e["path"].stem) or WEEK_RE.match(str(fm_value(e["fm"], "source_folder") or ""))
                    if e["dir"] == "3 Weeks" and m and int(m.group(1)) == a and (int(m.group(2)) if m.group(2) else None) == b:
                        return take(e)
            if note["kind"] == "special":
                names = {"course_info": ["courseinfo"], "announcements": ["announcements"], "inbox": ["inbox"], "grades": ["grades"],
                         "other_pages": ["pagesnotinanymodule"], "other_discussions": ["discussionsnotinanymodule"],
                         "course_files": ["coursefilesnotlinkedanywhere"]}.get(note["key"], [])
                for e in ours:
                    if norm(re.sub(r"^\d+\s+", "", e["path"].stem)) in names and e["dir"] == note["dir"]:
                        return take(e)
                return None
            if note["slugs"]:
                best, score = None, 0
                for e in ours:
                    s = len(note["slugs"] & e["slugs"])
                    if s > score:
                        best, score = e, s
                if best and score * 2 >= min(len(note["slugs"]), max(1, len(best["slugs"]))):
                    return take(best)
            for e in ours:
                if norm(re.sub(r"^\d+\s+", "", e["path"].stem)) == norm(note["source"]) or \
                        norm(str(fm_value(e["fm"], "source_folder") or "")) in (norm(note["source"]), norm(note["title"])):
                    return take(e)
            import difflib
            target = norm(note["source"].replace("&", "and"))
            for e in ours:
                if e["dir"] == note["dir"] and difflib.SequenceMatcher(None, norm(re.sub(r"^\d+\s+", "", e["path"].stem).replace("&", "and")), target).ratio() >= 0.85:
                    return take(e)
            return None

        taken = set()
        user_paths = {str(e["path"]).lower() for e in ex if not e["ours"]}
        for note in sorted(self.notes, key=lambda n: {"week": 0, "special": 1, "module": 2, "assessment": 3}[n["kind"]]):
            p = match(note) if self.T else None
            note["existing"] = p is not None
            stem = short_name(note.get("file_name") or clean_name(note["title"]))
            canon = self.T / note["dir"] / f"{stem}.md"
            if p is None:
                k = 2
                while str(canon).lower() in taken or str(canon).lower() in user_paths or \
                        (canon.exists() and str(canon) in self.ex_by_path and self.ex_by_path[str(canon)]["used"]):
                    extra = f" ({note['asg_id']})" if note["kind"] == "assessment" and k == 2 else f" ({k})"
                    canon = self.T / note["dir"] / f"{stem}{extra}.md"
                    k += 1
                if canon.exists() and str(canon) in self.ex_by_path and self.ex_by_path[str(canon)]["ours"]:
                    self.ex_by_path[str(canon)]["used"] = True
                    note["existing"] = True
            if p and self.u.tidy and p != canon:
                note["rename_from"] = p
                p = canon
            note["path"] = p if p else canon
            taken.add(str(note["path"]).lower())
        self.stale = [e for e in ex if e["ours"] and not e["used"]]
        self.user_notes = [e["path"] for e in ex if not e["ours"]]
        return self

    # ---- files
    def note_folder(self, note):
        return note["key"] if note["kind"] == "week" else Path(note["path"]).stem

    def plan_files(self):
        T, files = self.T, self.b.get("files") or {}
        order = []
        for note in self.notes:
            text = "\n".join(s for _, s in note["secs"] if s)
            for fid in re.findall(r"\(FILE:(\d+)\)", text):
                if fid not in self.file_refs:
                    self.file_refs[fid] = note
                    order.append(fid)
        disk = {}
        if (T / "Files").is_dir():
            for f in (T / "Files").rglob("*"):
                if f.is_file() and f.name != ".DS_Store":
                    try:
                        disk.setdefault((f.name, f.stat().st_size), f)
                    except OSError:
                        pass
        old_paths = {}
        for f in self.u.old.get("files", []):
            p = f.get("path") or (str(Path(f["folder"] if str(f.get("folder", "")).startswith("Files") else "Files/" + f.get("folder", "")) / f["name"]) if f.get("name") else None)
            if p:
                old_paths[str(f["id"])] = T / p
        claimed = set()
        for fid in order:
            meta = files.get(fid, {})
            note = self.file_refs[fid]
            role = meta.get("role")
            base = T / "Files" / self.note_folder(note)
            if role == "submission":
                folder = base / "Your submission"
            elif role == "feedback":
                folder = base / "Feedback"
            elif role == "inbox":
                folder = T / "Files" / "Inbox"
            else:
                folder = base
            if meta.get("status") or not meta.get("display_name"):
                self.fplan[fid] = {"action": "dead", "status": meta.get("status")}
                continue
            ct = meta.get("content_type") or ""
            if ct.startswith("image/") and role not in ("submission", "feedback"):
                self.fplan[fid] = {"action": "image"}
                continue
            if not self.u.media and role not in ("submission", "feedback") and (ct.startswith(("video/", "audio/")) or (meta.get("size") or 0) > MAX_BYTES):
                self.fplan[fid] = {"action": "media", "size": meta.get("size") or 0}
                continue
            name, size = clean_file_name(meta["display_name"]), meta.get("size")
            canon = folder / name
            op = old_paths.get(fid)
            if op and op.exists():
                if op.stat().st_size == size:
                    self.fplan[fid] = self.tidy_file(op, canon, size) if self.u.tidy else {"action": "reuse", "path": op}
                    continue
                canvas_t = (parse_dt(meta.get("updated_at")) or NOW).timestamp()
                if canvas_t <= op.stat().st_mtime:
                    self.fplan[fid] = {"action": "reuse", "path": op, "local_differs": True}
                    continue
                st, ext = os.path.splitext(op.name)
                self.fplan[fid] = {"action": "download", "path": op.with_name(f"{st} (updated {TODAY}){ext}"), "changed": str(op)}
                continue
            if canon.exists() and canon.stat().st_size == size:
                self.fplan[fid] = {"action": "reuse", "path": canon}
                continue
            hit = disk.get((name, size)) or disk.get((meta["display_name"], size))
            if hit:
                self.fplan[fid] = self.tidy_file(hit, canon, size) if self.u.tidy else {"action": "reuse", "path": hit}
                continue
            dest = canon
            if dest.exists() or str(dest).lower() in claimed:
                st, ext = os.path.splitext(name)
                dest = dest.with_name(f"{st}-{fid}{ext}")
            claimed.add(str(dest).lower())
            self.fplan[fid] = {"action": "download", "path": dest}
        return self

    def tidy_file(self, cur, canon, size):
        files_dir = (self.T / "Files").resolve()
        if cur == canon or files_dir not in Path(cur).resolve().parents:
            return {"action": "reuse", "path": cur}
        if canon.exists():
            if canon.stat().st_size == size and filecmp.cmp(cur, canon, shallow=False):
                return {"action": "reuse", "path": canon}
            return {"action": "reuse", "path": cur}
        return {"action": "reuse", "path": canon, "move_from": cur}

    def need(self):
        return [fid for fid, p in self.fplan.items() if p["action"] == "download"]

    # ---- annotated feedback: which submission files to open in the document viewer
    def viewer_keys(self, candidates):
        if not self.u.feedback_enabled:
            return []
        keys = []
        for c in candidates or []:
            if not (c.get("graded_at") or c.get("posted_at")):
                continue
            prev = self.feedback.get(c["key"])
            graded = parse_dt(c.get("graded_at") or c.get("posted_at"))
            recent = graded and (NOW - graded) < timedelta(days=21)
            stale_check = prev and (NOW - (parse_dt(prev.get("checked_at")) or NOW)) > timedelta(hours=20)
            if self.u.refresh_feedback or not prev or prev.get("graded_at") != c.get("graded_at") or \
                    prev.get("posted_at") != c.get("posted_at") or (recent and stale_check):
                keys.append(c["key"])
        return keys


def plain_rubric(s):
    s = re.sub(r"<br\s*/?>\s*", "\n", (s or "").replace("\r\n", "\n").replace("\r", "\n"), flags=re.I)
    s = re.sub(r"</?(p|div)[^>]*>", "\n", s, flags=re.I)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"<[^>]+>", "", s)).strip()


def mark_text(a):
    s = a.get("submission") or {}
    if s.get("score") is None and not s.get("grade"):
        return ""
    p = a.get("points_possible")
    if not isinstance(p, (int, float)) or p <= 0 or a.get("grading_type") in ("pass_fail", "letter_grade", "gpa_scale"):
        return str(s.get("grade") or pts(s.get("score")))
    return f"{pts(s['score'])} / {pts(p)}"


def natural(s):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", s or "")]


def asg_order(a):
    return (a.get("due_at") is None, a.get("due_at") or "", natural(a.get("name")))


def clean_file_name(name):
    base, ext = os.path.splitext(name or "file")
    return (clean_name(base) or "file") + re.sub(r"[^\w.]", "", ext)[:12]


# ---------------------------------------------------------------- writing
def resolve_links(text, note_dir: Path, planner: Planner, received):
    files = planner.b.get("files") or {}
    T = planner.T

    def rep_file(m):
        label, fid = m.group(1), m.group(2)
        meta = files.get(fid, {})
        p = planner.fplan.get(fid, {})
        label = label or meta.get("display_name") or f"file {fid}"
        label = label.replace("[", "(").replace("]", ")").replace("\n", " ")
        ok = p.get("action") == "reuse" or (p.get("action") == "download" and fid in received)
        if ok:
            return f"[{label}]({link_path(note_dir, Path(p['path']))})"
        return f"[{label}]({ORIGIN}/courses/{planner.cid}/files/{fid})"

    def rep_note(m):
        label, key = m.group(1), m.group(2)
        nt = next((n for n in planner.notes if n["key"] == key), None)
        if not nt:
            return label
        return f"[{label}]({link_path(note_dir, Path(nt['path']))})"

    def rep_path(m):
        label, rel = m.group(1), urllib.parse.unquote(m.group(2))
        return f"[{label}]({link_path(note_dir, T / rel)})"
    text = re.sub(r"\[((?:[^\]\\]|\\.)*)\]\(FILE:(\d+)\)", rep_file, text)
    text = re.sub(r"\[([^\]]*)\]\(NOTE:([^)]+)\)", rep_note, text)
    text = re.sub(r"\[([^\]]*)\]\(PATH:([^)]+)\)", rep_path, text)
    return text


def note_body(note):
    parts, prev = [], None
    for kind, s in note["secs"]:
        if not s:
            continue
        if parts and prev == "sec" and kind == "sec":
            parts.append("\n\n---\n\n")
        elif parts:
            parts.append("\n\n")
        parts.append(s)
        prev = kind
    body = "".join(parts) if parts else "*Nothing published on Canvas yet.*"
    return f"# {note['title']}\n\n{body.rstrip()}\n"


def render_fm(items, user_blocks, updated):
    lines = []
    for k, v in items.items():
        if v is None or v == "":
            continue
        lines.append(f"{k}: {yaml_val(v)}")
    lines.append(f"updated: {updated}")
    for k, ls in user_blocks:
        lines.extend(ls)
    return "---\n" + "\n".join(lines) + "\n---\n\n"


def write_note(unit, planner, note, received, old_sha, legacy_sha, was_edited=False):
    """Write one note. Keep the student's frontmatter keys and the text under My notes.
    A note the student edited stays theirs on every later run, until they ask for --reset-edited.
    Returns 'new', 'written', 'unchanged' or 'edited'."""
    path = Path(note["path"])
    gen = resolve_links(note_body(note), path.parent, planner, received)
    note["gen_sha"] = sha(gen)
    note["edited"] = False
    mine, user_blocks, cur = "", [], None
    if path.exists():
        cur = read_text(path)
        fm, body = split_frontmatter(cur)
        cur_gen, cur_mine = split_my_notes(body)
        if was_edited:
            edited = True
        elif old_sha is not None:
            edited = sha(cur_gen) != old_sha
        elif legacy_sha is not None:       # written by v3: no My notes section, hash over the whole file
            same_run = abs(path.stat().st_mtime - unit.manifest_mtime) < 120
            edited = not (raw_sha(cur) == legacy_sha or raw_sha(cur.replace("\r\n", "\n").replace("\r", "\n")) == legacy_sha or same_run)
            if cur_mine is not None:
                edited = edited and sha(cur_gen) != legacy_sha
        else:
            # No record of what easel wrote here: keep the file unless it already matches the Canvas version.
            edited = sha(cur_gen) != sha(gen)
        if edited and unit.reset_edited:
            keep = unit.target / ".easel" / "backups" / f"edited-{TODAY}" / path.relative_to(unit.target)
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(lp(path), lp(keep))
            edited = False
            unit.result.setdefault("reset", []).append(path.name)
        if edited:
            note["gen_sha"] = old_sha if old_sha is not None else legacy_sha
            note["edited"] = True
            return "edited"
        mine = cur_mine or ""
        user_blocks = [(k, ls) for k, ls in fm_blocks(fm) if k not in OWNED_FM]
    fm_items = dict(note.get("fm") or {})
    tail = f"\n{MY_NOTES}\n\n{MY_NOTES_HINT}\n" + (f"\n{mine}\n" if mine.strip() else "")
    old_updated = None
    if cur is not None:
        fm_old, _ = split_frontmatter(cur)
        old_updated = fm_value(fm_old, "updated")
        candidate = render_fm(fm_items, user_blocks, old_updated or TODAY) + gen + tail
        if normalize(candidate) == normalize(cur):
            return "unchanged"
    text = render_fm(fm_items, user_blocks, TODAY) + gen + tail
    write_text(path, text)
    return "written" if cur is not None else "new"


def check_links(T: Path):
    ok = bad = 0
    broken, refs, leftovers = [], set(), []
    for d in MANAGED[:3] + ["."]:
        base = T / d
        if not base.is_dir():
            continue
        for md in (base.glob("*.md") if d == "." else base.rglob("*.md")):
            if d == "." and md.name != "INDEX.md":
                continue
            t = read_text(md)
            if re.search(r"\((?:FILE|NOTE|PATH):[^)]+\)", t):
                leftovers.append(md.name)
            for m in re.finditer(r"\]\(([^)\s]+)\)", t):
                u = m.group(1).strip("<>")
                if u.startswith(("http", "mailto:", "#", "$", "tel:")):
                    continue
                p = (md.parent / urllib.parse.unquote(u.split("#")[0])).resolve()
                if p.exists():
                    ok += 1
                    refs.add(p)
                else:
                    bad += 1
                    broken.append(f"{md.name} -> {u}")
    orphans = [f.relative_to(T).as_posix() for f in (T / "Files").rglob("*")
               if f.is_file() and f.name != ".DS_Store" and f.resolve() not in refs] if (T / "Files").is_dir() else []
    return ok, bad, broken, leftovers, orphans


def week_status(planner):
    pub, empty, locked = [], [], []
    for n in planner.notes:
        if n["kind"] != "week":
            continue
        txt = "\n".join(s for k, s in n["secs"] if k == "sec" and s)
        if n["count"] == 0:
            empty.append(n["key"])
        elif txt.count("*Locked on Canvas") >= n["count"]:
            locked.append(n["key"])
        else:
            pub.append(n["key"])
    s = f"Canvas has content up to **{pub[-1]}**." if pub else "Canvas has no week content yet."
    if empty:
        s += " Empty so far: " + ", ".join(empty) + "."
    if locked:
        s += " Locked: " + ", ".join(locked) + "."
    return s


def write_index(unit, planner, last_update_lines):
    T, b, P = unit.target, unit.bundle, planner
    c = b["course"]
    lines = []
    fm = {"easel": "unit", "unit": unit.code, "canvas": f"{ORIGIN}/courses/{c['id']}", "term": c.get("term")}
    upcoming = sorted((a for a in b.get("assignments") or [] if a.get("published") is not False and P.status_of(a)[0] in ("todo",)
                       and parse_dt(a.get("due_at")) and parse_dt(a["due_at"]) >= NOW), key=lambda a: a["due_at"])
    status = week_status(P)
    if upcoming:
        a = upcoming[0]
        status += f" Next due: [{lbl(a['name'])}](NOTE:asg:{a['id']}), {fmt_day(a['due_at'])} ({relative_days(a['due_at'])})."
    lines.append(f"# {c['name']}\n\n> [!info] {status}")
    cur = P.grades.total()
    if cur is not None:
        band = band_of(P.scheme, cur)
        lines.append(f"**Average on marked work (easel's estimate):** {pct(cur)}" + (f" · {band}" if band else "") + " · [Grades](NOTE:grades)")
    rows = ["| Assessment | Due | Status | Mark |", "| --- | --- | --- | --- |"]
    for a in sorted(b.get("assignments") or [], key=asg_order):
        if a.get("published") is False:
            continue
        s = a.get("submission") or {}
        rows.append(f"| [{lbl(a['name'])}](NOTE:asg:{a['id']}) | {fmt_date(a.get('due_at')) or 'no date'} | {P.status_of(a)[1]} | {mark_text(a)} |")
    if len(rows) > 2:
        lines.append("## Assessments\n\n" + "\n".join(rows))
    for d, title in (("3 Weeks", "Weeks"), ("1 Course Info", "Course info"), ("2 Assessments", "Assessment notes and modules")):
        ns = [n for n in P.notes if Path(n["path"]).parent.name == d and n["kind"] != "assessment"]
        if not ns:
            continue
        ns.sort(key=lambda n: Path(n["path"]).name)
        lines.append(f"## {title}\n\n" + "\n".join(f"- [{lbl(Path(n['path']).stem)}](NOTE:{n['key']})" + (f" · {n['count']} items" if n['kind'] in ('week', 'module') else "")
                                                     for n in ns))
    if last_update_lines:
        lines.append("## Last update\n\n" + "\n".join(f"- {x}" for x in last_update_lines))
    note = {"key": "index", "kind": "index", "title": c["name"], "secs": [], "path": T / "INDEX.md", "fm": fm}
    body = "\n\n".join(lines) + "\n"
    body = resolve_links(body, T, P, unit.received)
    old_fm, _ = split_frontmatter(read_text(T / "INDEX.md")) if (T / "INDEX.md").exists() else (None, "")
    user_blocks = [(k, ls) for k, ls in fm_blocks(old_fm) if k not in OWNED_FM and k != "title"]
    write_text(T / "INDEX.md", render_fm(fm, user_blocks, TODAY) + body)
    return note


# ---------------------------------------------------------------- changes since the last run
def diff_changes(old, P, b):
    ch = {"announcements": [], "edited": [], "added": [], "marks": [], "modules": []}
    oldmods = old.get("modules", [])
    old_items = {}
    for m in oldmods:
        for p in m.get("pages", m.get("items", [])):
            old_items[p.get("key") or p.get("slug")] = p.get("updated_at")
    old_mod_names = {norm(m.get("name")) for m in oldmods}
    for m in b.get("modules") or []:
        if oldmods and norm(m["name"]) not in old_mod_names:
            ch["modules"].append(m["name"].strip())
        for it in m["items"]:
            if it["type"] == "SubHeader":
                continue
            k = it.get("page_url") or f"{it['type']}:{it.get('content_id')}"
            if k in old_items:
                if it.get("updated_at") and old_items[k] and it["updated_at"] != old_items[k]:
                    ch["edited"].append((m["name"].strip(), it["title"].strip()))
            elif oldmods:
                ch["added"].append((m["name"].strip(), it["title"].strip()))
    old_asg = {a.get("id"): a for a in old.get("assignments", [])}
    for a in b.get("assignments") or []:
        o = old_asg.get(a["id"])
        s = a.get("submission") or {}
        if s.get("score") is not None and (o is None and old or (o is not None and not o.get("graded"))):
            ch["marks"].append(f"{short_title(a['name'])} {pts(s['score'])}/{pts(a.get('points_possible'))}")
    old_ann = {str(a.get("id")) for a in old.get("announcements", [])}
    if old.get("announcements") is not None:
        for a in b.get("announcements") or []:
            if str(a["id"]) not in old_ann:
                ch["announcements"].append(a["title"])
    return ch


# ---------------------------------------------------------------- v3 migration
def backup_v3(T: Path):
    """Zip the v3 notes and manifest before v4 writes anything. Files/ is left in place: v4 does not move or delete it."""
    dest = T / ".easel" / "backups"
    dest.mkdir(parents=True, exist_ok=True)
    z = dest / f"v3-notes-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in MANAGED[:3]:
            for f in (T / d).rglob("*") if (T / d).is_dir() else []:
                if f.is_file():
                    zf.write(f, f.relative_to(T).as_posix())
        for name in ("INDEX.md", ".canvas-manifest.json"):
            if (T / name).exists():
                zf.write(T / name, name)
    return z


# ---------------------------------------------------------------- finalize one unit
def finalize(unit: Unit, phase="main"):
    t0 = time.time()
    P, T, b = unit.plan, unit.target, unit.bundle
    res = unit.result
    if phase == "main":
        res.update({"moved": 0, "renamed": 0, "removed": [], "written": [], "new": [], "edited": [], "backup": None})
        if unit.old_format == 3 and not (T / ".easel" / "manifest.json").exists():
            res["backup"] = backup_v3(T)
        for p in P.fplan.values():
            src = p.get("move_from")
            if src and Path(src).exists() and not Path(p["path"]).exists():
                Path(p["path"]).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), p["path"])
                res["moved"] += 1
        for n in P.notes:
            src = n.get("rename_from")
            if src and Path(src).exists():
                dst = Path(n["path"])
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists() and not os.path.samefile(src, dst):
                    continue
                tmp = dst.with_name(dst.name + ".tidy-tmp")
                os.rename(src, tmp)
                os.rename(tmp, dst)
                res["renamed"] += 1
        for fid, src in unit.received.items():
            p = P.fplan[fid]
            dest = Path(p["path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                st, ext = os.path.splitext(dest.name)
                dest = dest.with_name(f"{st}-{fid}{ext}")
                p["path"] = dest
            shutil.move(str(src), lp(dest))
    old_notes = {x.get("path"): x for x in unit.old.get("notes", [])}
    targets = P.notes if phase == "main" else [n for n in P.notes if n.get("asg_id") in unit.feedback_asg]
    for n in targets:
        n["path"] = Path(n["path"])
        rel = n["path"].relative_to(T).as_posix()
        prev = old_notes.get(rel) or {}
        if phase != "main":
            old_sha, legacy, was_edited = n.get("gen_sha"), None, n.get("edited", False)
        elif unit.old_format == 4:
            old_sha, legacy, was_edited = prev.get("sha"), None, bool(prev.get("edited"))
        else:
            old_sha, legacy, was_edited = None, prev.get("sha"), False
        st = write_note(unit, P, n, unit.received, old_sha, legacy, was_edited)
        if st == "edited":
            if n["path"].name not in res["edited"]:
                res["edited"].append(n["path"].name)
        elif st in ("written", "new") and phase == "main":
            res["written" if st == "written" else "new"].append(n["path"].name)
    if phase == "main":
        # v3 notes that v4 replaces, such as "Assignments.md", go away when nobody edited them. The backup holds them.
        for e in P.stale:
            prev = old_notes.get(e["path"].relative_to(T).as_posix())
            if prev and prev.get("sha") and (raw_sha(e["text"]) == prev["sha"] or abs(e["path"].stat().st_mtime - unit.manifest_mtime) < 120 or
                                             sha(split_my_notes(split_frontmatter(e["text"])[1])[0]) == prev["sha"]):
                if unit.old_format == 3 and res.get("backup") or unit.old_format == 4:
                    e["path"].unlink()
                    res["removed"].append(e["path"].name)
    changes = diff_changes(unit.old, P, b) if unit.old else {}
    summary_lines = summary_for(unit, changes)
    write_index(unit, P, [f"{TODAY}: " + "; ".join(summary_lines[1:]) if len(summary_lines) > 1 else f"{TODAY}: no changes on Canvas"])
    manifest = {
        "version": 4, "easel": VERSION, "canvas": ORIGIN, "course_id": b["course"]["id"], "course_name": b["course"]["name"],
        "course_code": b["course"].get("course_code"), "scraped": TODAY, "scraped_at": b.get("scraped_at"),
        "notes": [{"key": n["key"], "path": Path(n["path"]).relative_to(T).as_posix(), "module_ids": n.get("module_ids") or [],
                   "sections": n.get("count", 0), "sha": n.get("gen_sha"), **({"edited": True} if n.get("edited") else {})} for n in P.notes],
        "modules": [{"id": m["id"], "name": m["name"], "items": [{"key": it.get("page_url") or f"{it['type']}:{it.get('content_id')}",
                     "type": it["type"], "title": it["title"], "updated_at": it.get("updated_at")} for it in m["items"] if it["type"] != "SubHeader"]}
                    for m in b.get("modules") or []],
        "files": [{"id": fid, "name": (b.get("files") or {}).get(fid, {}).get("display_name"), "path": Path(p["path"]).relative_to(T).as_posix(),
                   "size": (b.get("files") or {}).get(fid, {}).get("size"), "updated_at": (b.get("files") or {}).get(fid, {}).get("updated_at")}
                  for fid, p in P.fplan.items() if p.get("path") and (p["action"] == "reuse" or fid in unit.received)],
        "announcements": [{"id": a["id"], "title": a["title"], "posted_at": a["posted_at"]} for a in b.get("announcements") or []],
        "assignments": [{"id": a["id"], "name": a["name"], "due_at": a.get("due_at"), "updated_at": a.get("updated_at"),
                         "rubric_criteria": len(a.get("rubric") or []), "graded": (a.get("submission") or {}).get("score") is not None}
                        for a in b.get("assignments") or []],
        "feedback": P.feedback,
    }
    write_text(T / ".easel" / "manifest.json", json.dumps(manifest, indent=1, ensure_ascii=False))
    if phase == "main" and (T / ".canvas-manifest.json").exists() and res.get("backup"):
        (T / ".canvas-manifest.json").unlink()
    unit.timing["build_s"] = round(time.time() - t0, 1)
    unit.report = full_report(unit, changes)
    write_text(T / ".easel" / "report.txt", unit.report + "\n")
    unit.summary = "\n".join(summary_lines)
    unit.done = True


def user_paths(T: Path, P: Planner):
    return [x for x in T.iterdir() if x.name not in MANAGED_TOP and x.name != ".DS_Store"] + list(P.user_notes)


def short_title(name, unit=""):
    s = UNIT_PREFIX.sub("", name or "").strip(" -:|")
    s = re.sub(r"\s*\((?:submit here|[\d.]+%)\)\s*$", "", s, flags=re.I)
    s = re.sub(r"\s*(submission link|submit here!?|submission)\s*$", "", s, flags=re.I).strip(" -:|.")
    return s if len(s) <= 48 else s[:46].rstrip() + "…"


def summary_for(unit, changes):
    """One line per unit for the chat, plus the facts that need the student."""
    P, b = unit.plan, unit.bundle
    bits = []
    if changes.get("announcements"):
        n = len(changes["announcements"])
        bits.append(f"{n} new announcement{'s' if n != 1 else ''}")
    if changes.get("marks"):
        bits.append("marks released: " + ", ".join(changes["marks"][:3]) + (" and more" if len(changes["marks"]) > 3 else ""))
    weeks = sorted({m for m, _ in changes.get("edited", []) + changes.get("added", []) if WEEK_RE.match(m)})
    other = len({m for m, _ in changes.get("edited", []) + changes.get("added", [])} - set(weeks))
    if weeks:
        bits.append("changed: " + ", ".join(re.sub(r"^\s*(weeks?\s*\d+).*$", r"\1", w, flags=re.I).title() for w in weeks[:4]) +
                    (" and more" if len(weeks) > 4 else ""))
    if other:
        bits.append(f"{other} other module{'s' if other != 1 else ''} changed")
    fb = unit.result.get("feedback_saved") or []
    if fb:
        bits.append("annotated feedback saved for " + ", ".join(fb[:3]))
    if not unit.old:
        bits.append(f"first run: {len(P.notes)} notes")
    if not bits and unit.result.get("written"):
        names = [os.path.splitext(x)[0] for x in unit.result["written"][:3]]
        bits.append("updated: " + ", ".join(names) + (" and more" if len(unit.result["written"]) > 3 else ""))
    if not bits:
        bits.append("no changes on Canvas")
    cur = P.grades.total()
    if cur is not None:
        band = band_of(P.scheme, cur)
        bits.append(f"average on marked work {pct(cur)}" + (f" ({band})" if band else ""))
    lines = [f"{unit.code}: " + "; ".join(bits) + "."]
    for x in bits:
        lines.append(x)
    return lines


def full_report(unit, changes):
    P, T, b = unit.plan, unit.target, unit.bundle
    ok, bad, broken, leftovers, orphans = check_links(T)
    after = snapshot(user_paths(T, P))
    before = unit.before
    changed_user = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    unit.checks = {"links_ok": ok, "links_bad": bad, "leftovers": len(leftovers), "user_changed": len(changed_user), "orphans": len(orphans)}
    acts = {}
    for p in P.fplan.values():
        acts[p["action"]] = acts.get(p["action"], 0) + 1
    c = b["course"]
    res = unit.result
    L = [f"== {unit.code} | {c['id']} {c['name']} | easel {VERSION} | {datetime.now().strftime('%Y-%m-%d %H:%M')}",
         f"notes: {len(P.notes)} ({len(res.get('new', []))} new, {len(res.get('written', []))} updated) | words {sum(words(chr(10).join(s for _, s in n['secs'] if s)) for n in P.notes):,}",
         f"files: {len(unit.received)} downloaded, {acts.get('reuse', 0)} already here, {len(unit.failed)} failed, {acts.get('dead', 0)} gone from Canvas, "
         f"{acts.get('image', 0)} images and {acts.get('media', 0)} video, audio or large files left as Canvas links"]
    if res.get("written") and len(res["written"]) <= 12:
        L.append("notes updated: " + ", ".join(res["written"]))
    if res.get("backup"):
        L.append(f"v3 notes backed up to {Path(res['backup']).relative_to(T).as_posix()}")
    for fid, p in P.fplan.items():
        if p.get("changed") and fid in unit.received:
            L.append(f"  file changed on Canvas, saved beside the old copy: {Path(p['path']).relative_to(T).as_posix()}")
    kept = [Path(p["path"]).relative_to(T).as_posix() for p in P.fplan.values() if p.get("local_differs")]
    if kept:
        L.append("  your copy differs from Canvas and is newer, kept yours: " + "; ".join(kept))
    if unit.failed:
        L.append("  failed downloads (left as Canvas links): " + ", ".join(f"{(b.get('files') or {}).get(k, {}).get('display_name', k)} [{v}]" for k, v in unit.failed.items()))
    if changes:
        for k, label in (("announcements", "new announcements"), ("marks", "marks released"), ("modules", "new modules")):
            if changes.get(k):
                L.append(f"{label}: " + "; ".join(changes[k][:20]))
        if changes.get("added"):
            L.append("new items: " + "; ".join(f"{m[:30]}: {t}" for m, t in changes["added"][:20]))
        if changes.get("edited"):
            L.append("edited on Canvas: " + "; ".join(f"{m[:30]}: {t}" for m, t in changes["edited"][:20]))
    L.append("status: " + week_status(P).replace("**", ""))
    rub = [a for a in b.get("assignments") or [] if a.get("rubric")]
    graded = [a for a in b.get("assignments") or [] if (a.get("submission") or {}).get("score") is not None]
    L.append(f"assessment: {len(b.get('assignments') or [])} assessments, {len(rub)} with a rubric, {len(graded)} marked, grade scale: "
             f"{(P.scheme or {}).get('title', 'none')}")
    fbs = unit.result.get("feedback_saved") or []
    if unit.viewer_keys:
        L.append(f"annotated feedback: {len(unit.viewer_keys)} files checked in the document viewer, {len(fbs)} saved"
                 + (f", problems: {'; '.join(unit.result.get('feedback_problems', [])[:5])}" if unit.result.get("feedback_problems") else ""))
    bad_api = {k: v for k, v in (b.get("api_status") or {}).items() if v not in (200, None)}
    if bad_api:
        L.append("  Canvas refused (HTTP status; this part is missing): " + ", ".join(f"{k} {v}" for k, v in bad_api.items()))
    cov = b.get("coverage") or {}
    if cov.get("words"):
        L.append(f"text coverage: {100 * (1 - cov['missing'] / cov['words']):.3f}% of {cov['words']:,} words the browser shows are in the notes"
                 + (f" ({cov['missing']} missing)" if cov["missing"] else ""))
        for pg in cov.get("pages", [])[:8]:
            L.append(f"  missing {pg['n']} on {pg['url']}: {' '.join(pg['missing'])}")
    L.append(f"checks: links {ok} ok / {bad} broken | placeholders left {len(leftovers)} | files not linked from a note {len(orphans)} | "
             f"your files changed {len(changed_user)} of {len(before)}")
    L += ["  BROKEN " + x for x in broken[:20]]
    L += ["  not linked " + x for x in orphans[:20]] + ([f"  ... {len(orphans) - 20} more"] if len(orphans) > 20 else [])
    L += ["  YOUR FILE CHANGED " + x for x in changed_user[:20]]
    if res.get("edited"):
        L.append("kept as you edited them: " + ", ".join(res["edited"]))
    if res.get("reset"):
        L.append(f"edited notes replaced with the Canvas version (your copies are in .easel/backups/edited-{TODAY}): " + ", ".join(res["reset"]))
    if res.get("removed"):
        L.append("old easel notes removed (in the backup): " + ", ".join(res["removed"]))
    stale = [e["path"].name for e in P.stale if e["path"].exists()]
    if stale:
        L.append("old easel notes left in place (module gone from Canvas, or edited): " + ", ".join(stale))
    if P.user_notes:
        L.append("your own notes inside easel folders (left alone): " + ", ".join(p.name for p in P.user_notes))
    L.append(f"time: fetch {b.get('fetch_ms', 0) / 1000:.1f}s, files {unit.timing.get('files_s', 0)}s, build {unit.timing.get('build_s', 0)}s")
    return "\n".join(L)


# ---------------------------------------------------------------- feedback from the document viewer
def apply_feedback(units, data):
    """Save marked-up PDFs and annotation text from the viewer step, then rewrite the affected assessment notes."""
    by_key = {}
    for u in units.values():
        for k in u.viewer_keys:
            by_key[k] = u
    touched = set()
    for r in data.get("results") or []:
        u = by_key.get(r.get("key"))
        if not u or not u.plan:
            continue
        P, T = u.plan, u.target
        sub_id, fid = r["key"].split("-", 1)
        a = next((x for x in u.bundle.get("assignments") or [] if str((x.get("submission") or {}).get("id")) == sub_id), None)
        if not a:
            continue
        cand = next((c for c in u.bundle.get("feedback_candidates") or [] if c["key"] == r["key"]), {})
        entry = dict(P.feedback.get(r["key"]) or {})
        entry.update({"checked_at": NOW.isoformat(), "graded_at": cand.get("graded_at"), "posted_at": cand.get("posted_at"),
                      "status": r.get("status"), "annotations": r.get("annotations") or []})
        if r.get("pdf"):
            import base64
            meta = (u.bundle.get("files") or {}).get(fid) or {}
            note = P.asg_note.get(a["id"])
            folder = T / "Files" / (Path(note["path"]).stem if note else clean_name(a["name"])) / "Feedback"
            stem = os.path.splitext(clean_file_name(meta.get("display_name") or f"file {fid}"))[0]
            dest = folder / f"{stem} (annotated).pdf"
            blob = base64.b64decode(r["pdf"])
            prev = entry.get("pdf")
            if dest.exists() and (not prev or (T / prev) != dest or (entry.get("pdf_sha") and file_sha(dest) != entry.get("pdf_sha"))):
                dest = folder / f"{stem} (annotated {TODAY}).pdf"
            folder.mkdir(parents=True, exist_ok=True)
            with open(lp(dest), "wb") as f:
                f.write(blob)
            entry["pdf"] = dest.relative_to(T).as_posix()
            entry["pdf_sha"] = hashlib.sha256(blob).hexdigest()[:16]
            u.result.setdefault("feedback_saved", []).append(short_title(a["name"]))
        elif r.get("status") not in ("ok", "no annotations"):
            u.result.setdefault("feedback_problems", []).append(f"{a['name']}: {r.get('status')}")
        P.feedback[r["key"]] = entry
        touched.add((u.code, a["id"]))
    for u in units.values():
        ids = {aid for code, aid in touched if code == u.code}
        if not ids or not u.plan:
            continue
        u.feedback_asg = ids
        for n in u.plan.notes:
            if n.get("asg_id") in ids:
                a = u.plan.asg[n["asg_id"]]
                n["secs"] = u.plan.assessment_parts(a)
        finalize(u, phase="feedback")


def download_dirs():
    """Folders where a browser may save the viewer step's file."""
    home = Path.home()
    out, ask = [], False
    roots = []
    if sys.platform == "darwin":
        sup = home / "Library" / "Application Support"
        roots = [sup / "Google" / "Chrome", sup / "Microsoft Edge", sup / "BraveSoftware" / "Brave-Browser", sup / "Arc" / "User Data",
                 sup / "Vivaldi", sup / "com.operasoftware.Opera", sup / "Chromium"]
    elif os.name == "nt":
        la, ra = Path(os.environ.get("LOCALAPPDATA", home)), Path(os.environ.get("APPDATA", home))
        roots = [la / "Google" / "Chrome" / "User Data", la / "Microsoft" / "Edge" / "User Data", la / "BraveSoftware" / "Brave-Browser" / "User Data",
                 la / "Vivaldi" / "User Data", ra / "Opera Software" / "Opera Stable", la / "Chromium" / "User Data"]
    else:
        cfg = home / ".config"
        roots = [cfg / "google-chrome", cfg / "chromium", cfg / "microsoft-edge", cfg / "BraveSoftware" / "Brave-Browser", cfg / "vivaldi", cfg / "opera"]
    for r in roots:
        prefs = list(r.glob("*/Preferences")) + ([r / "Preferences"] if (r / "Preferences").exists() else [])
        for p in prefs:
            try:
                d = json.loads(p.read_text(encoding="utf-8", errors="replace")).get("download") or {}
                if d.get("default_directory"):
                    out.append(Path(d["default_directory"]))
                ask = ask or bool(d.get("prompt_for_download"))
            except Exception:
                pass
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
                v = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")[0]
                out.append(Path(os.path.expandvars(v)))
        except Exception:
            pass
    elif sys.platform != "darwin":
        try:
            r = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=5)
            if r.stdout.strip():
                out.append(Path(r.stdout.strip()))
        except Exception:
            pass
    out.append(home / "Downloads")
    seen, dirs = set(), []
    for d in out:
        k = str(d).lower()
        if k not in seen and d.is_dir():
            seen.add(k)
            dirs.append(d)
    return dirs, ask


# ---------------------------------------------------------------- plan one unit when its data arrives
def plan_unit(unit: Unit, bundle):
    unit.bundle = bundle
    if unit.target is None:
        cname = clean_name(re.sub(r'^[A-Z]{2,5}\d{3,5}\S*\s*', '', bundle['course']['name']))
        unit.target = unit.root / f"{unit.code} {cname}"
        unit.target.mkdir(parents=True, exist_ok=True)
        unit.mode = "full"
    if unit.old.get("course_id") and int(unit.old["course_id"]) != int(bundle["course"]["id"]):
        raise RuntimeError(f"the unit folder belongs to Canvas course {unit.old['course_id']}, but Canvas returned course {bundle['course']['id']}")
    P = Planner(unit, bundle).build().assign_paths()
    P.plan_files()
    unit.plan = P
    unit.before = snapshot(user_paths(unit.target, P))
    unit.viewer_keys = P.viewer_keys(bundle.get("feedback_candidates"))
    return P.need(), unit.viewer_keys


# ---------------------------------------------------------------- server
class Run:
    def __init__(self, run_id):
        self.id = run_id
        self.dir = STATE / "runs" / run_id
        self.dir.mkdir(parents=True, exist_ok=True)

    def status(self):
        try:
            return json.loads((self.dir / "status.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    def set(self, **kw):
        st = self.status()
        st.update(kw)
        write_text(self.dir / "status.json", json.dumps(st, indent=1, ensure_ascii=False))
        return st


class Server:
    def __init__(self, units, port, run: Run):
        self.units = {u.code: u for u in units}
        self.port = port
        self.run = run
        self.last = time.time()
        self.connected = False
        self.all_done = threading.Event()
        self.logs = []
        self.t_files = {}
        self.viewer_expected = []

    def all_finished(self):
        return all(u.done or u.error for u in self.units.values())

    def handler(self):
        S = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def cors(self):
                if self.headers.get("Origin") == ORIGIN:
                    self.send_header("Access-Control-Allow-Origin", ORIGIN)
                    self.send_header("Access-Control-Allow-Private-Network", "true")
                    self.send_header("Access-Control-Allow-Local-Network", "true")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type")
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                    self.send_header("Vary", "Origin")

            def reply(self, code, body=b"", ctype="text/plain"):
                if isinstance(body, str):
                    body = body.encode("utf-8")
                self.send_response(code)
                self.cors()
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):
                self.send_response(204)
                self.cors()
                self.end_headers()

            def do_GET(self):
                S.last = time.time()
                url = urllib.parse.urlparse(self.path)
                if url.path == "/health":
                    return self.reply(200, "ok")
                if url.path == "/scrape.js" and self.headers.get("Origin") in (ORIGIN, None):
                    if S.connected:
                        return self.reply(200, "'easel is already running in this tab'", "text/javascript")
                    S.connected = True
                    S.run.set(state="running", connected=True, connected_at=time.time())
                    cfg = {"server": f"http://127.0.0.1:{S.port}", "run": S.run.id, "version": VERSION, "units": [u.cfg() for u in S.units.values()]}
                    js = (HERE / "scrape.js").read_text(encoding="utf-8").replace("__CFG__", json.dumps(cfg))
                    return self.reply(200, js, "text/javascript")
                self.reply(404)

            def body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n)

            def do_POST(self):
                S.last = time.time()
                if self.headers.get("Origin") != ORIGIN:
                    return self.reply(403)
                url = urllib.parse.urlparse(self.path)
                q = dict(urllib.parse.parse_qsl(url.query))
                u = S.units.get(q.get("unit", "").upper())
                try:
                    if url.path == "/log":
                        S.logs.append(self.body().decode(errors="replace"))
                        return self.reply(200)
                    if url.path == "/login":
                        self.body()
                        S.connected = False
                        S.run.set(state="login")
                        return self.reply(200)
                    if url.path == "/bundle":
                        bundle = json.loads(self.body().decode("utf-8"))
                        (STATE / "bundles").mkdir(parents=True, exist_ok=True)
                        write_text(STATE / "bundles" / f"{u.code}.json", json.dumps(bundle, ensure_ascii=False))
                        try:
                            need, keys = plan_unit(u, bundle)
                        except Exception as e:
                            u.error = f"planning failed: {e}\n{traceback.format_exc()}"
                            return self.reply(200, json.dumps({"error": str(e)}), "application/json")
                        S.t_files[u.code] = time.time()
                        return self.reply(200, json.dumps({"need": need, "feedback": keys}), "application/json")
                    if url.path == "/file":
                        fid = q["id"]
                        if fid not in u.plan.fplan or u.plan.fplan[fid]["action"] != "download":
                            return self.reply(400)
                        n = int(self.headers.get("Content-Length") or 0)
                        dst = u.staging / fid
                        with open(dst, "wb") as f:
                            while n > 0:
                                chunk = self.rfile.read(min(n, 1 << 20))
                                if not chunk:
                                    break
                                f.write(chunk)
                                n -= len(chunk)
                        u.received[fid] = dst
                        return self.reply(200)
                    if url.path == "/file_failed":
                        self.body()
                        u.failed[q["id"]] = q.get("status", "?")
                        return self.reply(200)
                    if url.path == "/done":
                        self.body()
                        u.timing["files_s"] = round(time.time() - S.t_files.get(u.code, time.time()), 1)
                        try:
                            finalize(u)
                        except Exception:
                            u.error = "writing notes failed: " + traceback.format_exc()
                        return self.reply(200)
                    if url.path == "/error":
                        msg = self.body().decode(errors="replace")
                        if u:
                            u.error = msg
                        return self.reply(200)
                    if url.path == "/all_done":
                        data = json.loads(self.body().decode("utf-8") or "{}")
                        S.viewer_expected = data.get("viewer") or []
                        self.reply(200)
                        S.all_done.set()
                        return
                except Exception as e:
                    S.logs.append(traceback.format_exc())
                    return self.reply(500, str(e))
                self.reply(404)
        return H


def summary_text(srv, elapsed):
    lines = []
    units = list(srv.units.values())
    okn = sum(1 for u in units if u.done)
    lines.append(f"easel {VERSION}: {okn} of {len(units)} unit{'s' if len(units) != 1 else ''} updated in {elapsed:.0f} s.")
    needs = []
    for u in units:
        if u.done:
            lines.append("- " + u.summary.split("\n")[0])
            # A note the student edited stays as they left it, and the chat says nothing about it (owner's rule, 2026-10-07):
            # students update notes by hand when their university changes its rules, such as when Gen AI is allowed.
            if getattr(u, "checks", {}).get("links_bad"):
                needs.append(f"{u.code}: {u.checks['links_bad']} broken link(s), see .easel/report.txt")
            if getattr(u, "checks", {}).get("user_changed"):
                needs.append(f"{u.code}: {u.checks['user_changed']} of your own files changed during the run, see .easel/report.txt")
            if u.plan and not u.plan.scheme and u.plan.grades.total() is not None:
                needs.append(f"SCALE_NEEDED {host_of(ORIGIN)}")
        else:
            err = (u.error or "did not finish").strip().split("\n")[0][:200]
            lines.append(f"- {u.code}: FAILED: {err}")
    if srv.viewer_expected and not srv.run.status().get("feedback_done"):
        needs.append("annotated feedback was not received from the browser")
    if needs:
        seen = []
        for n in needs:
            if n not in seen:
                seen.append(n)
        lines.append("Needs you: " + "; ".join(seen) + ".")
    roots = sorted({str(u.target.parent) for u in units if u.target})
    if roots:
        lines.append("Notes: " + "; ".join(roots))
    return "\n".join(lines[:12])


def serve(args):
    root = Path(args.root or ".").resolve()
    units = []
    for code in args.units:
        tgt = Path(args.target).resolve() if args.target else find_target(root, code)
        u = Unit(code, tgt, root)
        u.media, u.tidy = args.media, args.tidy
        u.feedback_enabled, u.refresh_feedback = not args.no_feedback, args.refresh_feedback
        u.reset_edited = args.reset_edited
        u.feedback_asg = set()
        units.append(u)
    set_origin(args.canvas, units)
    run = Run(args.run)
    srv = Server(units, args.port, run)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), srv.handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    started = time.time()
    run.set(state="waiting", port=args.port, started=started, pid=os.getpid())
    while not srv.all_done.wait(2):
        st = run.status()
        idle = time.time() - srv.last
        if (not srv.connected and time.time() - started > 1800) or (srv.connected and idle > 900):
            for u in units:
                if not (u.done or u.error):
                    u.error = "timed out: the Canvas tab closed or never connected"
            break
        if st.get("state") == "login" and time.time() - started > 3600:
            break
    for _ in range(60):     # units finalize as their /done arrives
        if srv.all_finished():
            break
        time.sleep(0.5)
    if srv.viewer_expected:
        run.set(state="viewer", viewer=len(srv.viewer_expected))
        dirs, ask = download_dirs()
        deadline = time.time() + 900
        name = f"easel-feedback-{run.id}"
        found = None
        while time.time() < deadline and not found:
            for d in dirs:
                for f in d.glob(name + "*.json"):
                    try:
                        s1 = f.stat().st_size
                        time.sleep(0.8)
                        if f.stat().st_size == s1 and s1 > 0:
                            found = f
                            break
                    except OSError:
                        pass
                if found:
                    break
            time.sleep(1.5)
        if found:
            try:
                data = json.loads(found.read_text(encoding="utf-8"))
                apply_feedback(srv.units, data)
                found.unlink()
                run.set(feedback_done=True)
            except Exception:
                srv.logs.append("feedback: " + traceback.format_exc())
    rep = "\n\n".join(u.report if u.report else f"== {u.code} | FAILED\n{u.error}" for u in units)
    if srv.logs:
        rep += "\n\nlog:\n" + "\n".join(srv.logs[-15:])
    write_text(run.dir / "report.txt", rep + "\n")
    run.set(state="finished", summary=summary_text(srv, time.time() - started))
    for u in units:
        shutil.rmtree(u.staging, ignore_errors=True)
    httpd.shutdown()


def free_port(p):
    for port in range(p, p + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("No free port between %d and %d." % (p, p + 19))


def loader_js(port, run_id):
    return ("await (async()=>{const P=%d,R='%s',C='%s';"
            "if(location.origin!==C)return 'WRONG_PAGE: open '+C+' in this tab first. This tab shows '+location.origin;"
            "let s='unknown';for(const n of['loopback-network','local-network-access']){try{s=(await navigator.permissions.query({name:n})).state;break}catch(e){}}"
            "window.__easel=fetch('http://127.0.0.1:'+P+'/scrape.js?run='+R).then(r=>r.text()).then(t=>(0,eval)(t)).catch(e=>'ERR '+e);"
            "return 'PERMISSION_'+s.toUpperCase()})()") % (port, run_id, ORIGIN)


def check_update():
    """Returns a one-line message. Installs a newer published release when one exists."""
    if os.environ.get("EASEL_NO_UPDATE"):
        return None
    try:
        with urllib.request.urlopen(RELEASE + "VERSION", timeout=4) as r:
            remote = r.read().decode("utf-8").strip()
    except Exception:
        return "Couldn't check for updates, carrying on with what you have."
    local = (KIT / "VERSION").read_text(encoding="utf-8").strip() if (KIT / "VERSION").exists() else VERSION
    if version_tuple(remote) <= version_tuple(local):
        return None
    # Download into the skill folder itself: os.replace cannot move files from another disk, such as a Linux /tmp.
    tmp = Path(tempfile.mkdtemp(prefix=".update-", dir=KIT))
    try:
        for name, rel in KIT_FILES.items():
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(RELEASE + name, timeout=20) as r:
                dst.write_bytes(r.read())
        compile((tmp / "scripts" / "easel.py").read_text(encoding="utf-8"), "easel.py", "exec")
        for rel in KIT_FILES.values():
            (KIT / rel).parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp / rel, KIT / rel)
    except Exception as e:
        return f"An update to {remote.split()[0]} exists but failed to install ({e.__class__.__name__}). Carrying on with {local.split()[0]}."
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return f"UPDATED {local.split()[0]} -> {remote.split()[0]}"


def cmd_start(args):
    msg = None if args.no_update else check_update()
    if msg and msg.startswith("UPDATED"):
        print(f"easel updated from {msg.split()[1]} to {msg.split()[3]}.")
        env = dict(os.environ, EASEL_NO_UPDATE="1")
        sys.exit(subprocess.call([sys.executable, str(HERE / "easel.py")] + sys.argv[1:], env=env))
    STATE.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    cwd = Path.cwd().resolve()
    if args.root:
        root = Path(args.root).expanduser().resolve()
    elif any(find_target(cwd, c) for c in args.units) or (cwd != Path.home().resolve() and not cfg.get("root")):
        root = cwd
    elif cfg.get("root") and Path(cfg["root"]).is_dir():
        root = Path(cfg["root"])
    else:
        print("ROOT_NEEDED: ask the user which folder holds (or should hold) the unit folders, then run start again with --root.")
        sys.exit(2)
    if not root.is_dir():
        print(f"ROOT_NEEDED: the notes folder does not exist: {root}. Ask the user for the right folder.")
        sys.exit(2)
    units = [Unit(c, Path(args.target).resolve() if args.target else find_target(root, c), root) for c in args.units]
    if not (args.canvas or cfg.get("canvas") or any(u.old.get("canvas") for u in units)):
        print("CANVAS_NEEDED: ask the user for their Canvas address, such as https://canvas.qut.edu.au, then run start again with --canvas.")
        sys.exit(2)
    set_origin(args.canvas or cfg.get("canvas"), units)
    cfg.update({"canvas": ORIGIN, "root": str(root)})
    save_config(cfg)
    port = free_port(args.port)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(2).hex()
    run = Run(run_id)
    write_text(STATE / "last", run_id)
    cmd = [sys.executable, str(Path(__file__).resolve()), "_serve", *args.units, "--root", str(root), "--port", str(port),
           "--canvas", ORIGIN, "--run", run_id]
    for flag, on in (("--media", args.media), ("--tidy", args.tidy), ("--no-feedback", args.no_feedback),
                     ("--refresh-feedback", args.refresh_feedback), ("--reset-edited", args.reset_edited)):
        if on:
            cmd.append(flag)
    if args.target:
        cmd += ["--target", args.target]
    log = open(run.dir / "server.log", "w")
    if os.name == "nt":
        subprocess.Popen(cmd, stdout=log, stderr=log, creationflags=0x00000008 | 0x00000200)
    else:
        subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True)
    for _ in range(80):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise SystemExit("The helper did not start. See " + str(run.dir / "server.log"))
    if msg:
        print(msg)
    print(f"easel {VERSION} | Canvas {ORIGIN} | notes folder {root}")
    for u in units:
        if u.target:
            v3 = " (v3 folder: backup, then migrate)" if u.old_format == 3 else ""
            print(f"{u.code}: {u.mode} -> {u.target}{v3}")
        else:
            # No placeholder path here: an agent once reported "<course name>" to the student as the real folder name.
            print(f"{u.code}: new folder in {root}, named after the course")
    print("LOADER: " + loader_js(port, run_id))
    return port


def cmd_wait(args):
    run_id = args.run or (STATE / "last").read_text(encoding="utf-8").strip()
    run = Run(run_id)
    t0 = time.time()
    while time.time() - t0 < args.max:
        st = run.status()
        state = st.get("state")
        if state == "finished":
            print(st.get("summary") or "finished")
            return
        if state == "login":
            print("LOGIN: Canvas says the browser is not signed in. Ask the user to sign in to Canvas in the Chrome tab. "
                  "When the tab shows Canvas again, run the LOADER again, then run wait again.")
            return
        if state == "viewer" and not st.get("viewer_told"):
            run.set(viewer_told=True)
            dirs, ask = download_dirs()
            print(f"VIEWER: the Canvas tab is moving to Canvas's document viewer to collect annotated feedback for {st.get('viewer')} file(s).")
            print("Run the script below in that tab with javascript_tool. If it returns NOT_READY, wait 3 seconds and run it again.")
            if ask:
                print("The browser asks where to save downloads: tell the user to click Save when the dialog appears.")
            print("Then run wait again.")
            print("VIEWER_JS:")
            print(viewer_script())
            return
        if state in ("waiting", "running") and not st.get("connected") and time.time() - float(st.get("started") or t0) > 90 and time.time() - t0 > 20:
            print("NOT_CONNECTED: the Canvas tab has not reached the helper. Check the LOADER result: "
                  "PERMISSION_PROMPT means the user must click Allow in Chrome's box; PERMISSION_DENIED means the user must allow "
                  "'Apps on device' (or 'Local network access') in the site settings for Canvas, then you run the LOADER again.")
            return
        time.sleep(1)
    print("STILL_RUNNING: run wait again.")


def viewer_script():
    """viewer.js without comment lines or indentation: the agent copies it, so shorter costs fewer tokens."""
    out = []
    for line in (HERE / "viewer.js").read_text(encoding="utf-8").split("\n"):
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        out.append(s)
    return "\n".join(out)


def cmd_viewer_js(args):
    print(viewer_script())


def cmd_scale(args):
    set_origin(args.canvas)
    pairs = []
    for part in args.set.split(","):
        if ":" not in part:
            continue
        name, v = part.rsplit(":", 1)
        v = float(v)
        pairs.append([name.strip(), v / 100 if v > 1 else v])
    if not pairs:
        raise SystemExit('Give the scale as names and minimum percentages, for example: --set "7:85,6:75,5:65,4:50,3:40,2:25,1:0"')
    cfg = load_config()
    cfg.setdefault("hosts", {}).setdefault(host_of(ORIGIN), {})["scale"] = pairs
    if args.title:
        cfg["hosts"][host_of(ORIGIN)]["scale_title"] = args.title
    save_config(cfg)
    print(f"Saved the grade scale for {host_of(ORIGIN)}: " + ", ".join(f"{n} from {pct(v)}" for n, v in pairs))


def cmd_rebuild(args):
    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    tgt = Path(args.target).resolve()
    u = Unit(bundle["unit"], tgt if tgt.exists() else None, tgt.parent)
    u.feedback_asg = set()
    if not tgt.exists():
        tgt.mkdir(parents=True)
        u.target = tgt
    u.tidy, u.reset_edited = args.tidy, args.reset_edited
    set_origin(args.canvas or u.old.get("canvas") or bundle.get("origin"), [u])
    need, _ = plan_unit(u, bundle)
    for fid in need:
        u.failed[fid] = "offline"
    u.viewer_keys = []
    finalize(u)
    print(u.report)
    print(f"(offline rebuild: {len(need)} files would have been downloaded)")


def cmd_refresh(args):
    """Rewrite notes from the last Canvas data on this computer, with no browser. For --reset-edited and a new grade scale."""
    cfg = load_config()
    root = Path(args.root).expanduser().resolve() if args.root else Path(cfg.get("root") or ".").resolve()
    lines = []
    for code in args.units:
        src = STATE / "bundles" / f"{code.upper()}.json"
        tgt = find_target(root, code)
        if not src.exists() or not tgt:
            lines.append(f"{code.upper()}: no earlier run found under {root}; run start instead")
            continue
        bundle = json.loads(src.read_text(encoding="utf-8"))
        u = Unit(code, tgt, root)
        u.reset_edited = args.reset_edited
        set_origin(cfg.get("canvas") or u.old.get("canvas") or bundle.get("origin"), [u])
        need, _ = plan_unit(u, bundle)
        for fid in need:
            u.failed[fid] = "not downloaded yet"
        u.viewer_keys = []
        finalize(u)
        extra = f"; replaced {len(u.result.get('reset', []))} edited note(s), copies in .easel/backups" if u.result.get("reset") else ""
        lines.append(f"{u.code}: notes rewritten from the last Canvas data ({len(u.result.get('written', []))} changed{extra})")
    print("\n".join(lines))


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="easel")
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "_serve"):
        p = sp.add_parser(name)
        p.add_argument("units", nargs="+")
        p.add_argument("--root")
        p.add_argument("--target")
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--canvas")
        p.add_argument("--media", action="store_true", help="also download video, audio and files over 100 MB")
        p.add_argument("--tidy", action="store_true", help="move notes and files to the standard names and folders")
        p.add_argument("--no-feedback", action="store_true", help="skip annotated feedback")
        p.add_argument("--refresh-feedback", action="store_true", help="check every marked file for annotations again")
        p.add_argument("--reset-edited", action="store_true", help="replace notes edited outside My notes; a copy goes to .easel/backups")
        p.add_argument("--no-update", action="store_true")
        p.add_argument("--run")
    p = sp.add_parser("wait")
    p.add_argument("--max", type=int, default=540)
    p.add_argument("--run")
    sp.add_parser("viewer-js")
    p = sp.add_parser("scale")
    p.add_argument("--canvas", required=True)
    p.add_argument("--set", required=True)
    p.add_argument("--title")
    p = sp.add_parser("rebuild")
    p.add_argument("bundle")
    p.add_argument("--target", required=True)
    p.add_argument("--tidy", action="store_true")
    p.add_argument("--reset-edited", action="store_true")
    p.add_argument("--canvas")
    p = sp.add_parser("refresh")
    p.add_argument("units", nargs="+")
    p.add_argument("--root")
    p.add_argument("--reset-edited", action="store_true")
    sp.add_parser("version")
    sp.add_parser("update")
    a = ap.parse_args()
    if a.cmd == "start":
        cmd_start(a)
    elif a.cmd == "_serve":
        serve(a)
    elif a.cmd == "wait":
        cmd_wait(a)
    elif a.cmd == "viewer-js":
        cmd_viewer_js(a)
    elif a.cmd == "scale":
        cmd_scale(a)
    elif a.cmd == "rebuild":
        cmd_rebuild(a)
    elif a.cmd == "refresh":
        cmd_refresh(a)
    elif a.cmd == "update":
        os.environ.pop("EASEL_NO_UPDATE", None)
        msg = check_update()
        print(f"easel updated from {msg.split()[1]} to {msg.split()[3]}." if msg and msg.startswith("UPDATED") else (msg or f"easel {VERSION} is up to date."))
    else:
        print(VERSION)


if __name__ == "__main__":
    main()
