"""Offline tests for the easel helper. They use made-up Canvas data and run on macOS, Windows and Linux.

    python -m unittest discover -s tests -v
"""
import base64
import copy
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "easel" / "scripts"
sys.path.insert(0, str(SCRIPTS))
os.environ["EASEL_NO_UPDATE"] = "1"
TMP_HOME = tempfile.mkdtemp(prefix="easel-test-home-")
os.environ["EASEL_HOME"] = TMP_HOME
import easel  # noqa: E402

ORIGIN = "https://canvas.example.edu"
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def make_bundle(weighted=True):
    """A small unit: two weeks, three assessments, one empty exam group, files, staff, groups and an Inbox thread."""
    rubric = [
        {"id": "_c1", "description": "Analysis", "long_description": "Depth of analysis.", "points": 10, "use_range": False,
         "ratings": [{"id": "r1a", "description": "High Distinction", "long_description": "Deep.", "points": 10},
                     {"id": "r1b", "description": "Credit", "long_description": "Sound.", "points": 6},
                     {"id": "r1c", "description": "Fail", "long_description": "Missing.", "points": 0}]},
        {"id": "_c2", "description": "Writing [clarity]", "long_description": "Clear writing.", "points": 10, "use_range": True,
         "ratings": [{"id": "r2a", "description": "Excellent", "long_description": "", "points": 10},
                     {"id": "r2b", "description": "Good", "long_description": "", "points": 7},
                     {"id": "r2c", "description": "Poor", "long_description": "", "points": 3}]},
    ]
    asg1 = {"id": 101, "name": "ABC101 Assignment 1: Report [Individual] (20%)", "due_at": "2026-08-20T13:59:00Z",
            "points_possible": 20, "grading_type": "points", "omit_from_final_grade": False, "published": True,
            "submission_types": ["online_upload"], "html_url": f"{ORIGIN}/courses/9/assignments/101", "assignment_group_id": 1,
            "rubric": rubric, "rubric_settings": {"title": "Report rubric", "points_possible": 20},
            "description_md": "Write a report. See [the template](FILE:501).",
            "submission": {"id": 7001, "workflow_state": "graded", "attempt": 1, "submitted_at": "2026-08-19T10:00:00Z",
                           "graded_at": "2026-09-01T03:00:00Z", "posted_at": "2026-09-01T03:00:00Z", "score": 15, "grade": "15",
                           "late": False, "missing": False, "excused": False, "files": ["601"],
                           "comments": [{"id": 1, "author": "Dr Tutor", "author_id": 50, "staff": True, "created_at": "2026-09-01T03:00:00Z",
                                         "comment": "Good work.\nExpand section 2.", "attachments": ["602"]}],
                           "rubric_assessment": {"_c1": {"rating_id": "r1a", "points": 10, "comments": "Strong analysis."},
                                                 "_c2": {"points": 5, "comments": ""}}}}
    asg2 = {"id": 102, "name": "ABC101 Assignment 2: Build", "due_at": "2026-10-30T13:59:00Z", "points_possible": 40,
            "grading_type": "points", "published": True, "submission_types": ["online_upload"],
            "html_url": f"{ORIGIN}/courses/9/assignments/102", "assignment_group_id": 2, "rubric": [], "description_md": "Build it.",
            "submission": None}
    quiz1 = {"id": 103, "name": "Weekly quiz 1", "due_at": "2026-08-01T13:59:00Z", "points_possible": 5, "grading_type": "points",
             "published": True, "submission_types": ["online_quiz"], "html_url": f"{ORIGIN}/courses/9/assignments/103",
             "assignment_group_id": 1, "rubric": [], "description_md": "",
             "submission": {"id": 7003, "workflow_state": "graded", "submitted_at": "2026-07-30T00:00:00Z", "score": 5, "files": [], "comments": []}}
    files = {
        "501": {"id": "501", "display_name": "Report template.docx", "size": 10, "content_type": "application/vnd.openxmlformats", "updated_at": "2026-07-01T00:00:00Z"},
        "502": {"id": "502", "display_name": "Week 1 slides (final).pdf", "size": 12, "content_type": "application/pdf", "updated_at": "2026-07-01T00:00:00Z"},
        "503": {"id": "503", "display_name": "diagram.png", "size": 5, "content_type": "image/png", "updated_at": "2026-07-01T00:00:00Z"},
        "601": {"id": "601", "display_name": "my report.pdf", "size": len(PDF), "content_type": "application/pdf", "updated_at": "2026-08-19T10:00:00Z",
                "role": "submission", "assignment_id": 101},
        "602": {"id": "602", "display_name": "feedback.docx", "size": 8, "content_type": "application/vnd.openxmlformats", "updated_at": "2026-09-01T03:00:00Z",
                "role": "feedback", "assignment_id": 101},
    }
    return {
        "easel": "4.0.0", "format": 4, "unit": "ABC101", "origin": ORIGIN, "scraped_at": "2026-10-07T00:00:00Z",
        "course": {"id": 9, "name": "ABC101_26se2 Test Unit", "course_code": "ABC101_26se2", "term": "2026 SEM-2", "teachers": ["Dr Tutor"],
                   "hide_final_grades": True, "apply_group_weights": weighted,
                   "grading_scheme": {"title": "7-Point Scale", "data": [["7", 0.85], ["6", 0.75], ["5", 0.65], ["4", 0.5], ["3", 0.4], ["2", 0.25], ["1", 0]]},
                   "tabs": [{"label": "Echo360", "type": "external", "html_url": f"{ORIGIN}/courses/9/external_tools/1"}]},
        "staff": [{"id": 50, "name": "Dr Tutor", "sortable_name": "Tutor, Dr", "roles": ["Coordinator"]}],
        "groups": [{"id": 3, "name": "Group 7", "members": ["Ann", "Ben"]}],
        "inbox": [{"id": 11, "subject": "Extension", "last_at": "2026-09-02T00:00:00Z",
                   "messages": [{"author": "Dr Tutor", "author_id": 50, "staff": True, "created_at": "2026-09-02T00:00:00Z", "body": "Approved.", "attachments": []}]}],
        "modules": [
            {"id": 1, "name": "Week 1: Basics", "position": 1, "items": [
                {"id": 11, "type": "Page", "title": "Welcome", "page_url": "welcome", "html_url": f"{ORIGIN}/courses/9/pages/welcome",
                 "body_md": "Hello. Slides: [slides](FILE:502). Figure: [image: a diagram]", "updated_at": "2026-07-01T00:00:00Z"},
                {"id": 12, "type": "Assignment", "title": "Assignment 1: Report [Individual] (20%)", "content_id": 101, "assignment_id": 101,
                 "html_url": f"{ORIGIN}/courses/9/assignments/101"},
                {"id": 13, "type": "File", "title": "diagram.png", "content_id": 503, "file_id": "503"}]},
            {"id": 2, "name": "Week 2: More", "position": 2, "items": [
                {"id": 21, "type": "Page", "title": "My notes", "page_url": "my-notes", "html_url": f"{ORIGIN}/courses/9/pages/my-notes",
                 "body_md": "A Canvas page called My notes.", "updated_at": "2026-07-02T00:00:00Z"}]},
            {"id": 3, "name": "Assessment information", "position": 3, "items": [
                {"id": 31, "type": "Page", "title": "Overview", "page_url": "overview", "html_url": f"{ORIGIN}/courses/9/pages/overview",
                 "body_md": "Weights are on the Grades tab.", "updated_at": "2026-07-03T00:00:00Z"}]},
        ],
        "assignments": [asg1, asg2, quiz1],
        "announcements": [{"id": 900, "title": "Welcome", "posted_at": "2026-07-01T00:00:00Z", "author": "Dr Tutor",
                           "html_url": f"{ORIGIN}/courses/9/discussion_topics/900", "message_md": "Hi all.", "attachments": []}],
        "syllabus_md": "",
        "assignment_groups": [{"id": 1, "name": "Assignments", "position": 1, "group_weight": 50, "rules": {}},
                              {"id": 2, "name": "Project", "position": 2, "group_weight": 20, "rules": {}},
                              {"id": 4, "name": "Final exam", "position": 3, "group_weight": 30, "rules": {}}],
        "group_weights": weighted, "extra_pages": [], "extra_discussions": [], "extra_files": [], "files": files,
        "feedback_candidates": [{"key": "7001-601", "assignment_id": 101, "file_id": "601", "graded_at": "2026-09-01T03:00:00Z",
                                 "posted_at": "2026-09-01T03:00:00Z"}],
        "api_status": {}, "fetch_ms": 1000, "coverage": {"words": 100, "missing": 0, "pages": []},
    }


