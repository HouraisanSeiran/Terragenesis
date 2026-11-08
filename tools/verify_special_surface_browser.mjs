// Real-browser acceptance for the special-terrain 3D workspace, without playwright.
//
// The repository's other frontend verifiers drive playwright, which is not installed here; this
// one speaks the Chrome DevTools Protocol over a plain WebSocket instead (node's built-in
// WebSocket, node >= 22).  It starts the read-only bridge on a scratch port, opens a headless
// Edge/Chrome, loads ?workspace=special, and checks the things a screenshot cannot: that the
// three-dimensional group actually rasterises non-blank pixels, that the flat map paints, that
// switching form re-reads a different pinned bundle, and that the export record carries the four
// capability flags as false.
//
// Usage:
//   node tools/verify_special_surface_browser.mjs [--output report.json] [--edge <exe>]
//                                                   [--python <exe>] [--keep]
// Exit code 0 means every assertion held; 1 means at least one did not (the report says which).

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const flag = name => args.includes(name);
const OUTPUT = option('--output', '');
const KEEP = flag('--keep');
const PYTHON = option('--python', path.join(ROOT, 'runtime/venv/Scripts/python.exe'));
const EDGE = option('--edge', [
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
].find(candidate => fs.existsSync(candidate)) || '');

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function freePort() {
  return new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.unref();
    probe.on('error', reject);
    probe.listen(0, '127.0.0.1', () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });
}

async function waitForPort(port, label, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const open = await new Promise(resolve => {
      const socket = net.connect(port, '127.0.0.1');
      socket.setTimeout(500);
      socket.on('connect', () => { socket.destroy(); resolve(true); });
      socket.on('error', () => resolve(false));
      socket.on('timeout', () => { socket.destroy(); resolve(false); });
    });
    if (open) return;
    await sleep(250);
  }
  throw Error(`${label} never listened on port ${port}`);
}

function connect(url) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    let next = 1;
    const pending = new Map();
    socket.onopen = () => resolve({
      send(method, params = {}) {
        const id = next++;
        return new Promise((done, fail) => {
          pending.set(id, { done, fail });
          socket.send(JSON.stringify({ id, method, params }));
        });
      },
      close: () => socket.close(),
    });
    socket.onerror = reject;
    socket.onmessage = event => {
      const message = JSON.parse(event.data);
      if (!pending.has(message.id)) return;
      const { done, fail } = pending.get(message.id);
      pending.delete(message.id);
      message.error ? fail(Error(JSON.stringify(message.error))) : done(message.result);
    };
  });
}

// The whole browser-side interrogation, kept as one expression so it runs in page context.
const PROBE = `(async () => {
  const out = {errors: []};
  const canvas = document.getElementById('specialSurface');
  const map = document.getElementById('specialMap');
  const unblank = target => {
    try {
      const gl = target.getContext('webgl2') || target.getContext('webgl');
      if (!gl) return {supported: false};
      const pixels = new Uint8Array(gl.drawingBufferWidth * gl.drawingBufferHeight * 4);
      gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      let lit = 0;
      for (let i = 0; i < pixels.length; i += 4) if (pixels[i] || pixels[i + 1] || pixels[i + 2]) lit++;
      return {supported: true, lit};
    } catch (error) { return {supported: false, error: String(error.message)}; }
  };
  out.webgl = unblank(document.createElement('canvas'));
  document.getElementById('view3d').click();
  await new Promise(r => setTimeout(r, 2000));
  out.three = {width: canvas.width, height: canvas.height, hidden: canvas.classList.contains('hidden'), ...unblank(canvas)};
  document.getElementById('view2d').click();
  await new Promise(r => setTimeout(r, 900));
  out.flat = {hidden: map.classList.contains('hidden'), width: map.width, height: map.height};
  try {
    const data = map.getContext('2d').getImageData(0, 0, Math.min(map.width, 500), Math.min(map.height, 500)).data;
    let lit = 0;
    for (let i = 0; i < data.length; i += 4) if (data[i] > 40 && data[i + 1] > 40) lit++;
    out.flat.lit = lit;
  } catch (error) { out.flat.error = String(error.message); }
  out.firstForm = window.specialSurface.reviewRecord();
  out.layers = document.getElementById('layers').textContent;
  const field = document.getElementById('specialField');
  field.value = 'elevation';
  field.dispatchEvent(new Event('change'));
  await new Promise(r => setTimeout(r, 700));
  const form = document.getElementById('specialForm');
  form.value = 'sandstone_pillar_field';
  form.dispatchEvent(new Event('change'));
  await new Promise(r => setTimeout(r, 3000));
  out.secondForm = window.specialSurface.reviewRecord();
  out.exportEnabled = !document.getElementById('exportReview').disabled;
  out.threeAgain = (() => { document.getElementById('view3d').click(); return true; })();
  await new Promise(r => setTimeout(r, 1500));
  out.threeSelected = unblank(document.getElementById('specialSurface'));
  return out;
})()`;

