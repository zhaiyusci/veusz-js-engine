'use strict';
// A real browser Worker hosts the existing scripts without browser DOM globals.
const token = new URL(self.location.href).searchParams.get('token');
const client = crypto.randomUUID();
const headers = {'X-Session-Token': token, 'X-Client-Id': client};
const assetURL = file => '/assets/' + file + '?token=' + encodeURIComponent(token);
async function jsonFetch(path, options = {}) {
    const response = await fetch(path, {signal: AbortSignal.timeout(20000), ...options, headers: {...headers, ...(options.headers || {})}});
    if (!response.ok) throw new Error(path + ': HTTP ' + response.status);
    return response.json();
}
async function post(path, body) {
    return jsonFetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
}
async function main() {
    globalThis.veuszFileHeads = await jsonFetch('/heads');
    const allowed = new Set(globalThis.veuszFileHeads.map(file => file.file));
    importScripts(assetURL('jsapi.js'), assetURL('feature.js'));
    await post('/ready', {client, userAgent: navigator.userAgent});
    self.postMessage({status: 'Connected. Existing MathJax feature loaded; waiting for Python requests.'});
    while (true) {
        const task = await jsonFetch('/task');
        if (!task) continue;
        const started = performance.now();
        let reply;
        try {
            let value;
            if (task.op === 'call' && ['veuszDescribe', 'veuszRender'].includes(task.name)) {
                value = globalThis[task.name](task.payload);
            } else if (task.op === 'load' && allowed.has(task.file)) {
                importScripts(assetURL(task.file));
                value = true;
            } else {
                throw new Error('Unsupported operation or resource');
            }
            reply = {id: task.id, value, elapsed_ms: performance.now() - started};
            if (task.name === 'veuszRender' && typeof value === 'string') {
                const rendered = JSON.parse(value);
                if (rendered.svg) self.postMessage({svg: rendered.svg});
            }
        } catch (error) {
            reply = {id: task.id, error: String(error.stack || error), elapsed_ms: performance.now() - started};
        }
        await post('/reply', reply);
        self.postMessage({status: 'Completed ' + task.op + ' ' + (task.name || task.file) + ' in ' + reply.elapsed_ms.toFixed(2) + ' ms (JS only).'});
    }
}
main().catch(async error => {
    const message = String(error.stack || error);
    self.postMessage({error: message});
    try { await post('/fatal', {error: message}); } catch (_) { /* Server may have exited. */ }
});
