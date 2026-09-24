/* Part of veusz-js-engine. Licensed under the Apache License 2.0.
 * Trusted loopback-only coordinator; worker execution never blocks polling. */
(() => {
  'use strict';
  const token = new URL(document.currentScript.src).searchParams.get('token');
  // Remove credentials from the address bar/history entry immediately.
  history.replaceState(null, '', '/');
  const client = crypto.randomUUID();
  const headers = {'X-Session-Token': token, 'X-Client-Id': client};
  const workers = new Map();
  const controller = new AbortController();
  let stopped = false;
  function stop() {
    if (stopped) return;
    stopped = true;
    controller.abort();
    for (const entry of workers.values()) {
      entry.port.close();
      entry.worker.terminate();
    }
    workers.clear();
  }
  async function request(path, body) {
    const response = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? headers : {...headers, 'Content-Type': 'application/json'},
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store', credentials: 'omit', redirect: 'error', signal: controller.signal
    });
    if (!response.ok) throw new Error('Bridge HTTP ' + response.status);
    return response.json();
  }
  function reply(task, value, error) {
    const message = {id: task.id, runtime: task.runtime};
    if (error !== undefined) message.error = String(error);
    else message.value = value;
    request('/result', message).catch(stop);
  }
  function dispatch(task) {
    try {
      if (task.op === 'create') {
        if (workers.has(task.runtime)) throw new Error('Duplicate runtime');
        const worker = new Worker('/worker.js?token=' + encodeURIComponent(token), {name: task.label});
        const channel = new MessageChannel();
        const entry = {worker, port: channel.port1, pending: new Map([[task.id, task]])};
        workers.set(task.runtime, entry);
        channel.port1.onmessage = event => {
          const message = event.data;
          const pending = entry.pending.get(message.id);
          if (!pending || message.runtime !== pending.runtime) { stop(); return; }
          entry.pending.delete(message.id);
          reply(pending, message.value, message.error);
        };
        worker.onerror = event => {
          event.preventDefault();
          for (const pending of entry.pending.values()) {
            reply(pending, undefined, event.message || 'Worker failed');
          }
          // A lost context must never silently be recreated.
          entry.pending.clear();
          entry.port.close();
          worker.terminate();
          workers.delete(task.runtime);
        };
        worker.onmessageerror = stop;
        channel.port1.onmessageerror = stop;
        worker.postMessage(task, [channel.port2]);
      } else {
        const entry = workers.get(task.runtime);
        if (!entry) throw new Error('Unknown or failed runtime');
        if (task.op === 'close') {
          entry.port.close();
          entry.worker.terminate();
          workers.delete(task.runtime);
          reply(task, '');
        } else {
          entry.pending.set(task.id, task);
          entry.port.postMessage(task);
        }
      }
    } catch (error) {
      reply(task, undefined, String(error) + (error && error.stack ? '\n' + error.stack : ''));
    }
  }
  addEventListener('pagehide', stop);
  (async () => {
    try {
      await request('/hello', {});
      while (!stopped) {
        const task = await request('/task');
        if (task && !stopped) dispatch(task);
      }
    } catch (_) {
      // Includes 410, disconnect, rejected credentials: never reconnect.
      stop();
    }
  })();
})();