(async () => {
  const checks = [];
  const record = (name, ok, detail) => checks.push({ name, ok, detail });
  let bridge = null;
  let browser = null;
  try {
    record('python is present', fs.existsSync(PYTHON), PYTHON);
    record('headless browser is present', Boolean(EDGE), EDGE || 'no Edge/Chrome found');
    if (!fs.existsSync(PYTHON) || !EDGE) throw Error('missing prerequisite');

    const servicePort = await freePort();
    const debugPort = await freePort();
    const profile = path.join(ROOT, '.scratch', `special-surface-browser-${Date.now()}`);

    bridge = spawn(PYTHON, ['web-preview/serve.py', '--port', String(servicePort)],
      { cwd: ROOT, stdio: 'ignore', detached: false });
    await waitForPort(servicePort, 'bridge');

    browser = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
      '--window-size=1600,1000', 'about:blank'], { stdio: 'ignore', detached: false });
    await waitForPort(debugPort, 'browser');

    const url = `http://127.0.0.1:${servicePort}/?workspace=special`;
    const target = await (await fetch(
      `http://127.0.0.1:${debugPort}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' })).json();
    const client = await connect(target.webSocketDebuggerUrl);
    await client.send('Runtime.enable');

    let state = null;
    for (let attempt = 0; attempt < 45; attempt++) {
      await sleep(1000);
      const result = await client.send('Runtime.evaluate', {
        expression: `(() => window.specialSurface && window.surfaceReview ? {
          ready: true, loading: window.specialSurface.isLoading(),
          title: document.getElementById('viewTitle').textContent,
          subtitle: document.getElementById('viewSubtitle').textContent,
          workspace: document.body.dataset.workspace,
          forms: document.getElementById('specialForm').options.length,
          record: window.specialSurface.reviewRecord() } : {ready: false})()`,
        awaitPromise: true, returnByValue: true,
      });
      state = result.result.value;
      if (state?.ready && !state.loading && state.record) break;
    }
    const probe = (await client.send('Runtime.evaluate', {
      expression: PROBE, awaitPromise: true, returnByValue: true,
    })).result.value;
    client.close();

    record('workspace switches to special', state?.workspace === 'special', state?.workspace);
    record('panel titles name the synthetic chart',
      /特殊地形/.test(state?.title || '') && /合成图幅/.test(state?.title || ''),
      `${state?.title} / ${state?.subtitle}`);
    record('catalog offers four forms', state?.forms === 4, String(state?.forms));
    record('page has no script errors', (probe?.errors || []).length === 0, probe?.errors?.join('; '));
    record('webgl is available', probe?.webgl?.supported === true, JSON.stringify(probe?.webgl));
    record('three-dimensional group rasterises',
      probe?.three?.hidden === false && probe?.three?.lit > 10000, JSON.stringify(probe?.three));
    record('flat map paints', probe?.flat?.hidden === false && probe?.flat?.lit > 1000, JSON.stringify(probe?.flat));
    // The protected layer only exists for a bundle that protects cells, so the assertion follows
    // the descriptor rather than demanding the label unconditionally.
    const layerLabels = ['保存地表', '解析参考面', '侵蚀变化'];
    const protectedLayer = (probe?.firstForm?.protected_cells ?? 0) > 0;
    record('layer list carries the new layers',
      layerLabels.every(label => (probe?.layers || '').includes(label)) &&
      (probe?.layers || '').includes('保护区') === protectedLayer,
      `${probe?.layers} (protected_cells=${probe?.firstForm?.protected_cells})`);
    record('first form reads a pinned bundle',
      probe?.firstForm?.source?.manifest_sha256?.startsWith('d1f12249'), probe?.firstForm?.caseId);
    record('switching form reads a different bundle',
      probe?.secondForm?.caseId === 'sandstone_pillar_field' &&
      probe?.secondForm?.source?.identity?.startsWith('bc410d6b'), probe?.secondForm?.caseId);
    record('three dimensions survive a form switch', probe?.threeSelected?.lit > 10000,
      JSON.stringify(probe?.threeSelected));
    record('export is enabled and refuses to claim capability',
      probe?.exportEnabled === true && ['hydraulic_ready', 'natural_outlet_verified', 'publishable',
        'self_intersection_verified'].every(name => probe?.secondForm?.[name] === false) &&
      probe?.secondForm?.status?.startsWith('bounded_relaxation'),
      `${probe?.secondForm?.status} export=${probe?.exportEnabled}`);
  } catch (error) {
    record('verifier ran to completion', false, String(error.message || error));
  } finally {
    if (!KEEP) {
      try { browser?.kill(); } catch { /* already gone */ }
      try { bridge?.kill(); } catch { /* already gone */ }
      await sleep(500);
    }
  }

  const failed = checks.filter(item => !item.ok);
  const report = { schema: 'special-surface-browser-verification-v1', workspace: 'special',
    root: ROOT, passed: checks.length - failed.length, failed: failed.length, checks };
  if (OUTPUT) fs.writeFileSync(OUTPUT, JSON.stringify(report, null, 2));
  for (const item of checks) console.log(`${item.ok ? 'ok  ' : 'FAIL'} ${item.name}: ${item.detail ?? ''}`);
  console.log(`\n${report.passed}/${checks.length} checks passed`);
  process.exit(failed.length ? 1 : 0);
})();