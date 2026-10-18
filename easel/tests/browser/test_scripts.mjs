// Runs scrape.js and viewer.js against fake Canvas replies, with jsdom standing in for the tab.
// Checks that a failed, throttled, cut-off or unreadable read is reported as such, never as an empty answer.
//
//   cd easel/tests/browser && npm install && npm test
import {readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import path from "node:path";
import assert from "node:assert/strict";
import {JSDOM} from "jsdom";

const here = path.dirname(fileURLToPath(import.meta.url));
const scripts = path.join(here, "..", "..", "skills", "easel", "scripts");
const ORIGIN = "https://canvas.example.edu";
const SRV = "http://127.0.0.1:1";
let passed = 0;

function reply(status, body, headers = {}) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return {status, ok: status >= 200 && status < 300, headers: {get: (k) => headers[k.toLowerCase()] || null},
    text: async () => text, json: async () => JSON.parse(text), blob: async () => new Blob([text]), clone() { return this; }};
}

// A fake Canvas: routes is {pathWithQuery or path: handler | reply}. Unmatched Canvas paths answer 200 [].
function tab(routes, posted) {
  const dom = new JSDOM("<!doctype html><html><body></body></html>", {url: ORIGIN + "/", runScripts: "outside-only"});
  const w = dom.window;
  const calls = [];
  w.fetch = async (url, opts = {}) => {
    const u = new URL(url, ORIGIN);
    if (url.startsWith(SRV)) {
      const body = opts.body;
      posted.push({path: u.pathname + u.search, body: typeof body === "string" ? body : null});
      if (u.pathname === "/bundle") return reply(200, {need: [], feedback: []});
      return reply(200, "");
    }
    calls.push(u.pathname + u.search);
    const hit = routes[u.pathname + u.search] || routes[u.pathname];
    if (typeof hit === "function") return hit(calls.filter(c => c === u.pathname + u.search || c === u.pathname).length);
    if (hit) return hit;
    return reply(200, []);
  };
  w.performance = {now: () => Date.now()};
  w.calls = calls;
  return w;
}

async function runScrape(routes, cfg) {
  const posted = [];
  const w = tab(routes, posted);
  const js = readFileSync(path.join(scripts, "scrape.js"), "utf8").replaceAll("__CFG__", () => JSON.stringify({server: SRV, run: "t", version: "test", units: [cfg]}));
  w.eval(js.replace(/\(\d+\s*\*\s*\(i \+ 1\)\)/g, "(1)").replace("const RETRY_MAX_MS = 10000", "const RETRY_MAX_MS = 5"));   // short waits
  await w.__EASEL_RUN;
  const b = posted.find(p => p.path.startsWith("/bundle"));
  return {bundle: b ? JSON.parse(b.body) : null, posted, calls: w.calls};
}

const course = {id: 9, name: "ABC101 Test", course_code: "ABC101"};
const base = {
  "/api/v1/users/self": reply(200, {id: 1, locale: "en-AU"}),
  "/api/v1/courses/9": reply(200, course),
  "/api/v1/courses/9?include[]=syllabus_body&include[]=term&include[]=teachers": reply(200, {...course, syllabus_body: ""}),
  "/api/v1/courses/9/assignments?per_page=100&order_by=due_at&include[]=score_statistics": reply(200, [{id: 101, name: "A1", points_possible: 20, html_url: ORIGIN + "/courses/9/assignments/101"}]),
  "/api/v1/courses/9/students/submissions?student_ids[]=self&include[]=submission_comments&include[]=rubric_assessment&include[]=submission_history&per_page=100":
    reply(200, [{id: 7001, assignment_id: 101, score: 15, workflow_state: "graded", submission_comments: [], attachments: []}]),
};
const unit = {unit: "ABC101", course_id: 9};

async function test(name, fn) { await fn(); passed++; console.log("ok - " + name); }

await test("a good run records 200 for every list and the mark", async () => {
  const {bundle} = await runScrape(base, unit);
  assert.equal(bundle.api_status.submissions, 200);
  assert.equal(bundle.assignments[0].submission.score, 15);
  assert.equal(bundle.api_status.modules, 200);
});

await test("a server error after the retries is reported, not turned into an empty answer", async () => {
  const routes = {...base};
  const key = "/api/v1/courses/9/students/submissions?student_ids[]=self&include[]=submission_comments&include[]=rubric_assessment&include[]=submission_history&per_page=100";
  routes[key] = () => reply(503, "down");
  const {bundle, calls} = await runScrape(routes, unit);
  assert.equal(bundle.api_status.submissions, 503);
  assert.equal(bundle.assignments[0].submission, null);
  assert.equal(calls.filter(c => c === key).length, 5);       // five tries, then give up
});

await test("throttling is retried with the Retry-After wait, then the answer counts", async () => {
  const routes = {...base};
  const key = "/api/v1/courses/9/students/submissions?student_ids[]=self&include[]=submission_comments&include[]=rubric_assessment&include[]=submission_history&per_page=100";
  routes[key] = (n) => n < 3 ? reply(429, "slow down", {"retry-after": "0.001"}) : base[key];
  const {bundle, calls} = await runScrape(routes, unit);
  assert.equal(bundle.api_status.submissions, 200);
  assert.equal(bundle.assignments[0].submission.score, 15);
  assert.equal(calls.filter(c => c === key).length, 3);
});

