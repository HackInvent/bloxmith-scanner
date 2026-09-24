/** Canvas action using the existing public runtime client; no hidden data channel. */
const pending = new Map();

export function mount(root, api) {
  const abort = new AbortController();
  const { signal } = abort;
  const button = root.querySelector('[data-scan-start]');
  const status = root.querySelector('[data-scan-status]');
  if (!button || !status) return () => abort.abort();
  const t = (key, fallback) => api.t?.('block.scanner.' + key, {}, fallback) || fallback;
  const readOnly = () => typeof api.isReadOnly === 'function' ? api.isReadOnly() : Boolean(api.isReadOnly);
  // The currently exposed scope getter includes the canonical composite runtime node ID.
  // Only its run/node identity is used here; no audio APIs or transport are involved.
  const scope = () => api.actions?.getRuntimeAudioStreamContext?.(api.getNode?.()) || {};
  let checking = false;
  function display(key, fallback) {
    status.removeAttribute('data-i18n');
    status.textContent = t(key, fallback);
  }
  async function refresh() {
    if (signal.aborted) return;
    for (const [key, value] of pending) {
      if (Date.now() - value.started > value.timeout) pending.delete(key);
    }
    const current = scope();
    const key = current.runId + ':' + current.nodeId;
    const request = pending.get(key);
    const selected = Boolean(api.getNode?.()?.config?.device);
    button.disabled = readOnly() || !current.available || !selected || Boolean(request);
    if (!selected) display('choose_device', 'Select a scanner in settings.');
    else if (!current.available) display('start_run', 'Start Run, then scan.');
    else if (!request) display('ready', 'Ready · PDF output');
    else {
      display('scanning', 'Scanning…');
      if (checking) return;
      checking = true;
      try {
        const response = await window.CWRuntimeApi.getRun(current.runId);
        const run = response.run || response;
        const output = JSON.stringify(run.output_values?.[current.nodeId + ':1'] || '');
        const failed = ['failed', 'cancelled'].includes(run.node_statuses?.[current.nodeId]);
        if (output !== request.before || failed || ['stopped', 'failed', 'completed'].includes(run.status)) {
          pending.delete(key);
          if (failed && !signal.aborted) display('scan_error', 'Scan failed. See the block error log.');
        } else if (Date.now() - request.started > request.timeout) {
          pending.delete(key);
          if (!signal.aborted) display('scan_timeout', 'Check the block log before starting another scan.');
        }
      } catch (_) {
        // A temporary status polling failure must not enqueue another hardware action.
      } finally { checking = false; }
    }
  }
  for (const event of ['pointerdown', 'mousedown', 'dblclick']) {
    button.addEventListener(event, e => e.stopPropagation(), { signal });
  }
  button.addEventListener('click', async event => {
    event.preventDefault(); event.stopPropagation();
    const current = scope();
    const key = current.runId + ':' + current.nodeId;
    if (readOnly() || !current.available || pending.has(key) || !api.getNode?.()?.config?.device) return;
    const request = { before: '', started: Date.now(), timeout: (Number(api.getNode?.()?.config?.timeout_sec || 120) + 20) * 1000 };
    pending.set(key, request); button.disabled = true;
    display('scanning', 'Scanning…');
    try {
      const response = await window.CWRuntimeApi.getRun(current.runId);
      const run = response.run || response;
      request.before = JSON.stringify(run.output_values?.[current.nodeId + ':1'] || '');
      if (signal.aborted) { pending.delete(key); return; }
      const latest = scope();
      if (!latest.available || latest.runId !== current.runId || latest.nodeId !== current.nodeId) {
        pending.delete(key); return;
      }
      await window.CWRuntimeApi.controlActiveRun(current.runId, { action: 'trigger_node', node_id: current.nodeId });
    } catch (error) {
      // Keep a short uncertainty window: a lost HTTP response is not proof that scan did not start.
      request.timeout = Math.min(request.timeout, 10000);
      if (!signal.aborted) display('scan_error', 'Scan failed. See the block error log.');
    }
  }, { signal });
  void refresh();
  const timer = setInterval(() => { void refresh(); }, 1000);
  return () => { abort.abort(); clearInterval(timer); };
}
