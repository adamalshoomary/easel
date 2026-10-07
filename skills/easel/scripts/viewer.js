// easel viewer step. Run it in the tab that shows Canvas's document viewer.
// It reads the document list from the address after "#easel=", collects each marker's
// annotations and the marked-up PDF, and saves one file to the browser's download folder.
(() => {
  if (!/canvadocs/.test(location.host) || !location.hash.startsWith('#easel=')) return 'NOT_READY ' + location.host;
  if (window.__easelViewer) return 'RUNNING ' + JSON.stringify(window.__easelViewer);
  const cfg = JSON.parse(decodeURIComponent(location.hash.slice(7)));
  const S = window.__easelViewer = {total: cfg.docs.length, done: 0, pdfs: 0, problems: 0, state: 'running'};
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  // A frame shows Canvas first, then the viewer. Reading it throws until it reaches the viewer.
  const viewerIn = async (w, ms) => {
    for (const end = Date.now() + ms; Date.now() < end; await sleep(300)) {
      try { if (w.DocViewer && w.DocViewer.accessToken && w.DocViewer.documentId) return w.DocViewer; } catch (e) { /* not there yet */ }
    }
    return null;
  };
  const b64 = (blob) => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1]); r.onerror = no; r.readAsDataURL(blob); });
  async function collect(D) {
    const h = {Authorization: 'Bearer ' + D.accessToken};
    const ar = await fetch(`/1/sessions/${D.accessToken}/annotations`, {headers: h});
    if (!ar.ok) return {status: 'annotations HTTP ' + ar.status};
    const list = ((await ar.json()) || {}).data || [];
    const out = {annotations: list.map(a => ({id: a.id, type: a.type, page: a.page, author: a.user_name || null, role: a.user_role || null,
      created_at: a.created_at || null, contents: a.contents || '', inreplyto: a.inreplyto || null}))};
    if (!list.length) return Object.assign(out, {status: 'no annotations'});
    const base = `/v2/documents/${D.documentId}/merged-documents`;
    const m = await fetch(base, {method: 'POST', headers: h});
    if (!m.ok) return Object.assign(out, {status: 'merge HTTP ' + m.status});
    const id = ((await m.json()) || {}).mergedDocumentId;
    let ready = false;
    for (let i = 0; i < 90 && !ready; i++) {
      const r = await fetch(`${base}/${id}/is_ready`, {headers: h});
      ready = r.ok && ((await r.json()) || {}).ready === true;
      if (!ready) await sleep(1000);
    }
    if (!ready) return Object.assign(out, {status: 'merge timed out'});
    const l = await fetch(`${base}/${id}/single-use-download-link`, {method: 'POST', headers: h});
    const url = l.ok ? ((await l.json()) || {}).singleUseDownloadUrl : null;
    if (!url) return Object.assign(out, {status: 'link HTTP ' + l.status});
    const f = await fetch(url);
    if (!f.ok) return Object.assign(out, {status: 'pdf HTTP ' + f.status});
    return Object.assign(out, {status: 'ok', pdf: await b64(await f.blob())});
  }
  (async () => {
    const results = [];
    for (let i = 0; i < cfg.docs.length; i++) {
      const doc = cfg.docs[i];
      let r;
      try {
        if (i === 0) {
          const D = await viewerIn(window, 30000);
          r = D ? await collect(D) : {status: 'viewer did not load'};
        } else {
          const fr = document.createElement('iframe');
          fr.style.cssText = 'position:fixed;left:-10000px;top:0;width:900px;height:700px';
          fr.src = doc.url;
          document.body.appendChild(fr);
          const D = await viewerIn(fr.contentWindow, 30000);
          r = D ? await collect(D) : {status: 'viewer did not load in a frame (third-party cookies may be blocked)'};
          fr.remove();
        }
      } catch (e) { r = {status: 'error ' + String(e).slice(0, 160)}; }
      r.key = doc.key;
      results.push(r);
      S.done++;
      if (r.pdf) S.pdfs++;
      if (r.status !== 'ok' && r.status !== 'no annotations') S.problems++;
    }
    const blob = new Blob([JSON.stringify({easel: 'feedback', run: cfg.run, results})], {type: 'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `easel-feedback-${cfg.run}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    S.state = 'saved';
  })();
  return 'STARTED ' + cfg.docs.length + ' documents';
})()