await test("a cut-off list is incomplete, with the pages that arrived", async () => {
  const routes = {...base};
  routes["/api/v1/courses/9/discussion_topics?only_announcements=true&per_page=100"] = reply(200, [{id: 1, title: "One", message: "<p>x</p>", html_url: ORIGIN + "/x"}],
    {link: `<${ORIGIN}/api/v1/courses/9/discussion_topics?only_announcements=true&per_page=100&page=2>; rel="next"`});
  routes["/api/v1/courses/9/discussion_topics?only_announcements=true&per_page=100&page=2"] = () => reply(502, "bad gateway");
  const {bundle} = await runScrape(routes, unit);
  assert.equal(bundle.api_status.announcements, "incomplete");
  assert.equal(bundle.announcements.length, 0);              // the helper decides what to keep; nothing is passed off as complete
});

await test("an unreadable reply is malformed, not empty", async () => {
  const routes = {...base};
  routes["/api/v1/courses/9/assignment_groups?per_page=100"] = reply(200, "<html>maintenance</html>");
  const {bundle} = await runScrape(routes, unit);
  assert.equal(bundle.api_status.assignment_groups, "malformed");
  assert.deepEqual(bundle.assignment_groups, []);
});

await test("a network failure is status 0, and the run still finishes", async () => {
  const routes = {...base};
  routes["/api/v1/courses/9/users?enrollment_type[]=teacher&enrollment_type[]=ta&enrollment_type[]=designer&include[]=enrollments&per_page=100"] = () => { throw new TypeError("Failed to fetch"); };
  const {bundle, posted} = await runScrape(routes, unit);
  assert.equal(bundle.api_status.staff, 0);
  assert.ok(posted.some(p => p.path.startsWith("/done")));
});

await test("a page that fails inside a module keeps its status for the helper", async () => {
  const routes = {...base};
  routes["/api/v1/courses/9/modules?include[]=items&include[]=content_details&per_page=100"] = reply(200, [{id: 1, name: "Week 1", position: 1,
    items: [{id: 11, type: "Page", title: "Welcome", page_url: "welcome", html_url: ORIGIN + "/courses/9/pages/welcome"}]}]);
  routes["/api/v1/courses/9/pages/welcome"] = () => reply(500, "err");
  const {bundle} = await runScrape(routes, unit);
  const it = bundle.modules[0].items[0];
  assert.equal(it.status, 500);
  assert.equal(it.body_md, undefined);
  assert.equal(bundle.modules[0].items_status, 200);
});

await test("a signed-out tab reports login instead of scraping", async () => {
  const routes = {...base, "/api/v1/users/self": reply(401, {errors: "unauthenticated"})};
  const {bundle, posted} = await runScrape(routes, unit);
  assert.equal(bundle, null);
  assert.ok(posted.some(p => p.path.startsWith("/login")));
});

// ---- viewer.js: annotations and the merged PDF, with failures reported as status text
async function runViewer(fetchImpl, docs = [{key: "7001-601", url: "https://canvadocs.example/view/1"}]) {
  const hash = "#easel=" + encodeURIComponent(JSON.stringify({run: "t", docs}));
  const dom = new JSDOM("<!doctype html><html><body></body></html>", {url: "https://canvadocs.example/view/1" + hash, runScripts: "outside-only"});
  const w = dom.window;
  w.DocViewer = {accessToken: "tok", documentId: "doc1"};
  w.Blob = Blob;                                   // Node's Blob has text(); jsdom's does not
  w.fetch = fetchImpl;
  let saved = null;
  w.URL.createObjectURL = (blob) => { saved = blob; return "blob:x"; };
  w.HTMLAnchorElement.prototype.click = function () {};
  w.FileReader = class { readAsDataURL(blob) { blob.text().then(t => { this.result = "data:x;base64," + Buffer.from(t).toString("base64"); this.onload(); }); } };
  const js = readFileSync(path.join(scripts, "viewer.js"), "utf8").replace(/^\/\/.*$/gm, "");
  const started = w.eval(js);
  for (let i = 0; i < 200 && w.__easelViewer.state !== "saved"; i++) await new Promise(r => setTimeout(r, 10));
  return {started, state: w.__easelViewer, results: JSON.parse(await saved.text()).results};
}

await test("viewer: annotations and the merged PDF are collected", async () => {
  const {results} = await runViewer(async (url, opts = {}) => {
    if (url.endsWith("/annotations")) return reply(200, {data: [{id: "a1", type: "text", page: 0, user_name: "Dr Tutor", contents: "Cite this."}]});
    if (url.endsWith("/merged-documents")) return reply(200, {mergedDocumentId: "m1"});
    if (url.endsWith("/is_ready")) return reply(200, {ready: true});
    if (url.endsWith("/single-use-download-link")) return reply(200, {singleUseDownloadUrl: "https://canvadocs.example/dl"});
    if (url.endsWith("/dl")) return reply(200, "%PDF-1.4 fake");
    return reply(404, "");
  });
  assert.equal(results[0].status, "ok");
  assert.equal(results[0].annotations[0].contents, "Cite this.");
  assert.equal(Buffer.from(results[0].pdf, "base64").toString(), "%PDF-1.4 fake");
});

await test("viewer: a failed annotation read is reported as its status, with nothing invented", async () => {
  const {results} = await runViewer(async (url) => url.endsWith("/annotations") ? reply(503, "down") : reply(404, ""));
  assert.equal(results[0].status, "annotations HTTP 503");
  assert.equal(results[0].pdf, undefined);
});

await test("viewer: a merge that never becomes ready times out with its annotations kept", async () => {
  const {results} = await runViewer(async (url) => {
    if (url.endsWith("/annotations")) return reply(200, {data: [{id: "a1", type: "text", page: 0, contents: "x"}]});
    if (url.endsWith("/merged-documents")) return reply(500, "no");
    return reply(404, "");
  });
  assert.equal(results[0].status, "merge HTTP 500");
  assert.equal(results[0].annotations.length, 1);
});

console.log(`${passed} browser-script tests passed`);