def run_unit(bundle, root, received=None, reset_edited=False, feedback=None):
    """Plan and write one unit the way the server does, with fake downloads."""
    easel.set_origin(ORIGIN)
    u = easel.Unit(bundle["unit"], easel.find_target(Path(root), bundle["unit"]), Path(root))
    u.reset_edited = reset_edited
    need, keys = easel.plan_unit(u, copy.deepcopy(bundle))
    for fid in need:
        p = u.staging / fid
        p.write_bytes(PDF if fid == "601" else b"x" * 10)
        u.received[fid] = p
    easel.finalize(u)
    if feedback is not None:
        u.viewer_keys = keys
        easel.apply_feedback({u.code: u}, feedback)
    return u


class Helpers(unittest.TestCase):
    def test_split_my_notes(self):
        body = "# T\n\ntext\n\n## My notes\n\n" + easel.MY_NOTES_HINT + "\n\nmine\n"
        gen, mine = easel.split_my_notes(body)
        self.assertEqual(mine, "mine")
        self.assertTrue(gen.endswith("text\n\n"))
        self.assertEqual(easel.split_my_notes("# T\n\nno section\n"), ("# T\n\nno section\n", None))

    def test_names(self):
        self.assertEqual(easel.clean_name('a/b: c*?"<>|'), "a-b - c")
        self.assertEqual(easel.clean_name("CON"), "CON note")
        self.assertEqual(easel.UNIT_PREFIX.sub("", "IFB102_PRAC 1: Set up"), "PRAC 1: Set up")
        self.assertEqual(easel.UNIT_PREFIX.sub("", "IFB220_26se2 Week 3"), "Week 3")
        self.assertEqual(easel.short_title("IFB240 Assessment Task 2 - Part A submission link (5%)"), "Assessment Task 2 - Part A")

    def test_versions_agree(self):
        v = (ROOT / "skills" / "easel" / "VERSION").read_text(encoding="utf-8").split()[0]
        self.assertEqual(v, easel.VERSION)
        for f in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
            data = json.loads((ROOT / f).read_text(encoding="utf-8"))
            found = data.get("version") or data["plugins"][0]["version"]
            self.assertEqual(found, v, f)

    def test_yaml(self):
        self.assertEqual(easel.yaml_val("marked"), "marked")
        self.assertEqual(easel.yaml_val("2026 SEM-2"), '"2026 SEM-2"')
        self.assertEqual(easel.yaml_val("https://x.y/z"), '"https://x.y/z"')
        self.assertEqual(easel.yaml_val(6.0), "6")


