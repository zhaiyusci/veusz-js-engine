'use strict';
const status = document.querySelector('#status');
const token = new URLSearchParams(location.hash.slice(1)).get('token');
history.replaceState(null, '', location.pathname);
if (!token) {
    status.textContent = 'Missing session token. Open the complete URL printed by server.py.';
} else {
    const worker = new Worker('/worker.js?token=' + encodeURIComponent(token));
    let previousURL;
    worker.onmessage = ({data}) => {
        status.textContent = data.error || data.status || status.textContent;
        if (data.svg) {
            if (previousURL) URL.revokeObjectURL(previousURL);
            previousURL = URL.createObjectURL(new Blob([data.svg], {type: 'image/svg+xml'}));
            document.querySelector('#preview').src = previousURL;
        }
    };
    worker.onerror = event => {
        status.textContent = 'Worker failed: ' + event.message;
        fetch('/fatal', {method: 'POST', headers: {'X-Session-Token': token, 'Content-Type': 'application/json'}, body: JSON.stringify({error: status.textContent})}).catch(() => {});
    };
}
