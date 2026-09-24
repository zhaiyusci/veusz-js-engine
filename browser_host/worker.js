/* Part of veusz-js-engine. Licensed under the Apache License 2.0.
 * No protocol globals, require, or module are installed in feature contexts. */
(() => {
  'use strict';
  // Capture transport and intrinsics before any feature code can replace globals.
  const root = globalThis;
  const evaluate = (0, eval);
  const stringify = String;
  const apply = Reflect.apply;
  const load = importScripts.bind(root);
  const BlobClass = Blob;
  const makeURL = URL.createObjectURL.bind(URL);
  const revokeURL = URL.revokeObjectURL.bind(URL);
  const listen = addEventListener.bind(root);
  const unlisten = removeEventListener.bind(root);
  const replace = Function.prototype.call.bind(String.prototype.replace);
  // Preserve the platform's offline, pure-computation feature contract. The
  // coordinator owns HTTP; only the captured loader can import host-supplied JS.
  // This is defense in depth/compatibility, not an untrusted-code sandbox.
  for (const name of ['fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource',
                      'WebTransport', 'Worker', 'SharedWorker', 'importScripts']) {
    Object.defineProperty(root, name, {value: undefined, writable: false, configurable: false});
  }
  function source(task) {
    // A sourceURL is diagnostic only, never an HTTP/filesystem resource route.
    return task.source + '\n//# sourceURL=' +
      replace(stringify(task.name || '<javascript>'), /[\r\n\u2028\u2029]/g, ' ') + '\n';
  }
  function initialize(event) {
    unlisten('message', initialize);
    const port = event.ports[0];
    const send = port.postMessage.bind(port);
    const runtime = event.data.runtime;
    port.onmessage = event => {
      const task = event.data;
      const answer = {id: task.id, runtime};
      try {
        if (task.runtime !== runtime) throw new Error('Runtime mismatch');
        let result;
        if (task.op === 'eval') {
          // Indirect eval is global, but its lexical let/const bindings are temporary.
          result = evaluate(source(task));
        } else if (task.op === 'load') {
          const url = makeURL(new BlobClass([source(task)], {type: 'text/javascript'}));
          try {
            // Classic scripts share the Worker's persistent global lexical environment.
            load(url);
          } finally {
            revokeURL(url);
          }
          result = undefined;
        } else if (task.op === 'call') {
          const fn = root[task.fn_name];
          if (typeof fn !== 'function') throw new Error('Not a function: ' + task.fn_name);
          result = apply(fn, root, [task.payload]);
        } else {
          throw new Error('Unknown worker operation');
        }
        answer.value = stringify(result);
      } catch (error) {
        // Firefox's Error.stack omits the message; include both explicitly.
        try { answer.error = stringify(error) + (error && error.stack ? '\n' + stringify(error.stack) : ''); }
        catch (_) { answer.error = 'JavaScript exception (unprintable)'; }
      }
      send(answer);
    };
    port.start();
    send({id: event.data.id, runtime, value: ''});
  }
  listen('message', initialize);
})();
