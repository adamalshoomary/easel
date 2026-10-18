"""Offline tests for the easel helper. They use made-up Canvas data and run on macOS, Windows and Linux.

    python -m unittest discover -s easel/tests -v
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
import threading
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

sys.path.insert(0, str(ROOT / "tools"))
import release_files  # noqa: E402

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


def run_unit(bundle, root, received=None, reset_edited=False, feedback=None, blobs=None):
    """Plan and write one unit the way the server does, with fake downloads."""
    easel.set_origin(ORIGIN)
    u = easel.Unit(bundle["unit"], easel.find_target(Path(root), bundle["unit"]), Path(root))
    u.reset_edited = reset_edited
    need, keys = easel.plan_unit(u, copy.deepcopy(bundle))
    for fid in need:
        p = u.staging / fid
        p.write_bytes((blobs or {}).get(fid) or (PDF if fid == "601" else b"x" * 10))
        u.received[fid] = p
    easel.finalize(u)
    if feedback is not None:
        u.viewer_keys = keys
        easel.apply_feedback({u.code: u}, feedback)
    return u


A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_ = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _zip(parts):
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return buf.getvalue()


def make_pptx():
    """Three slides: a title slide, a slide with speaker notes, a slide with a table. Slide 3 comes first in the file list."""
    def sp(*paras):
        return f'<p:sp xmlns:p="{P_}" xmlns:a="{A}"><p:txBody>' + "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in paras) + "</p:txBody></p:sp>"
    slide = lambda body: f'<p:sld xmlns:p="{P_}" xmlns:a="{A}"><p:cSld><p:spTree>{body}</p:spTree></p:cSld></p:sld>'
    tbl = (f'<p:graphicFrame xmlns:p="{P_}" xmlns:a="{A}"><a:graphic><a:graphicData><a:tbl>'
           '<a:tr><a:tc><a:txBody><a:p><a:r><a:t>Layer</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody><a:p><a:r><a:t>Example</a:t></a:r></a:p></a:txBody></a:tc></a:tr>'
           '<a:tr><a:tc><a:txBody><a:p><a:r><a:t>Link</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody><a:p><a:r><a:t>Ethernet</a:t></a:r></a:p></a:txBody></a:tc></a:tr>'
           '</a:tbl></a:graphicData></a:graphic></p:graphicFrame>')
    return _zip({
        "ppt/presentation.xml": f'<p:presentation xmlns:p="{P_}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="256" r:id="rId2"/><p:sldId id="257" r:id="rId3"/><p:sldId id="258" r:id="rId1"/></p:sldIdLst></p:presentation>',
        "ppt/_rels/presentation.xml.rels": f'<Relationships xmlns="{REL}"><Relationship Id="rId1" Target="slides/slide1.xml"/><Relationship Id="rId2" Target="slides/slide2.xml"/><Relationship Id="rId3" Target="slides/slide3.xml"/></Relationships>',
        "ppt/slides/slide2.xml": slide(sp("Welcome to IFB102") + sp("Bits and bytes", "Why they matter")),
        "ppt/slides/slide3.xml": slide(sp("Networks") + sp("Layers of the stack")),
        "ppt/slides/_rels/slide3.xml.rels": f'<Relationships xmlns="{REL}"><Relationship Id="rId9" Target="../notesSlides/notesSlide1.xml"/></Relationships>',
        "ppt/notesSlides/notesSlide1.xml": slide(sp("Remind them about the quiz.") + sp("2")),
        "ppt/slides/slide1.xml": slide(tbl),
    })


def make_docx():
    para = lambda t, style=None, num=False: (f'<w:p><w:pPr>{f"<w:pStyle w:val={chr(34)}{style}{chr(34)}/>" if style else ""}{"<w:numPr/>" if num else ""}</w:pPr><w:r><w:t>{t}</w:t></w:r></w:p>')
    cell_ = lambda t: f"<w:tc>{para(t)}</w:tc>"
    body = (para("Assessment brief", "Heading1") + para("Write a report on one computer system.") + para("Write 500 words.", num=True) +
            f"<w:tbl><w:tr>{cell_('Criterion')}{cell_('Marks')}</w:tr><w:tr>{cell_('Analysis')}{cell_('10')}</w:tr></w:tbl>")
    return _zip({"word/document.xml": f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'})


VTT = 'WEBVTT\n\nNOTE made up for the tests\n\n1\n00:00:01.000 --> 00:00:03.000\n<v Lecturer>Welcome to week one.</v>\n\n2\n00:00:03.000 --> 00:00:05.000\nWelcome to week one. Today we cover\n\n3\n00:00:05.000 --> 00:00:07.000\nToday we cover networks &amp; graphs.\n\n4\n00:00:12.000 --> 00:00:14.000\nAfter a long pause, we continue\n\n5\n00:00:14.500 --> 00:01:15.000\nwith a second paragraph that runs past a minute and has no sentence end yet\n\n6\n00:01:15.000 --> 00:01:17.000\nuntil here.\n\n7\n00:01:17.500 --> 00:01:19.000\nA third paragraph starts.\n'
SRT = '1\n00:00:01,000 --> 00:00:02,500\nFirst line.\n\n2\n00:00:02,500 --> 00:00:04,000\nSecond line.\n'


class Helpers(unittest.TestCase):
    def test_vtt_to_paragraphs(self):
        cues = easel.merge_rolling(easel.parse_cues(VTT))
        paras = easel.paragraphs(cues)
        self.assertEqual(paras[0][2], "Welcome to week one. Today we cover networks & graphs.")   # rolling repeats merged, tags and entities gone
        self.assertEqual([easel.fmt_hms(s) for s, _, _ in paras], ["0:00:01", "0:00:12", "0:01:17"])
        self.assertTrue(paras[1][2].endswith("until here."))                                # the 60 s rule waits for a sentence end
        zoom = [(0, 2, "Ann Lee: Hello all."), (2, 4, "Ann Lee: Today is week two."), (4, 6, "Bob Ray: Can you hear me?"), (6, 8, "Ann Lee: Yes.")]
        paras = easel.paragraphs(zoom)
        self.assertEqual([(w, x) for _, w, x in paras], [("Ann Lee", "Hello all. Today is week two."), ("Bob Ray", "Can you hear me?"), ("Ann Lee", "Yes.")])
        self.assertEqual(easel.fmt_duration(3905), "1 h 05 min")
        self.assertEqual(easel.fmt_duration(600), "10 min")

    def test_srt_cues(self):
        cues = easel.parse_cues(SRT)
        self.assertEqual(cues, [(1.0, 2.5, "First line."), (2.5, 4.0, "Second line.")])
        self.assertIsNone(easel.choose_track([{"locale": "en", "content": ""}], "en-AU"))
        picked = easel.choose_track([{"locale": "fr", "content": "a"}, {"locale": "en-GB", "content": "b"}], "en-AU")
        self.assertEqual(picked["locale"], "en-GB")

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

    def test_transcripts_written_and_linked(self):
        b = make_bundle()
        page = b["modules"][0]["items"][0]
        page["body_md"] = ("Watch this.\n\n[Lecture 1.mp4](%s/media_attachments_iframe/77?embedded=true&type=video)\n\nTRANSCRIPT:att:77\n\n"
                           "- In a list:\n  [Silent clip.mp4](%s/media_attachments_iframe/78?embedded=true&type=video)\n  TRANSCRIPT:att:78\n"
                           "- Also listed:\n  [Lecture 1.mp4](%s/media_attachments_iframe/77?embedded=true&type=video)\n  TRANSCRIPT:att:77\n\nThe end.") % (ORIGIN, ORIGIN, ORIGIN)
        b["student_locale"] = "en-AU"
        b["media"] = {"att:77": {"kind": "attachment", "id": "77", "title": "Lecture 1.mp4", "status": 200,
                                 "tracks": [{"id": 1, "kind": "subtitles", "locale": "en-GB", "content": VTT}]},
                      "att:78": {"kind": "attachment", "id": "78", "title": "Silent clip.mp4", "status": 200, "tracks": []}}
        u = run_unit(b, self.root)
        T = self.unit_dir()
        tr = T / "Files" / "Week 01" / "Transcripts" / "Lecture 1.md"
        self.assertTrue(tr.exists())
        text = tr.read_text(encoding="utf-8")
        self.assertIn("easel: transcript", text)
        self.assertIn("**[0:00:01]** Welcome to week one.", text)
        week = (T / "3 Weeks" / "Week 01 - Basics.md").read_text(encoding="utf-8")
        self.assertIn("\n\nTranscript: [Lecture 1](../Files/Week%2001/Transcripts/Lecture%201.md)", week)
        self.assertIn("\n  Transcript: [Lecture 1](../Files/Week%2001/Transcripts/Lecture%201.md)", week)   # indented inside a list item
        self.assertNotIn("TRANSCRIPT:", week)
        self.assertFalse((T / "Files" / "Week 01" / "Transcripts" / "Silent clip.md").exists())
        self.assertIn("no transcript on Canvas: Silent clip", u.report)
        self.assertIn("1 transcript saved", u.summary)
        ok, bad, broken, leftovers, orphans = easel.check_links(T)
        self.assertEqual((bad, leftovers), (0, []), broken)
        self.assertNotIn("Files/Week 01/Transcripts/Lecture 1.md", orphans)
        # a second run changes nothing
        u2 = run_unit(b, self.root)
        self.assertEqual(u2.result["transcripts"]["unchanged"], 1)
        self.assertEqual(u2.result["written"], [])
        # the student's edit survives
        tr.write_text(text + "\nMy own line.\n", encoding="utf-8")
        u3 = run_unit(b, self.root)
        self.assertEqual(u3.result["transcripts"]["edited"], ["Lecture 1.md"])
        self.assertIn("My own line.", tr.read_text(encoding="utf-8"))

    def test_coverage_ledger(self):
        b = make_bundle()
        page = b["modules"][0]["items"][0]
        url = f"{ORIGIN}/courses/9/pages/welcome"
        page["body_md"] = ("Hello. Slides: [slides](FILE:502). Figure: [image: a diagram]\n\n"
                           "[Lecture 1.mp4](%s/media_attachments_iframe/77?type=video)\n\nTRANSCRIPT:att:77\n\n"
                           "[Silent clip.mp4](%s/media_attachments_iframe/78?type=video)\n\nTRANSCRIPT:att:78\n\n"
                           "[Lecture recording](https://echo360.net.au/lesson/1)\n\n[Quiz tool](%s/courses/9/external_tools/retrieve?url=https%%3A%%2F%%2Fh5p.com%%2Fx)\n\n"
                           "Read [the docs](https://www.python.org/doc/).") % (ORIGIN, ORIGIN, ORIGIN)
        b["refs"] = {url: [
            {"kind": "file", "id": "502", "title": "slides"},
            {"kind": "image", "id": "503", "title": "a diagram", "image": "alt text", "host": ""},
            {"kind": "image", "id": f"{ORIGIN}/files/900/preview", "title": "", "image": "no alt text", "host": ""},
            {"kind": "image", "id": f"{ORIGIN}/files/901/preview", "title": "logo", "image": "decorative", "host": ""},
            {"kind": "image", "id": f"{ORIGIN}/equation_images/x", "title": "x^2", "image": "equation"},
            {"kind": "media", "id": "att:77", "title": "Lecture 1.mp4"},
            {"kind": "media", "id": "att:78", "title": "Silent clip.mp4"},
            {"kind": "external", "id": "https://echo360.net.au/lesson/1", "title": "Lecture recording"},
            {"kind": "lti", "id": f"{ORIGIN}/courses/9/external_tools/retrieve?url=https%3A%2F%2Fh5p.com%2Fx", "title": "Quiz tool"},
            {"kind": "external", "id": "https://www.python.org/doc/", "title": "the docs"},
        ]}
        b["student_locale"] = "en-AU"
        b["media"] = {"att:77": {"kind": "attachment", "id": "77", "title": "Lecture 1.mp4", "status": 200,
                                 "tracks": [{"id": 1, "kind": "subtitles", "locale": "en-GB", "content": VTT}]},
                      "att:78": {"kind": "attachment", "id": "78", "title": "Silent clip.mp4", "status": 200, "tracks": []}}
        b["inbox_skipped"] = [{"id": 12, "subject": "Group chat", "reason": "no message from teaching staff"}]
        b["api_status"] = {"files": 403}
        b["modules"][1]["items"].append({"id": 22, "type": "ExternalUrl", "title": "Padlet board", "external_url": "https://padlet.com/x/y"})
        u = run_unit(b, self.root)
        T = self.unit_dir()
        data = json.loads((T / ".easel" / "coverage.json").read_text(encoding="utf-8"))
        rows = data["rows"]
        # copied: Welcome page, the equation image, the Assignment 1 card, the My notes page, the Overview page, 3 assessment notes,
        # 1 announcement, 1 Inbox thread. Then 1 transcript, 1 video without one, 3 links on the page plus the Padlet item,
        # 3 images and diagram.png and 1 Inbox thread skipped, 4 files saved, and the refused file list.
        expect = {"copied": 1 + 1 + 1 + 1 + 1 + 3 + 1 + 1, "transcript": 1, "unsupported": 1, "link": 3 + 1, "skipped": 3 + 1 + 1, "file": 4, "refused": 1}
        self.assertEqual(data["totals"]["outcome"], expect, json.dumps(rows, indent=1))
        self.assertEqual(len(rows), sum(expect.values()))
        self.assertEqual(data["totals"]["service"], {"Echo360": 1, "H5P": 1, "python.org": 1, "Padlet": 1})
        by = {(r["kind"], r["title"]): r for r in rows}
        self.assertEqual(by[("image", "x^2")]["outcome"], "copied")
        self.assertIn("decorative", by[("image", "logo")]["detail"])
        self.assertEqual(by[("image", "a diagram")]["found_in"], "Week 01 - Basics")
        self.assertEqual(by[("media", "Silent clip")]["detail"], "no transcript on Canvas")
        self.assertEqual(by[("conversation", "Group chat")]["outcome"], "skipped")
        self.assertEqual(by[("file", "file list")]["detail"], "HTTP 403")
        self.assertEqual(by[("file", "diagram.png")]["outcome"], "skipped")
        self.assertEqual(u.coverage_line, "ABC101: 10 items copied, 1 transcript, 4 files, 4 links (Echo360 1, H5P 1, Padlet 1), 1 refused, 1 unsupported, 4 images and 1 Inbox thread skipped")
        md = (T / ".easel" / "coverage.md").read_text(encoding="utf-8")
        self.assertTrue(md.startswith("# Coverage: ABC101\n\n" + u.coverage_line + "."))
        self.assertIn("### Week 01 - Basics", md)
        self.assertIn("coverage: 10 items copied", u.report)

        class Srv:
            units = {u.code: u}
            viewer_expected = []

            class run:
                @staticmethod
                def status():
                    return {}
        self.assertIn("\n  " + u.coverage_line, easel.summary_text(Srv, 10))
        # the second run writes the same ledger
        run_unit(b, self.root)
        self.assertEqual(json.loads((T / ".easel" / "coverage.json").read_text(encoding="utf-8"))["rows"], rows)
        self.assertEqual((T / ".easel" / "coverage.md").read_text(encoding="utf-8"), md)

    def test_q15_content(self):
        """Tool names, class statistics, dates, quiz attempts, a graded discussion outside modules, the staff fallback."""
        b = make_bundle()
        tool = f"{ORIGIN}/courses/9/external_tools/retrieve?display=in_rce&resource_link_lookup_uuid=abc"
        page = b["modules"][0]["items"][0]
        page["body_md"] = f"Watch [Embedded iframe]({tool}) and [Lecture 3](https://echo360.net.au/lesson/9) and [the docs](https://www.python.org/)."
        b["tools"] = {tool: {"status": 200, "host": "mediahub.canvas.qut.edu.au"}}
        b["refs"] = {f"{ORIGIN}/courses/9/pages/welcome": [{"kind": "lti", "id": tool, "title": "Embedded iframe"},
                                                             {"kind": "external", "id": "https://echo360.net.au/lesson/9", "title": "Lecture 3"},
                                                             {"kind": "external", "id": "https://www.python.org/", "title": "the docs"}]}
        b["assignments"][0]["score_statistics"] = {"min": 8, "max": 20, "mean": 14.5, "median": 15}
        b["assignments"][1]["is_quiz_lti"] = True
        disc = {"id": 77, "title": "Week 3 debate", "html_url": f"{ORIGIN}/courses/9/discussion_topics/77", "posted_at": "2026-08-01T00:00:00Z",
                "author": "Dr Tutor", "assignment_id": 104, "body_md": "Argue a side.", "attachments": [], "replies": {"status": 200, "entries": [
                    {"depth": 0, "author": "Ann", "created_at": "2026-08-02T00:00:00Z", "message_md": "I say yes."}]}}
        b["extra_discussions"] = [disc]
        b["assignments"].append({"id": 104, "name": "Debate post", "due_at": "2026-08-10T13:59:00Z", "points_possible": 10, "grading_type": "points",
                                 "published": True, "submission_types": ["discussion_topic"], "html_url": f"{ORIGIN}/courses/9/assignments/104",
                                 "assignment_group_id": 1, "rubric": [], "description_md": "Post once.", "discussion_id": 77, "submission": None})
        b["modules"][1]["items"].append({"id": 23, "type": "Quiz", "title": "Week 2 quiz", "content_id": 500, "html_url": f"{ORIGIN}/courses/9/quizzes/500",
            "quiz": {"question_count": 2, "points_possible": 2, "allowed_attempts": -1, "time_limit": None, "assignment_id": None, "quiz_type": "practice_quiz"},
            "body_md": "Try it.", "attempts": {"status": 200, "attempts": [{"id": 1, "attempt": 1, "score": 1, "kept_score": 1, "points_possible": 2,
            "finished_at": "2026-08-05T00:00:00Z", "questions_status": 200, "questions": [
                {"name": "Q1", "type": "true_false_question", "text_md": "<span>Bits are binary.</span>", "points": 1, "answers": ["True", "False"], "correct": True},
                {"name": "Q2", "type": "multiple_choice_question", "text_md": "A byte has", "points": 1, "answers": ["4 bits", "8 bits"], "correct": False}]}]}})
        b["events"] = [{"id": 5, "title": "Guest lecture", "start_at": "2026-09-10T04:00:00Z", "end_at": None, "all_day": False, "location": "Room 101",
                        "description_md": "Bring questions.", "html_url": f"{ORIGIN}/calendar?event_id=5"}]
        b["staff"] = []
        b["api_status"] = {"staff": 403}
        u = run_unit(b, self.root)
        T = self.unit_dir()
        week1 = (T / "3 Weeks" / "Week 01 - Basics.md").read_text(encoding="utf-8")
        self.assertIn(f"[MediaHub]({tool})", week1)                       # a generic label becomes the tool's name
        self.assertIn("[Lecture 3 (Echo360)](https://echo360.net.au/lesson/9)", week1)
        self.assertIn("[the docs](https://www.python.org/)", week1)        # an ordinary website keeps its label
        a1 = next((T / "2 Assessments").glob("Assignment 1*.md")).read_text(encoding="utf-8")
        self.assertIn("Class: mean 14.5, from 8 to 20 out of 20", a1)
        a2 = next((T / "2 Assessments").glob("Assignment 2*.md")).read_text(encoding="utf-8")
        self.assertIn("New Quiz: Canvas does not let students read the questions", a2)
        debate = next((T / "2 Assessments").glob("Debate post*.md")).read_text(encoding="utf-8")
        self.assertIn("[Read the thread and replies](../1%20Course%20Info/Discussions%20not%20in%20any%20module.md)", debate)
        other = (T / "1 Course Info" / "Discussions not in any module.md").read_text(encoding="utf-8")
        self.assertIn("I say yes.", other)
        self.assertIn("Open the assessment note", other)
        week2 = (T / "3 Weeks" / "Week 02 - More.md").read_text(encoding="utf-8")
        self.assertIn("### Your attempts", week2)
        self.assertIn("**Attempt 1** · 1 / 2", week2)
        self.assertIn("1. Bits are binary. ✓", week2)
        self.assertIn("2. A byte has ✗", week2)
        self.assertIn("Options: 4 bits; 8 bits", week2)
        info = (T / "1 Course Info" / "00 Course Info.md").read_text(encoding="utf-8")
        self.assertIn("## Dates", info)
        self.assertIn("[Guest lecture](", info)
        self.assertIn("Room 101", info)
        self.assertIn("Canvas refused the staff list (HTTP 403)", info)
        rows = json.loads((T / ".easel" / "coverage.json").read_text(encoding="utf-8"))["rows"]
        by = {(r["kind"], r["title"]): r for r in rows}
        self.assertEqual(by[("lti", "Embedded iframe")]["detail"], "MediaHub")
        self.assertEqual(by[("event", "Guest lecture")]["outcome"], "copied")
        self.assertEqual(by[("quiz", "Week 2 quiz")]["detail"], "description, settings and 1 attempt")
        self.assertIn("graded discussion", by[("discussion", "Week 3 debate")]["detail"])
        ok, bad, broken, leftovers, orphans = easel.check_links(T)
        self.assertEqual((bad, leftovers), (0, []), broken)
        u2 = run_unit(b, self.root)
        self.assertEqual(u2.result["written"], [])

    def test_q20_file_text(self):
        """A deck and a Word file get a text file beside them, linked from the note; a broken deck is reported."""
        b = make_bundle()
        b["files"]["504"] = {"id": "504", "display_name": "Week 1 lecture.pptx", "size": 0, "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "updated_at": "2026-07-01T00:00:00Z"}
        b["files"]["505"] = {"id": "505", "display_name": "Brief.docx", "size": 0, "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "updated_at": "2026-07-01T00:00:00Z"}
        b["files"]["506"] = {"id": "506", "display_name": "Broken.pptx", "size": 0, "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "updated_at": "2026-07-01T00:00:00Z"}
        b["modules"][0]["items"][0]["body_md"] = "Slides: [deck](FILE:504). Brief: [brief](FILE:505). Old: [old](FILE:506)."
        pptx, docx = make_pptx(), make_docx()
        b["files"]["504"]["size"], b["files"]["505"]["size"], b["files"]["506"]["size"] = len(pptx), len(docx), 3
        u = run_unit(b, self.root, blobs={"504": pptx, "505": docx, "506": b"bad"})
        T = self.unit_dir()
        deck = T / "Files" / "Week 01" / "Slides text" / "Week 1 lecture.md"
        self.assertTrue(deck.exists())
        text = deck.read_text(encoding="utf-8")
        self.assertIn("easel: slides", text)
        self.assertIn("slides: 3", text)
        self.assertIn("## Slide 1: Welcome to IFB102", text)
        self.assertIn("Bits and bytes", text)
        self.assertIn("## Slide 2: Networks", text)
        self.assertIn("**Speaker notes**\n\nRemind them about the quiz.", text)
        self.assertIn("## Slide 3", text)
        self.assertIn("| Layer | Example |", text)
        brief = T / "Files" / "Week 01" / "Document text" / "Brief.md"
        self.assertTrue(brief.exists())
        bt = brief.read_text(encoding="utf-8")
        self.assertIn("## Assessment brief", bt)
        self.assertIn("- Write 500 words.", bt)
        self.assertIn("| Criterion | Marks |", bt)
        week = (T / "3 Weeks" / "Week 01 - Basics.md").read_text(encoding="utf-8")
        self.assertIn("[deck](../Files/Week%2001/Week%201%20lecture.pptx) · [slide text](../Files/Week%2001/Slides%20text/Week%201%20lecture.md)", week)
        self.assertIn("[brief](../Files/Week%2001/Brief.docx) · [text](../Files/Week%2001/Document%20text/Brief.md)", week)
        self.assertIn("[old](../Files/Week%2001/Broken.pptx).", week)
        self.assertIn("unreadable: Broken.pptx (BadZipFile", u.report)
        self.assertIn("2 decks or documents as text", u.summary)
        rows = json.loads((T / ".easel" / "coverage.json").read_text(encoding="utf-8"))["rows"]
        by = {(r["kind"], r["title"]): r for r in rows}
        self.assertTrue(by[("file", "Week 1 lecture.pptx")]["detail"].startswith("saved; slide text saved, "))
        self.assertTrue(by[("file", "Broken.pptx")]["detail"].startswith("saved; text unreadable: BadZipFile"))
        ok, bad, broken, leftovers, orphans = easel.check_links(T)
        self.assertEqual((bad, leftovers), (0, []), broken)
        self.assertNotIn("Files/Week 01/Slides text/Week 1 lecture.md", orphans)
        u2 = run_unit(b, self.root, blobs={"504": pptx, "505": docx, "506": b"bad"})
        self.assertEqual(u2.result["texts"]["unchanged"], 2)
        self.assertEqual(u2.result["written"], [])
        deck.write_text(text + "\nMy own line.\n", encoding="utf-8")
        u3 = run_unit(b, self.root, blobs={"504": pptx, "505": docx, "506": b"bad"})
        self.assertEqual(u3.result["texts"]["edited"], ["Week 1 lecture.md"])

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


class Updates(unittest.TestCase):
    """The helper updates itself from the latest release, served here the way GitHub serves it."""

    def run_update(self, kit, base):
        env = {k: v for k, v in os.environ.items() if k != "EASEL_NO_UPDATE"}
        env.update(EASEL_HOME=TMP_HOME, EASEL_FROM=base)
        return subprocess.run([sys.executable, str(kit / "scripts" / "easel.py"), "update"], env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=60).stdout

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="easel-update-test-"))
        self.kit = self.tmp / "kit"
        shutil.copytree(ROOT / "skills" / "easel", self.kit, ignore=shutil.ignore_patterns("__pycache__"))
        self.release = release_files.stage(self.tmp / "release")
        self.httpd = release_files.server(self.release, 0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}/latest/download"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_update_from_newer_release(self):
        (self.release / "VERSION").write_text("9.9.9 (test)\n", encoding="utf-8")
        helper = (self.release / "easel.py").read_text(encoding="utf-8")
        (self.release / "easel.py").write_text(helper.replace('VERSION = "', '# updated in test\nVERSION = "', 1), encoding="utf-8")
        out = self.run_update(self.kit, self.base)
        self.assertIn(f"easel updated from {easel.VERSION} to 9.9.9.", out, out)
        self.assertEqual((self.kit / "VERSION").read_text(encoding="utf-8"), "9.9.9 (test)\n")
        self.assertIn("# updated in test", (self.kit / "scripts" / "easel.py").read_text(encoding="utf-8"))
        self.assertEqual([p.name for p in self.kit.iterdir() if p.name.startswith(".update-")], [])
        self.assertIn("is up to date", self.run_update(self.kit, self.base))

    def test_missing_release_changes_nothing(self):
        before = {p: p.read_bytes() for p in self.kit.rglob("*") if p.is_file()}
        out = self.run_update(self.kit, self.base + "/missing")
        self.assertIn("Couldn't check for updates", out, out)
        self.assertEqual({p: p.read_bytes() for p in self.kit.rglob("*") if p.is_file()}, before)


if __name__ == "__main__":
    unittest.main()
