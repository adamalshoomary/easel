// easel browser script. The helper serves this file and replaces __CFG__.
// It runs in a signed-in Canvas tab. It reads the Canvas API with the student's session,
// converts HTML to Markdown with the browser's own parser, and posts the results and the
// file bytes to the helper on 127.0.0.1. It sends Canvas read requests only.
(() => {
const CFG = __CFG__;
const SRV = CFG.server;
const ORIGIN = location.origin;

const post = (path, body, type) => fetch(SRV + path, {method: 'POST', body, headers: type ? {'Content-Type': type} : {}});
const log = (msg) => post('/log?run=' + CFG.run, String(msg)).catch(() => {});
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// At most eight Canvas requests run at once, across all units.
let inFlight = 0;
const waiting = [];
async function slot(fn) {
  while (inFlight >= 8) await new Promise(r => waiting.push(r));
  inFlight++;
  try { return await fn(); } finally { inFlight--; const next = waiting.shift(); if (next) next(); }
}

async function api(url, {all = false, tries = 5} = {}) {
  let out = [], next = url.startsWith('http') ? url : ORIGIN + url, status = 0;
  while (next) {
    const r = await slot(async () => {
      let res;
      for (let i = 0; i < tries; i++) {
        res = await fetch(next, {headers: {Accept: 'application/json'}, credentials: 'include'});
        if (res.status === 403 && /rate limit/i.test(await res.clone().text())) { await sleep(1500 * (i + 1)); continue; }
        if (res.status >= 500) { await sleep(1000 * (i + 1)); continue; }
        break;
      }
      return res;
    });
    status = r.status;
    const txt = (await r.text()).replace(/^while\(1\);/, '');
    let data; try { data = JSON.parse(txt); } catch { data = null; }
    if (!r.ok) return {status, data};
    if (!all) return {status, data};
    out = out.concat(Array.isArray(data) ? data : []);
    const m = (r.headers.get('Link') || '').match(/<([^>]+)>;\s*rel="next"/);
    next = m ? m[1] : null;
  }
  return {status, data: out};
}

// GraphQL is a POST, but these queries only read.
async function graphql(query, variables) {
  const csrf = decodeURIComponent((document.cookie.match(/(?:^|;\s*)_csrf_token=([^;]+)/) || [])[1] || '');
  try {
    const r = await slot(() => fetch(ORIGIN + '/api/graphql', {method: 'POST', credentials: 'include',
      headers: {'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRF-Token': csrf},
      body: JSON.stringify({query, variables})}));
    const d = await r.json().catch(() => null);
    return {status: r.status, data: d && d.data, errors: d && d.errors};
  } catch (e) { return {status: 0, data: null, errors: [String(e)]}; }
}

async function pool(items, n, fn) {
  const res = new Array(items.length); let i = 0;
  await Promise.all(Array.from({length: Math.min(n, items.length)}, async () => {
    while (i < items.length) { const k = i++; try { res[k] = await fn(items[k], k); } catch (e) { res[k] = {error: String(e)}; } }
  }));
  return res;
}

// ---------- HTML to Markdown (recursive, no ordering traps) ----------
const FILE_RE = /\/files\/(\d+)|[?&]preview=(\d+)/;
const isCanvas = (u) => { try { return new URL(u).origin === ORIGIN; } catch { return false; } };
const enc = (u) => u.replace(/ /g, '%20').replace(/\(/g, '%28').replace(/\)/g, '%29');
const DECOR = /\b(logo|icon|banner|sub-?banner|divider|spacer|bullet|decorative)\b/i;
const IMG_NAME = /\.(png|jpe?g|gif|svg|webp|bmp|tiff?)$/i;
const BLOCK = new Set(['p','div','section','article','header','footer','main','aside','figure','figcaption','details','summary','dl','dt','dd','address','center','nav','form','fieldset']);
const SKIP = new Set(['script','style','noscript','template','button','input','select','textarea','svg','canvas','object','head','title','meta','link']);

function MD(html, base) {
  if (!html) return {md: '', files: [], expected: 0, missing: []};
  const doc = new DOMParser().parseFromString('<div id="__r">' + html + '</div>', 'text/html');
  const root = doc.getElementById('__r');
  const files = new Set();
  const abs = (h) => { try { return new URL(h, base || ORIGIN + '/').href; } catch { return h; } };
  const inline = (s) => s.replace(/\s*\n\s*/g, ' ').replace(/ {2,}/g, ' ').trim();
  const wrap = (s, mark) => { if (!s.trim() || s.includes('\n')) return s; const m = s.match(/^(\s*)([\s\S]*?)(\s*)$/); return m[1] + mark + m[2] + mark + m[3]; };
  const block = (s) => { s = s.trim(); return s ? '\n\n' + s + '\n\n' : ''; };

  // text of a <pre>, keeping line breaks that editors store as <br> or <div>/<p>
  function preText(n) {
    let s = '';
    for (const k of n.childNodes) {
      if (k.nodeType === 3) s += k.nodeValue;
      else if (k.nodeType === 1) {
        const t = k.tagName.toLowerCase();
        if (t === 'br') s += '\n';
        else if (t === 'div' || t === 'p') { const x = preText(k); s += (s && !s.endsWith('\n') ? '\n' : '') + x + (x.endsWith('\n') ? '' : '\n'); }
        else s += preText(k);
      }
    }
    return s;
  }

  function kids(n, c) { let s = ''; for (const k of n.childNodes) s += conv(k, c); return s; }

  function conv(n, c) {
    if (n.nodeType === 3) return c.pre ? n.nodeValue : n.nodeValue.replace(/[ \t\r\n\f]+/g, ' ');
    if (n.nodeType !== 1) return '';
    const tag = n.tagName.toLowerCase();
    if (SKIP.has(tag)) return '';
    const cls = n.getAttribute('class') || '';
    if (/\bscreenreader-only\b/.test(cls)) return '';
    if (/^h[1-6]$/.test(tag)) {
      const t = inline(kids(n, {...c, heading: true}));
      return t ? '\n\n' + '#'.repeat(+tag[1]) + ' ' + t + '\n\n' : '';
    }
    switch (tag) {
      case 'br': return c.cell ? '<br>' : '\n';
      case 'hr': return '\n\n---\n\n';
      case 'a': {
        const h = n.getAttribute('href') || '';
        let t = inline(kids(n, {...c, link: true}));
        if (!t) { const im = n.querySelector('img[alt]'); t = im ? im.getAttribute('alt').trim() : ''; }
        if (!h || h.startsWith('javascript:')) return t;
        const u = abs(h);
        const f = isCanvas(u) && u.match(FILE_RE);
        if (f && !/\/users\/\d+\/files/.test(u)) { const id = f[1] || f[2]; files.add(id); return '[' + t + '](FILE:' + id + ')'; }
        if (u.startsWith(ORIGIN) && h.startsWith('#')) return t;
        return '[' + (t || u) + '](' + enc(u) + ')';
      }
      case 'img': {
        if (/\bequation_image\b/.test(cls)) { const tex = n.getAttribute('data-equation-content') || n.getAttribute('alt') || ''; return tex ? '$' + tex.trim() + '$' : ''; }
        const alt = (n.getAttribute('alt') || '').trim();
        if (c.link || !alt || IMG_NAME.test(alt) || /^image$/i.test(alt) || DECOR.test(alt)) return '';
        return '[image: ' + alt + ']';
      }
      case 'iframe': case 'video': case 'audio': case 'embed': {
        let src = n.getAttribute('src') || (n.querySelector && n.querySelector('source[src]') ? n.querySelector('source[src]').getAttribute('src') : '') || '';
        if (src) src = abs(src);
        const title = (n.getAttribute('title') || '').trim();
        return src ? '\n\n[' + (title || 'Embedded ' + tag) + '](' + enc(src) + ')\n\n' : '';
      }
      case 'pre': {
        const t = preText(n).replace(/^\n+|\s+$/g, '');
        return '\n\n```\n' + t + '\n```\n\n';
      }
      case 'code': case 'kbd': case 'samp': case 'tt': {
        if (c.pre) return n.textContent;
        if (n.querySelector('br')) { const b = preText(n).replace(/^\n+|\s+$/g, ''); return b.trim() ? '\n\n```\n' + b + '\n```\n\n' : ''; }
        const t = n.textContent; if (!t.trim()) return t;
        const tick = t.includes('`') ? '``' : '`';
        return tick + t.replace(/\s+/g, ' ') + tick;
      }
      case 'strong': case 'b': {
        const t = kids(n, {...c, strong: true});
        return c.heading || c.strong ? t : wrap(t, '**');
      }
      case 'em': case 'i': case 'cite': {
        const t = kids(n, {...c, em: true});
        return c.heading || c.em ? t : wrap(t, '*');
      }
      case 's': case 'strike': case 'del': return wrap(kids(n, c), '~~');
      case 'ul': case 'ol': {
        let num = parseInt(n.getAttribute('start') || '1', 10) || 1;
        const lines = [];
        for (const li of n.children) {
          if (li.tagName.toLowerCase() !== 'li') { const t = conv(li, c).trim(); if (t) lines.push(t); continue; }
          const mark = tag === 'ol' ? (num++) + '. ' : '- ';
          let t = kids(li, {...c, cell: false}).replace(/[ \t]+\n/g, '\n').replace(/\n{2,}/g, '\n').trim();
          const pad = ' '.repeat(mark.length);
          t = t.split('\n').map((l, i) => i ? (l.trim() ? pad + l : l) : l).join('\n');
          lines.push(mark + t);
        }
        return lines.length ? '\n\n' + lines.join('\n') + '\n\n' : '';
      }
      case 'li': return '\n- ' + kids(n, c).trim() + '\n';
      case 'table': {
        const rows = [...n.querySelectorAll(':scope > tr, :scope > thead > tr, :scope > tbody > tr, :scope > tfoot > tr')];
        const capEl = n.querySelector(':scope > caption');
        const capT = capEl ? inline(kids(capEl, c)) : '';
        const lead = capT ? '\n\n' + capT + '\n\n' : '';
        // Markdown tables cannot hold code blocks, headings or nested tables: lay the cells out as blocks
        if (n.querySelector('pre, h1, h2, h3, h4, h5, h6, table')) {
          const out = [];
          for (const r of rows) for (const cell of r.children) {
            if (!/^t[hd]$/i.test(cell.tagName)) continue;
            const t = kids(cell, c).trim();
            if (t) out.push(cell.tagName.toLowerCase() === 'th' && !t.includes('\n') && !/^(#|\*\*)/.test(t) ? '**' + t.replace(/^\*\*|\*\*$/g, '') + '**' : t);
          }
          return lead + block(out.join('\n\n'));
        }
        const grid = rows.map(r => {
          const cells = [];
          for (const cell of r.children) {
            if (!/^t[hd]$/i.test(cell.tagName)) continue;
            const t = kids(cell, {...c, cell: true}).replace(/\n{2,}/g, '\n').trim().replace(/\n/g, '<br>').replace(/\|/g, '\\|').replace(/[ \t]{2,}/g, ' ');
            cells.push(t);
            for (let k = 1; k < (+cell.getAttribute('colspan') || 1); k++) cells.push('');
          }
          return cells;
        }).filter(r => r.length);
        if (!grid.length) return lead;
        const ncol = Math.max(...grid.map(r => r.length));
        if (ncol === 1 && grid.length === 1) return lead + block(kids(rows[0].children[0], c));
        const line = (r) => '| ' + Array.from({length: ncol}, (_, k) => r[k] || '').join(' | ') + ' |';
        const out = [line(grid[0]), '| ' + Array(ncol).fill('---').join(' | ') + ' |', ...grid.slice(1).map(line)];
        return lead + '\n\n' + out.join('\n') + '\n\n';
      }
      case 'caption': return '';
      case 'blockquote': {
        const t = kids(n, c).replace(/\n{3,}/g, '\n\n').trim();
        return t ? '\n\n' + t.split('\n').map(l => '> ' + l).join('\n') + '\n\n' : '';
      }
    }
    if (tag === 'span' && !c.pre && /font-family:[^;"]*(courier|monospace|consolas|menlo)/i.test(n.getAttribute('style') || '')) {
      const t = n.textContent;
      if (t.trim() && !t.includes('\n') && !n.querySelector('a,img,br')) { const tick = t.includes('`') ? '``' : '`'; return tick + t.replace(/\s+/g, ' ') + tick; }
    }
    if (BLOCK.has(tag)) return c.cell ? kids(n, c) + '\n' : block(kids(n, c));
    return kids(n, c);
  }

  // words the browser itself would show, for the coverage check
  const words = (t) => (t.toLowerCase().match(/[\p{L}\p{N}]+/gu) || []);
  const shown = root.cloneNode(true);
  shown.querySelectorAll([...SKIP].join(',') + ',.screenreader-only').forEach(x => x.remove());
  shown.querySelectorAll('br,p,div,li,td,th,tr,h1,h2,h3,h4,h5,h6,pre,table,caption,blockquote,section,article,ul,ol,dt,dd,a,hr,figure,figcaption,summary,details').forEach(x => { x.before(' '); x.after(' '); });
  const expected = words(shown.textContent.replace(/[\u200b\u200c\u200d\ufeff\u00ad]/g, ''));

  let md = conv(root, {});
  md = md.replace(/\u00a0/g, ' ').replace(/[\u200b\u200c\u200d\ufeff\u00ad]/g, '').replace(/\r\n?/g, '\n');
  md = md.split(/(\n```\n[\s\S]*?\n```\n)/).map((part, i) => i % 2 ? part :
    part.replace(/[ \t]+$/gm, '').replace(/^ (?=\S)/gm, '').replace(/\n{3,}/g, '\n\n')).join('');
  md = md.replace(/\n{3,}/g, '\n\n').trim();
  const have = new Map();
  for (const w of words(md.replace(/[*`~]/g, ''))) have.set(w, (have.get(w) || 0) + 1);
  const missing = [];
  for (const w of expected) { const k = have.get(w) || 0; if (k) have.set(w, k - 1); else missing.push(w); }
  return {md, files: [...files], expected: expected.length, missing};
}

window.__EASEL_MD = MD;   // for checking a single page in the console

// ---------- one unit ----------
const unitRe = (unit) => new RegExp('(^|[^A-Za-z0-9])' + unit.replace(/[^A-Za-z0-9]/g, '') + '(?![0-9])', 'i');

async function findCourse(unit, knownId) {
  if (knownId) {
    const r = await api(`/api/v1/courses/${knownId}`);
    if (r.status === 200 && r.data) return r.data;
  }
  const re = unitRe(unit);
  for (const q of ['enrollment_state=active&', '']) {
    const r = await api(`/api/v1/courses?${q}per_page=100`, {all: true});
    const hits = (r.data || []).filter(c => re.test((c.course_code || '') + ' ' + (c.name || '')));
    if (hits.length) return hits.sort((a, b) => b.id - a.id)[0];
  }
  return null;
}

let groupsOnce = null;
const myGroups = () => groupsOnce || (groupsOnce = api('/api/v1/users/self/groups?per_page=100', {all: true}));

const viewerDocs = [];   // filled as units finish: {key, unit, url}

async function scrapeUnit(U) {
  const t0 = performance.now();
  const course = await findCourse(U.unit, U.course_id);
  if (!course) { await post(`/error?unit=${U.unit}&run=${CFG.run}`, 'No Canvas course matches ' + U.unit + '. Check the unit code.'); return U.unit + ': not found'; }
  const cid = course.id, B = `/api/v1/courses/${cid}`;
  const page = (slug) => `${ORIGIN}/courses/${cid}/pages/${slug}`;
  await log(`${U.unit}: course ${cid}`);

  const [mods, asg, ann, crs, tabs, disc, groupsR, subs, pagesAll, filesAll, front, staffR, inboxA, inboxB, scheme] = await Promise.all([
    api(`${B}/modules?include[]=items&include[]=content_details&per_page=100`, {all: true}),
    api(`${B}/assignments?per_page=100&order_by=due_at`, {all: true}),
    api(`${B}/discussion_topics?only_announcements=true&per_page=100`, {all: true}),
    api(`${B}?include[]=syllabus_body&include[]=term&include[]=teachers`),
    api(`${B}/tabs`),
    api(`${B}/discussion_topics?per_page=100`, {all: true}),
    api(`${B}/assignment_groups?per_page=100`, {all: true}),
    api(`${B}/students/submissions?student_ids[]=self&include[]=submission_comments&include[]=rubric_assessment&include[]=submission_history&per_page=100`, {all: true}),
    api(`${B}/pages?per_page=100`, {all: true}),
    api(`${B}/files?per_page=100`, {all: true}),
    api(`${B}/front_page`),
    api(`${B}/users?enrollment_type[]=teacher&enrollment_type[]=ta&enrollment_type[]=designer&include[]=enrollments&per_page=100`, {all: true}),
    api(`/api/v1/conversations?scope=inbox&filter[]=course_${cid}&per_page=100`, {all: true}),
    api(`/api/v1/conversations?scope=archived&filter[]=course_${cid}&per_page=100`, {all: true}),
    graphql('query($id: ID!) { course(id: $id) { gradingStandard { title data { letterGrade baseValue } } } }', {id: String(cid)}),
  ]);
  const ok = (r) => r.status === 200 && Array.isArray(r.data) ? r.data : [];

  const allFiles = new Set();
  const fileMeta = {};
  const coverage = {words: 0, missing: 0, pages: []};
  const md = (html, base) => {
    const r = MD(html, base); r.files.forEach(f => allFiles.add(f));
    coverage.words += r.expected || 0;
    if (r.missing && r.missing.length) { coverage.missing += r.missing.length; coverage.pages.push({url: base, missing: r.missing.slice(0, 12), n: r.missing.length}); }
    return r.md;
  };
  // Files that are not course files: the student's submission, feedback files and Inbox attachments.
  const ownFile = (a, extra) => {
    const id = String(a.id);
    fileMeta[id] = {id, display_name: a.display_name, filename: a.filename, size: a.size, content_type: a['content-type'] || a.content_type,
      updated_at: a.updated_at, url: a.url, ...extra};
    return id;
  };

  // ---- teaching staff, groups, Inbox
  const staff = ok(staffR).map(u => {
    const roles = [...new Set((u.enrollments || []).filter(e => e.course_id === cid || !e.course_id).map(e => e.role || e.type))];
    return {id: u.id, name: u.name, sortable_name: u.sortable_name, roles: roles.length ? roles : ['Teaching staff']};
  });
  const staffIds = new Set(staff.map(s => s.id));
  const groups = [];
  for (const g of ok(await myGroups())) {
    if (String(g.course_id) !== String(cid)) continue;
    const m = await api(`/api/v1/groups/${g.id}/users?per_page=100`, {all: true});
    groups.push({id: g.id, name: g.name, members: ok(m).map(u => u.name)});
  }
  const convs = new Map();
  for (const c of [...ok(inboxA), ...ok(inboxB)]) convs.set(c.id, c);
  const inbox = [];
  await pool([...convs.values()].slice(0, 100), 4, async (c) => {
    const r = await api(`/api/v1/conversations/${c.id}?auto_mark_as_read=false`);
    if (r.status !== 200 || !r.data) return;
    const who = {};
    for (const p of (r.data.participants || [])) who[p.id] = p.name || p.full_name;
    const msgs = (r.data.messages || []).map(m => ({author: who[m.author_id] || null, author_id: m.author_id, staff: staffIds.has(m.author_id),
      created_at: m.created_at, body: (m.body || '').replace(/\r\n?/g, '\n'),
      attachments: (m.attachments || []).map(a => ownFile(a, {role: 'inbox'}))}));
    if (!msgs.some(m => m.staff)) return;   // keep conversations with a message from teaching staff
    inbox.push({id: c.id, subject: r.data.subject || '(no subject)', last_at: r.data.last_message_at || c.last_message_at, messages: msgs.reverse()});
  });

  // ---- assignments, rubrics, submissions
  // Rubric text is plain text in some rubrics and HTML in others. Keep its line breaks either way.
  const mdText = (s, base) => md(/<[a-z][\s\S]*>/i.test(s || '') ? s : String(s || '').replace(/\r?\n/g, '<br>'), base);
  const rubricOf = (a) => (a.rubric || []).map(c => ({id: c.id, description: c.description, long_description: mdText(c.long_description, a.html_url),
    points: c.points, use_range: !!c.criterion_use_range, ignore: !!c.ignore_for_scoring,
    ratings: (c.ratings || []).map(r => ({id: r.id, description: r.description, long_description: mdText(r.long_description, a.html_url), points: r.points}))}));
  const rubricSettings = (a) => a.rubric_settings ? {title: a.rubric_settings.title, points_possible: a.rubric_settings.points_possible,
    free_form: !!a.rubric_settings.free_form_criterion_comments, hide_score_total: !!a.rubric_settings.hide_score_total, hide_points: !!a.rubric_settings.hide_points} : null;
  const subByAsg = {};
  for (const s of ok(subs)) subByAsg[s.assignment_id] = s;
  const feedbackCandidates = [];
  const previewUrl = {};
  const submissionOf = (aid) => {
    const s = subByAsg[aid];
    if (!s) return null;
    const files = (s.attachments || []).map(a => {
      const id = ownFile(a, {role: 'submission', assignment_id: aid});
      if (a.preview_url) { const key = `${s.id}-${a.id}`; previewUrl[key] = ORIGIN + a.preview_url; feedbackCandidates.push({key, assignment_id: aid, file_id: id, graded_at: s.graded_at, posted_at: s.posted_at}); }
      return id;
    });
    const comments = (s.submission_comments || []).map(c => ({id: c.id, author: c.author_name, author_id: c.author_id, staff: staffIds.has(c.author_id),
      created_at: c.created_at, attempt: c.attempt || null, comment: (c.comment || '').replace(/\r\n?/g, '\n'),
      attachments: (c.attachments || []).map(a => ownFile(a, {role: 'feedback', assignment_id: aid})),
      media: c.media_comment ? {type: c.media_comment.media_type, url: c.media_comment.url || null} : null}));
    if (!s.submitted_at && s.score == null && !comments.length && !s.excused && !s.missing && !files.length) return null;
    return {id: s.id, workflow_state: s.workflow_state, attempt: s.attempt, submitted_at: s.submitted_at, graded_at: s.graded_at, posted_at: s.posted_at,
      score: s.score, grade: s.grade, late: !!s.late, missing: !!s.missing, excused: !!s.excused, seconds_late: s.seconds_late || 0,
      submission_type: s.submission_type, url: s.url || null, body_md: s.body ? md(s.body, ORIGIN) : '', files, comments,
      rubric_assessment: s.rubric_assessment || null,
      history: (s.submission_history || []).filter(h => h.attempt && h.attempt !== s.attempt).map(h => ({attempt: h.attempt, submitted_at: h.submitted_at,
        files: (h.attachments || []).map(a => a.display_name)}))};
  };
  const asgObj = (a) => ({id: a.id, name: a.name, due_at: a.due_at, unlock_at: a.unlock_at, lock_at: a.lock_at, points_possible: a.points_possible,
    grading_type: a.grading_type, omit_from_final_grade: !!a.omit_from_final_grade, submission_types: a.submission_types,
    allowed_attempts: a.allowed_attempts, html_url: a.html_url, updated_at: a.updated_at, position: a.position,
    quiz_id: a.quiz_id || null, is_quiz_lti: !!a.is_quiz_lti_assignment, discussion_id: a.discussion_topic ? a.discussion_topic.id : null,
    group_category_id: a.group_category_id || null, published: a.published !== false,
    locked: !!a.locked_for_user, lock_explanation: a.lock_explanation || null,
    assignment_group_id: a.assignment_group_id || null, rubric: rubricOf(a), rubric_settings: rubricSettings(a),
    submission: submissionOf(a.id), description_md: md(a.description, a.html_url)});
  const asgById = {};
  const assignments = ok(asg).map(a => (asgById[a.id] = asgObj(a)));

  const discById = {};
  for (const d of ok(disc)) discById[d.id] = d;
  const modules = mods.data || [];
  for (const m of modules) if (!m.items && m.items_url) m.items = ok(await api(m.items_url + '?per_page=100', {all: true}));

  const repliesOf = async (tid) => {
    const r = await api(`${B}/discussion_topics/${tid}/view`);
    if (r.status !== 200 || !r.data) return {status: r.status, entries: []};
    const who = {};
    for (const p of (r.data.participants || [])) who[p.id] = p.display_name;
    const entries = [];
    const walk = (list, depth) => { for (const e of (list || [])) {
      if (!e.deleted) entries.push({depth, author: who[e.user_id] || e.user_name || null, created_at: e.created_at, message_md: md(e.message, `${ORIGIN}/courses/${cid}/discussion_topics/${tid}`)});
      walk(e.replies, depth + 1); } };
    walk(r.data.view, 0);
    return {status: 200, entries};
  };

  // every module item body, in parallel
  const items = modules.flatMap(m => (m.items || []).map(it => ({m, it})));
  await pool(items, 6, async ({it}) => {
    const out = {};
    if (it.type === 'Page' && it.page_url) {
      const r = await api(`${B}/pages/${encodeURIComponent(it.page_url)}`);
      if (r.status === 200) Object.assign(out, {title: r.data.title, updated_at: r.data.updated_at, body_md: md(r.data.body, page(it.page_url)),
        locked: !!r.data.locked_for_user, lock_explanation: r.data.lock_explanation || null});
      else Object.assign(out, {status: r.status, locked: true, lock_explanation: (r.data && (r.data.lock_explanation || r.data.message)) || null});
    } else if (it.type === 'Assignment') {
      if (!asgById[it.content_id]) {
        const r = await api(`${B}/assignments/${it.content_id}`);
        if (r.status === 200) assignments.push(asgById[r.data.id] = asgObj(r.data)); else out.status = r.status;
      }
      out.assignment_id = it.content_id;
    } else if (it.type === 'Quiz') {
      const r = await api(`${B}/quizzes/${it.content_id}`);
      if (r.status === 200) { const q = r.data; Object.assign(out, {updated_at: q.updated_at || null, quiz: {question_count: q.question_count, points_possible: q.points_possible, due_at: q.due_at, unlock_at: q.unlock_at, lock_at: q.lock_at, allowed_attempts: q.allowed_attempts, time_limit: q.time_limit, assignment_id: q.assignment_id}, body_md: md(q.description, it.html_url), locked: !!q.locked_for_user, lock_explanation: q.lock_explanation || null}); }
      else out.status = r.status;
    } else if (it.type === 'Discussion') {
      const r = discById[it.content_id] ? {status: 200, data: discById[it.content_id]} : await api(`${B}/discussion_topics/${it.content_id}`);
      if (r.status === 200) { const d = r.data; Object.assign(out, {updated_at: d.updated_at || d.last_reply_at || null, posted_at: d.posted_at, author: d.author && d.author.display_name, body_md: md(d.message, it.html_url), assignment_id: d.assignment_id || null, locked: !!d.locked_for_user, lock_explanation: d.lock_explanation || null});
        (d.attachments || []).forEach(x => allFiles.add(String(x.id))); out.attachments = (d.attachments || []).map(x => String(x.id));
        out.replies = await repliesOf(d.id); }
      else out.status = r.status;
    } else if (it.type === 'File') {
      allFiles.add(String(it.content_id)); out.file_id = String(it.content_id);
    }
    it.x = out;
  });

  const announcements = ok(ann).map(a => {
    (a.attachments || []).forEach(x => allFiles.add(String(x.id)));
    return {id: a.id, title: a.title, posted_at: a.posted_at || a.delayed_post_at || a.created_at, author: a.author && a.author.display_name,
      html_url: a.html_url, message_md: md(a.message, a.html_url), attachments: (a.attachments || []).map(x => String(x.id))};
  });
  const cs = crs.data || {};
  const syllabus_md = md(cs.syllabus_body, `${ORIGIN}/courses/${cid}/assignments/syllabus`);

  // content that no module links to: pages (the home page too), discussions and course files
  const modSlugs = new Set(items.filter(x => x.it.page_url).map(x => x.it.page_url));
  const modDisc = new Set(items.filter(x => x.it.type === 'Discussion').map(x => x.it.content_id));
  const asgDisc = new Set(assignments.map(a => a.discussion_id).filter(Boolean));
  const extra_pages = [];
  const pageList = ok(pagesAll).filter(p => !modSlugs.has(p.url) && p.published !== false);
  if (front.status === 200 && front.data && front.data.url && !modSlugs.has(front.data.url) && !pageList.some(p => p.url === front.data.url)) pageList.unshift(front.data);
  await pool(pageList, 6, async (p) => {
    const r = p.body !== undefined ? {status: 200, data: p} : await api(`${B}/pages/${encodeURIComponent(p.url)}`);
    extra_pages.push(r.status === 200
      ? {page_url: p.url, title: r.data.title, updated_at: r.data.updated_at, front_page: !!r.data.front_page, body_md: md(r.data.body, page(p.url)),
         locked: !!r.data.locked_for_user, lock_explanation: r.data.lock_explanation || null}
      : {page_url: p.url, title: p.title, updated_at: p.updated_at, status: r.status, locked: true});
  });
  const extra_discussions = [];
  await pool(ok(disc).filter(d => !modDisc.has(d.id) && !asgDisc.has(d.id)), 4, async (d) => {
    (d.attachments || []).forEach(x => allFiles.add(String(x.id)));
    extra_discussions.push({id: d.id, title: d.title, html_url: d.html_url, posted_at: d.posted_at, author: d.author && d.author.display_name,
      updated_at: d.updated_at || d.last_reply_at || null, body_md: md(d.message, d.html_url), locked: !!d.locked_for_user,
      lock_explanation: d.lock_explanation || null, attachments: (d.attachments || []).map(x => String(x.id)), replies: await repliesOf(d.id)});
  });
  const extra_files = [];
  for (const f of ok(filesAll)) {
    const id = String(f.id);
    if (!allFiles.has(id)) { allFiles.add(id); extra_files.push(id); }
  }
  const assignment_groups = ok(groupsR).map(g => ({id: g.id, name: g.name, position: g.position, group_weight: g.group_weight, rules: g.rules || {}}));

  // metadata for linked course files
  await pool([...allFiles].filter(fid => !fileMeta[fid]), 6, async (fid) => {
    let r = await api(`${B}/files/${fid}`);
    if (r.status !== 200) r = await api(`/api/v1/files/${fid}`);
    if (r.status === 200) { const f = r.data; fileMeta[fid] = {id: String(f.id), display_name: f.display_name, filename: f.filename, size: f.size, content_type: f['content-type'], updated_at: f.updated_at, url: f.url, locked: !!f.locked_for_user}; }
    else fileMeta[fid] = {id: fid, status: r.status};
  });

  const std = scheme.data && scheme.data.course && scheme.data.course.gradingStandard;
  const bundle = {
    easel: CFG.version, format: 4, unit: U.unit, origin: ORIGIN, scraped_at: new Date().toISOString(),
    course: {id: cid, name: course.name, course_code: course.course_code, term: cs.term ? cs.term.name : null, start_at: cs.start_at, end_at: cs.end_at,
             time_zone: cs.time_zone || null, teachers: (cs.teachers || []).map(t => t.display_name), syllabus_public: cs.public_syllabus,
             hide_final_grades: !!cs.hide_final_grades, apply_group_weights: !!cs.apply_assignment_group_weights,
             grading_scheme: std && Array.isArray(std.data) ? {title: std.title, data: std.data.map(d => [d.letterGrade, d.baseValue])} : null,
             tabs: ok(tabs).filter(t => t.hidden !== true).map(t => ({label: t.label, type: t.type, html_url: t.full_url || (t.html_url ? ORIGIN + t.html_url : null)}))},
    staff, groups, inbox,
    modules: modules.map(m => ({id: m.id, name: m.name, position: m.position, unlock_at: m.unlock_at, state: m.state, items_count: m.items_count,
      items: (m.items || []).map(it => ({id: it.id, type: it.type, title: it.title, indent: it.indent, content_id: it.content_id, page_url: it.page_url,
        html_url: it.html_url, external_url: it.external_url, published: it.published, ...it.x}))})),
    assignments, announcements, syllabus_md,
    assignment_groups, group_weights: !!cs.apply_assignment_group_weights, extra_pages, extra_discussions, extra_files,
    files: Object.fromEntries(Object.entries(fileMeta).map(([k, v]) => { const {url, ...rest} = v; return [k, rest]; })),
    feedback_candidates: feedbackCandidates,
    api_status: {modules: mods.status, assignments: asg.status, announcements: ann.status, course: crs.status, assignment_groups: groupsR.status,
                 submissions: subs.status, pages: pagesAll.status, files: filesAll.status, discussions: disc.status, staff: staffR.status,
                 inbox: inboxA.status, grading_scheme: scheme.status},
    fetch_ms: Math.round(performance.now() - t0),
    coverage,
  };
  const r = await post(`/bundle?unit=${U.unit}&run=${CFG.run}`, JSON.stringify(bundle), 'application/json');
  const plan = await r.json();
  if (plan.error) { await log(U.unit + ': helper refused the data: ' + plan.error); return U.unit + ': ' + plan.error; }

  // download only what the helper asked for, straight to the helper (no Downloads folder)
  let got = 0; const failed = [];
  await pool(plan.need || [], 3, async (fid) => {
    const meta = fileMeta[fid];
    try {
      // Canvas download links carry a verifier, and the file host refuses cookies from another site. Try without cookies first.
      let fr = await fetch(meta.url, {credentials: 'omit'}).catch(() => null);
      if (!fr || !fr.ok) fr = await fetch(meta.url, {credentials: 'include'}).catch(() => null);
      if (!fr || !fr.ok) { failed.push(fid); await post(`/file_failed?unit=${U.unit}&id=${fid}&status=${fr ? fr.status : 0}&run=${CFG.run}`, ''); return; }
      const blob = await fr.blob();
      const pr = await post(`/file?unit=${U.unit}&id=${fid}&run=${CFG.run}`, blob, 'application/octet-stream');
      if (pr.ok) got++; else failed.push(fid);
    } catch (e) { failed.push(fid); await post(`/file_failed?unit=${U.unit}&id=${fid}&status=0&run=${CFG.run}`, String(e)).catch(() => {}); }
  });
  for (const key of (plan.feedback || [])) if (previewUrl[key]) viewerDocs.push({key, unit: U.unit, url: previewUrl[key]});
  await post(`/done?unit=${U.unit}&run=${CFG.run}`, JSON.stringify({got, failed: failed.length}), 'application/json');
  return `${U.unit}: ${items.length} items, ${got}/${(plan.need || []).length} files`;
}

window.__EASEL_RUN = (async () => {
  const me = await api('/api/v1/users/self');
  if (me.status !== 200) {
    await post('/login?run=' + CFG.run, String(me.status)).catch(() => {});
    return 'not signed in to Canvas';
  }
  const out = await Promise.all(CFG.units.map(async (U) => {
    try { return await scrapeUnit(U); }
    catch (e) { await post(`/error?unit=${U.unit}&run=${CFG.run}`, String(e && e.stack || e)).catch(() => {}); return U.unit + ': error ' + e; }
  }));
  await post('/all_done?run=' + CFG.run, JSON.stringify({lines: out, viewer: viewerDocs.map(d => ({key: d.key, unit: d.unit}))}), 'application/json').catch(() => {});
  // Annotated feedback lives in Canvas's document viewer, on another host. Go there with the list in the address fragment.
  if (viewerDocs.length) setTimeout(() => { location.href = viewerDocs[0].url + '#easel=' + encodeURIComponent(JSON.stringify({run: CFG.run, docs: viewerDocs.map(d => ({key: d.key, url: d.url}))})); }, 300);
  return out.join('\n');
})();
return 'easel started: ' + CFG.units.map(u => u.unit).join(', ');
})();
