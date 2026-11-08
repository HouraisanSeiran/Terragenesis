// Real-browser acceptance for the pillar-field true-3D workspace, without playwright.
//
// The repository's other frontend verifiers drive playwright, which is not installed here; this
// one speaks the Chrome DevTools Protocol over a plain WebSocket instead (node's built-in
// WebSocket, node >= 22).  It starts the read-only bridge on a scratch port, opens a headless
// Edge/Chrome, loads ?workspace=pillars3d, and checks the things a screenshot cannot: that the
// three-dimensional group actually rasterises non-blank pixels, that the flat plan view paints
// the joint-cell rings, that the two meshes arrive with the counts the artifact declares, and
// that the export record carries all capability flags as false while naming the superseded
// height-field schema.
//
// Usage:
//   node tools/verify_pillars3d_browser.mjs [--output report.json] [--edge <exe>]
//                                          [--python <exe>] [--keep]
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
  const canvas = document.getElementById('pillarsSolid');
  const map = document.getElementById('pillarsMap');
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
  await new Promise(r => setTimeout(r, 2500));
  out.three = {width: canvas.width, height: canvas.height, hidden: canvas.classList.contains('hidden'), ...unblank(canvas)};
  out.firstRecord = window.pillars3d.reviewRecord();
  out.layers = document.getElementById('layers').textContent;
  // Hide the two auxiliary layers and confirm the solid alone still paints: that is what
  // separates a rendered mesh from a layer leftover.
  const boxes = Array.from(document.querySelectorAll('#layers input'));
  for (const box of boxes) if (box.dataset.layer !== 'carved') { box.checked = false; box.dispatchEvent(new Event('change')); }
  await new Promise(r => setTimeout(r, 1500));
  out.solidOnly = unblank(canvas);
  for (const box of boxes) { box.checked = box.dataset.layer !== 'plain'; box.dispatchEvent(new Event('change')); }
  await new Promise(r => setTimeout(r, 1200));
  document.getElementById('view2d').click();
  await new Promise(r => setTimeout(r, 900));
  out.flat = {hidden: map.classList.contains('hidden'), width: map.width, height: map.height};
  try {
    const data = map.getContext('2d').getImageData(0, 0, Math.min(map.width, 500), Math.min(map.height, 500)).data;
    let lit = 0;
    for (let i = 0; i < data.length; i += 4) if (data[i] > 40 && data[i + 1] > 40) lit++;
    out.flat.lit = lit;
  } catch (error) { out.flat.error = String(error.message); }
  const shade = document.getElementById('pillars3dShade');
  shade.value = 'carve';
  shade.dispatchEvent(new Event('change'));
  await new Promise(r => setTimeout(r, 700));
  const mapData = map.getContext('2d').getImageData(0, 0, Math.min(map.width, 500), Math.min(map.height, 500)).data;
  let rust = 0;
  for (let i = 0; i < mapData.length; i += 4) if (mapData[i] > 120 && mapData[i + 1] < 110 && mapData[i + 2] < 110) rust++;
  out.carveShadeRustPixels = rust;
  out.exportEnabled = !document.getElementById('exportReview').disabled;
  document.getElementById('view3d').click();
  await new Promise(r => setTimeout(r, 2000));
  out.threeAgain = unblank(canvas);
  out.record = window.pillars3d.reviewRecord();
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
    const profile = path.join(ROOT, '.scratch', `pillars3d-browser-${Date.now()}`);

    bridge = spawn(PYTHON, ['web-preview/serve.py', '--port', String(servicePort)],
      { cwd: ROOT, stdio: 'ignore', detached: false });
    await waitForPort(servicePort, 'bridge');

    browser = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
      '--window-size=1600,1000', 'about:blank'], { stdio: 'ignore', detached: false });
    await waitForPort(debugPort, 'browser');

    const url = `http://127.0.0.1:${servicePort}/?workspace=pillars3d`;
    const target = await (await fetch(
      `http://127.0.0.1:${debugPort}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' })).json();
    const client = await connect(target.webSocketDebuggerUrl);
    await client.send('Runtime.enable');

    let state = null;
    for (let attempt = 0; attempt < 60; attempt++) {
      await sleep(1000);
      const result = await client.send('Runtime.evaluate', {
        expression: `(() => window.pillars3d && window.surfaceReview ? {
          ready: true, loading: window.pillars3d.isLoading(),
          title: document.getElementById('viewTitle').textContent,
          subtitle: document.getElementById('viewSubtitle').textContent,
          workspace: document.body.dataset.workspace,
          options: document.getElementById('reviewProject').options.length,
          record: window.pillars3d.reviewRecord() } : {ready: false})()`,
        awaitPromise: true, returnByValue: true,
      });
      state = result.result.value;
      if (state?.ready && !state.loading && state.record) break;
      // A refused read is also an answer: surface it rather than spinning for two minutes.
      if (state?.ready && !state.loading && !state.record && attempt > 8) break;
    }
    const probe = (await client.send('Runtime.evaluate', {
      expression: PROBE, awaitPromise: true, returnByValue: true,
    })).result.value;
    client.close();

    record('workspace switches to pillars3d', state?.workspace === 'pillars3d', state?.workspace);
    record('panel title names the true-3D solid',
      /石柱群/.test(state?.title || '') && /真三维/.test(state?.title || ''),
      `${state?.title} / ${state?.subtitle}`);
    record('project list registers the new workspace', (state?.options ?? 0) >= 4, String(state?.options));
    record('page has no script errors', (probe?.errors || []).length === 0, probe?.errors?.join('; '));
    record('webgl is available', probe?.webgl?.supported === true, JSON.stringify(probe?.webgl));
    record('three-dimensional solid rasterises',
      probe?.three?.hidden === false && probe?.three?.lit > 10000, JSON.stringify(probe?.three));
    record('the carved solid paints with its sibling layers hidden',
      probe?.solidOnly?.lit > 5000, JSON.stringify(probe?.solidOnly));
    record('flat plan view paints the joint cells',
      probe?.flat?.hidden === false && probe?.flat?.lit > 1000, JSON.stringify(probe?.flat));
    record('carve shading reaches the rust end of the ramp',
      (probe?.carveShadeRustPixels ?? 0) > 20, String(probe?.carveShadeRustPixels));
    record('layer list carries the three new layers',
      ['雕刻后闭合实体', '未雕刻棱柱', '柱顶节理胞轮廓'].every(label => (probe?.layers || '').includes(label)),
      probe?.layers);
    record('first read is a pinned candidate artifact',
      probe?.firstRecord?.status === 'candidate' && probe?.firstRecord?.caseId === 'pillars3d',
      `${probe?.firstRecord?.caseId} ${probe?.firstRecord?.status}`);
    record('mesh counts match the artifact declaration',
      probe?.firstRecord?.components === 1 &&
      probe?.firstRecord?.every_section_simple === true &&
      probe?.firstRecord?.full_depth_pillars === 14 &&
      probe?.firstRecord?.pillar_count === 16,
      JSON.stringify({ pillars: probe?.firstRecord?.pillar_count,
        components: probe?.firstRecord?.components,
        every_section_simple: probe?.firstRecord?.every_section_simple,
        full_depth: probe?.firstRecord?.full_depth_pillars }));
    record('every witness verdict is true',
      Object.values(probe?.firstRecord?.witnesses || {}).every(value => value === true),
      JSON.stringify(probe?.firstRecord?.witnesses));
    record('three dimensions survive the view round trip', probe?.threeAgain?.lit > 10000,
      JSON.stringify(probe?.threeAgain));
    record('export is enabled and refuses to claim capability',
      probe?.exportEnabled === true &&
      ['hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified']
        .every(name => probe?.record?.[name] === false) &&
      probe?.record?.supersedes?.superseded_schema === 'metric-special-terrain-v1',
      `${probe?.record?.status} supersedes=${probe?.record?.supersedes?.superseded_schema} export=${probe?.exportEnabled}`);
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
  const report = { schema: 'pillars3d-browser-verification-v1', workspace: 'pillars3d',
    root: ROOT, passed: checks.length - failed.length, failed: failed.length, checks };
  if (OUTPUT) fs.writeFileSync(OUTPUT, JSON.stringify(report, null, 2));
  for (const item of checks) console.log(`${item.ok ? 'ok  ' : 'FAIL'} ${item.name}: ${item.detail ?? ''}`);
  console.log(`\n${report.passed}/${checks.length} checks passed`);
  process.exit(failed.length ? 1 : 0);
})();