class Grades(unittest.TestCase):
    def test_weighted_with_empty_exam(self):
        g = easel.Grades(make_bundle(weighted=True))
        # Assignments group: 15/20 and 5/5 = 20/25 = 0.8. Project unmarked. Exam has no Canvas assessment yet.
        self.assertAlmostEqual(g.total(), 0.8)
        self.assertAlmostEqual(g.total(fill=0.0, empty_fill=0.0), 0.5 * 0.8)
        self.assertAlmostEqual(g.total(fill=1.0, empty_fill=1.0), 0.5 * 0.8 + 0.2 + 0.3)
        need = g.need(0.85)
        self.assertAlmostEqual(need, (0.85 - 0.4) / 0.5, places=4)
        self.assertEqual(g.need(0.3), "secured")

    def test_points_and_drop_lowest(self):
        b = make_bundle(weighted=False)
        b["assignment_groups"][0]["rules"] = {"drop_lowest": 1}
        g = easel.Grades(b)
        # Drop lowest of 15/20 (0.75) and 5/5 (1.0): keeps 5/5. Exam group has no assessments and no weight in points mode.
        self.assertAlmostEqual(g.total(), 1.0)

    def test_band(self):
        s = easel.scheme_of(make_bundle())
        self.assertEqual(easel.band_of(s, 0.8), "6")
        self.assertEqual(easel.band_of(s, 0.85), "7")


class Notes(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="easel-test-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def unit_dir(self):
        return next(self.root.glob("ABC101*"))

    def test_first_run_links_and_layout(self):
        u = run_unit(make_bundle(), self.root)
        T = self.unit_dir()
        ok, bad, broken, leftovers, orphans = easel.check_links(T)
        self.assertEqual(bad, 0, broken)
        self.assertEqual(leftovers, [])
        for rel in ["INDEX.md", "2 Assessments/Grades.md", "1 Course Info/Inbox.md", "1 Course Info/00 Course Info.md",
                    "3 Weeks/Week 01 - Basics.md", "3 Weeks/Week 02 - More.md"]:
            self.assertTrue((T / rel).exists(), rel)
        a1 = next((T / "2 Assessments").glob("Assignment 1*.md"))
        text = a1.read_text(encoding="utf-8")
        self.assertIn("**✓ High Distinction**", text)  # level found by rating id
        self.assertIn("**✓ Good**", text)              # level found by points range: 5 sits in "7 to >3"
        self.assertIn("Expand section 2.", text)
        self.assertIn("Your submission", text)
        self.assertTrue((T / "Files" / a1.stem / "Your submission" / "my report.pdf").exists())
        self.assertTrue((T / "Files" / a1.stem / "Feedback" / "feedback.docx").exists())
        week2 = (T / "3 Weeks" / "Week 02 - More.md").read_text(encoding="utf-8")
        self.assertIn("## My notes (Canvas)", week2)
        self.assertEqual(week2.count("\n## My notes\n"), 1)
        grades = (T / "2 Assessments" / "Grades.md").read_text(encoding="utf-8")
        self.assertIn("What you need", grades)
        self.assertIn("hides the unit total", grades)
        self.assertFalse((T / "Files" / "Week 01" / "diagram.png").exists())   # images stay on Canvas
        self.assertTrue(u.done)

    def test_second_run_changes_nothing(self):
        run_unit(make_bundle(), self.root)
        T = self.unit_dir()
        before = {p: p.read_bytes() for p in T.rglob("*.md")}
        u = run_unit(make_bundle(), self.root)
        self.assertEqual(u.result["written"], [])
        self.assertEqual(u.result["new"], [])
        for p, data in before.items():
            if p.name != "INDEX.md":
                self.assertEqual(p.read_bytes(), data, p.name)

    def test_my_notes_and_properties_survive(self):
        run_unit(make_bundle(), self.root)
        T = self.unit_dir()
        w = T / "3 Weeks" / "Week 01 - Basics.md"
        text = w.read_text(encoding="utf-8").replace("updated:", "tags: [exam]\nupdated:", 1) + "\nMy summary line.\n"
        w.write_text(text, encoding="utf-8")
        b = make_bundle()
        b["modules"][0]["items"][0]["body_md"] = "Hello again, updated on Canvas."
        b["modules"][0]["items"][0]["updated_at"] = "2026-10-01T00:00:00Z"
        run_unit(b, self.root)
        out = w.read_text(encoding="utf-8")
        self.assertIn("Hello again, updated on Canvas.", out)
        self.assertIn("My summary line.", out)
        self.assertIn("tags: [exam]", out)

    def test_edited_note_is_kept_and_not_mentioned(self):
        run_unit(make_bundle(), self.root)
        T = self.unit_dir()
        w = T / "1 Course Info" / "02 Assessment information.md"
        if not w.exists():
            w = next((T / "2 Assessments").glob("*Assessment information.md"))
        edited = w.read_text(encoding="utf-8").replace("Weights are on the Grades tab.", "Gen AI is allowed in Assignment 2 (email from the coordinator).")
        w.write_text(edited, encoding="utf-8")
        b = make_bundle()
        b["modules"][2]["items"][0]["body_md"] = "Weights changed on Canvas."
        u = run_unit(b, self.root)
        self.assertEqual(w.read_text(encoding="utf-8"), edited)
        self.assertIn(w.name, u.result["edited"])

        class Srv:
            units = {u.code: u}
            viewer_expected = []

            class run:
                @staticmethod
                def status():
                    return {}
        self.assertNotIn("edit", easel.summary_text(Srv, 10).lower())
        u2 = run_unit(b, self.root, reset_edited=True)
        self.assertIn("Weights changed on Canvas.", w.read_text(encoding="utf-8"))
        self.assertTrue(list((T / ".easel" / "backups").rglob(w.name)))
        self.assertIn(w.name, u2.result["reset"])

    def test_annotated_feedback(self):
        fb = {"results": [{"key": "7001-601", "status": "ok", "pdf": base64.b64encode(PDF).decode(),
                           "annotations": [{"id": "a1", "type": "text", "page": 0, "author": "Dr Tutor", "role": "teacher", "contents": "Cite this."},
                                           {"id": "a2", "type": "commentReply", "page": 0, "author": "Dr Tutor", "contents": "And this.", "inreplyto": "a1"}]}]}
        run_unit(make_bundle(), self.root, feedback=fb)
        T = self.unit_dir()
        a1 = next((T / "2 Assessments").glob("Assignment 1*.md"))
        text = a1.read_text(encoding="utf-8")
        self.assertIn('Page 1 · comment by Dr Tutor: "Cite this." / "And this."', text)
        pdfs = list((T / "Files").rglob("*(annotated).pdf"))
        self.assertEqual(len(pdfs), 1)
        self.assertEqual(pdfs[0].read_bytes(), PDF)
        ok, bad, broken, leftovers, orphans = easel.check_links(T)
        self.assertEqual(bad, 0, broken)

    def test_v3_folder_migrates_with_backup(self):
        T = self.root / "ABC101 Test Unit"
        for d in ("1 Course Info", "2 Assessments", "3 Weeks", "Files/Week 01"):
            (T / d).mkdir(parents=True)
        v3_week = "---\nsource_folder: Week 1: Basics\npages: 1\nscraped: 2026-10-01\n---\n\n# Week 01 - Basics\n\nold text\n"
        (T / "3 Weeks" / "Week 01 - Basics.md").write_text(v3_week, encoding="utf-8")
        old_asg = "---\nsource_folder: Assignments\npages: 1\nscraped: 2026-10-01\n---\n\n# Assignments\n\nold\n"
        (T / "2 Assessments" / "Assignments.md").write_text(old_asg, encoding="utf-8")
        (T / "Files" / "Week 01" / "Week 1 slides (final).pdf").write_bytes(b"y" * 12)
        (T / "my own note.md").write_text("mine", encoding="utf-8")
        sha = lambda s: easel.raw_sha(s)  # noqa: E731
        (T / ".canvas-manifest.json").write_text(json.dumps({
            "version": 3, "canvas": ORIGIN, "course_id": 9, "scraped": "2026-10-01",
            "notes": [{"key": "Week 01", "path": "3 Weeks/Week 01 - Basics.md", "module_ids": [1], "sha": sha(v3_week)},
                      {"key": "assignments", "path": "2 Assessments/Assignments.md", "module_ids": [], "sha": sha(old_asg)}],
            "files": [{"id": "502", "name": "Week 1 slides (final).pdf", "path": "Files/Week 01/Week 1 slides (final).pdf", "size": 12}],
            "assignments": [{"id": 101, "name": "A1", "graded": False}], "announcements": []}), encoding="utf-8")
        u = run_unit(make_bundle(), self.root)
        self.assertTrue(list((T / ".easel" / "backups").glob("v3-notes-*.zip")))
        self.assertFalse((T / "2 Assessments" / "Assignments.md").exists())
        self.assertFalse((T / ".canvas-manifest.json").exists())
        self.assertTrue((T / ".easel" / "manifest.json").exists())
        self.assertIn("Hello.", (T / "3 Weeks" / "Week 01 - Basics.md").read_text(encoding="utf-8"))
        self.assertEqual((T / "my own note.md").read_text(encoding="utf-8"), "mine")
        self.assertTrue(any("marks released" in x for x in u.summary.split("\n")))


class EditedStaysEdited(unittest.TestCase):
    """A note the student edited stays theirs on the first v4 run and on every run after it."""

    def test_v3_edit_survives_repeat_runs(self):
        root = Path(tempfile.mkdtemp(prefix="easel-edit-"))
        try:
            T = root / "ABC101 Test Unit"
            for d in ("1 Course Info", "2 Assessments", "3 Weeks", "Files"):
                (T / d).mkdir(parents=True)
            written = "---\nsource_folder: Week 1: Basics\npages: 1\nscraped: 2026-10-01\n---\n\n# Week 01 - Basics\n\nold text\n"
            edited = written.replace("old text", "old text\n\n> [!warning] Gen AI\n> Gen AI is allowed in Assignment 2.")
            note = T / "3 Weeks" / "Week 01 - Basics.md"
            note.write_text(edited, encoding="utf-8")
            manifest = T / ".canvas-manifest.json"
            manifest.write_text(json.dumps({"version": 3, "canvas": ORIGIN, "course_id": 9, "scraped": "2026-10-01",
                                            "notes": [{"key": "Week 01", "path": "3 Weeks/Week 01 - Basics.md", "module_ids": [1],
                                                       "sha": easel.raw_sha(written)}], "files": [], "assignments": [], "announcements": []}),
                                encoding="utf-8")
            old = time.time() - 86400
            os.utime(note, (old, old))
            for _ in range(3):
                u = run_unit(make_bundle(), root)
                self.assertEqual(note.read_text(encoding="utf-8"), edited)
                self.assertIn(note.name, u.result["edited"])
            entry = next(n for n in json.loads((T / ".easel" / "manifest.json").read_text(encoding="utf-8"))["notes"] if n["key"] == "Week 01")
            self.assertTrue(entry.get("edited"))
        finally:
            shutil.rmtree(root, ignore_errors=True)


class Server(unittest.TestCase):
    """The helper's HTTP flow, as the browser script drives it."""

    def test_bundle_files_done(self):
        root = Path(tempfile.mkdtemp(prefix="easel-srv-"))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        run_id = "test-" + str(int(time.time()))
        env = dict(os.environ, EASEL_HOME=TMP_HOME, EASEL_NO_UPDATE="1")
        proc = subprocess.Popen([sys.executable, str(SCRIPTS / "easel.py"), "_serve", "ABC101", "--root", str(root), "--port", str(port),
                                 "--canvas", ORIGIN, "--run", run_id], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
                    break
                except Exception:
                    time.sleep(0.1)

            def post(path, data, ctype="application/json"):
                req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method="POST",
                                             headers={"Origin": ORIGIN, "Content-Type": ctype})
                return urllib.request.urlopen(req, timeout=30).read()
            js = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/scrape.js?run={run_id}", headers={"Origin": ORIGIN})).read().decode()
            self.assertIn('"run": "%s"' % run_id, js)
            plan = json.loads(post(f"/bundle?unit=ABC101&run={run_id}", json.dumps(make_bundle()).encode()))
            self.assertIn("601", plan["need"])
            self.assertEqual(plan["feedback"], ["7001-601"])
            for fid in plan["need"]:
                post(f"/file?unit=ABC101&id={fid}&run={run_id}", PDF if fid == "601" else b"x" * 10, "application/octet-stream")
            post(f"/done?unit=ABC101&run={run_id}", b"{}")
            post(f"/all_done?run={run_id}", json.dumps({"lines": [], "viewer": []}).encode())
            out = subprocess.run([sys.executable, str(SCRIPTS / "easel.py"), "wait", "--run", run_id, "--max", "60"], env=env,
                                 capture_output=True, text=True, encoding="utf-8", timeout=90).stdout
            self.assertIn("1 of 1 unit updated", out, out)
            self.assertIn("ABC101", out)
            forbidden = urllib.request.Request(f"http://127.0.0.1:{port}/log", data=b"x", method="POST", headers={"Origin": "https://evil.example"})
            with self.assertRaises(Exception):
                urllib.request.urlopen(forbidden, timeout=5)
        finally:
            proc.wait(timeout=30) if proc.poll() is None else None
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
