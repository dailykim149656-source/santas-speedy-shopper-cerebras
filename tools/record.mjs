#!/usr/bin/env node
// Records only an owned, local OpenClaw viewport. Bootstrap authentication is never captured.
import fs from 'node:fs';
import { createHash } from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { performance } from 'node:perf_hooks';
import { pathToFileURL } from 'node:url';
const browserRuntime=process.env.BOUNTY_BROWSER_RUNTIME || path.join(os.homedir(),'.codex/plugins/cache/sisyphuslabs/omo/5.1.30/skills/browser/scripts/omowright.mjs');
const { loadOmowright } = await import(pathToFileURL(browserRuntime));

const saveJSON = (file, value) => fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
const ffmpeg = flags => {
  const result = spawnSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', ...flags], { encoding: 'utf8' });
  if (result.status !== 0) throw Error(`ffmpeg failed: ${result.stderr}`);
};
const probeVideo = file => JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-show_format', '-show_streams', '-of', 'json', file], { encoding: 'utf8' }));
export function encodeRecording({ dir, framesDir, frames, ended, sourceVideo, durationSeconds }) {
  const duration = sourceVideo ? durationSeconds : (ended - frames[0].at) / 1000;
  if (!sourceVideo) {
    saveJSON(path.join(dir, 'capture-timeline.json'), { durationSeconds: duration, frames: frames.map(frame => ({ file: frame.file, seconds: (frame.at - frames[0].at) / 1000 })) });
    const concat = frames.map((frame, i) => `file '${frame.file}'\nduration ${((frames[i + 1]?.at ?? ended) - frame.at) / 1000}\n`).join('') + `file '${frames.at(-1).file}'\n`;
    fs.writeFileSync(path.join(framesDir, 'concat.txt'), concat, { mode: 0o600 });
  }
  const input = sourceVideo ? ['-i', sourceVideo] : ['-f', 'concat', '-safe', '0', '-i', path.join(framesDir, 'concat.txt')];
  // Sample the timestamped stills explicitly so long holds survive the encoder's frame sync.
  const frameRate = sourceVideo ? ['-fps_mode', 'cfr', '-r', '25'] : ['-vf', 'fps=25', '-fps_mode', 'passthrough'];
  const original = path.join(dir, 'original.mp4');
  ffmpeg([...input, ...frameRate, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-t', String(duration), original]);
  const originalProbe = probeVideo(original);
  saveJSON(path.join(dir, 'original-probe.json'), originalProbe);
  if (!originalProbe.streams.some(stream => stream.codec_type === 'video') || Math.abs(Number(originalProbe.format.duration) - duration) > 0.12) throw Error('Encoded original does not match the real recording timeline');
  let demoError;
  try {
    ffmpeg(['-ss', String(Math.max(0, duration - 55)), '-i', original, '-t', '55', '-fps_mode', 'cfr', '-r', '25', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', path.join(dir, 'demo.mp4')]);
    const demoProbe = probeVideo(path.join(dir, 'demo.mp4'));
    saveJSON(path.join(dir, 'ffprobe.json'), demoProbe);
    if (Number(demoProbe.format.duration) > 55) throw Error('Demo exceeds 55 seconds');
  } catch (error) { demoError = error.message; }
  return { durationSeconds: duration, originalPlayable: true, demoReady: !demoError, demoError };
}

export function recordingSidebarState(collapse) {
  const shell = document.querySelector('.shell');
  if (shell?.classList.contains('shell--nav-collapsed')) return 'collapsed';
  const button = shell?.querySelector('button.sidebar-brand__collapse[aria-label="Collapse sidebar"][aria-expanded="true"]:not(:disabled)');
  if (!button?.checkVisibility() || !button.getBoundingClientRect().width) return 'unavailable';
  if (!collapse) return 'expanded';
  button.click();
  return 'requested';
}

export function readViewport(scrollTo) {
  const roots = [document];
  for (let i = 0; i < roots.length; i++) for (const el of roots[i].querySelectorAll('*')) if (el.shadowRoot) roots.push(el.shadowRoot);
  const query = selector => roots.flatMap(root => [...root.querySelectorAll(selector)]);
  const visibleRect = (el, r, textOnly = false) => {
    if (r.width <= 0 || r.height <= 0 || r.top < 0 || r.left < 0 || r.bottom > innerHeight || r.right > innerWidth) return false;
    for (let parent = el; parent; parent = parent.parentElement || parent.getRootNode()?.host) {
      const style = getComputedStyle(parent);
      if (style.visibility !== 'visible' || style.display === 'none' || Number(style.opacity) === 0) return false;
      const b = parent.getBoundingClientRect();
      if ((/(auto|scroll|hidden|clip)/.test(style.overflowY) && (r.top < b.top || r.bottom > b.bottom)) || (/(auto|scroll|hidden|clip)/.test(style.overflowX) && (r.left < b.left || r.right > b.right))) return false;
    }
    const hit = el.getRootNode().elementFromPoint?.(r.left + r.width / 2, r.top + r.height / 2);
    return !!hit && (el === hit || (!textOnly && el.contains(hit)));
  };
  const visible = el => visibleRect(el, el.getBoundingClientRect());
  const summaries = query('.chat-gen-speed--summary');
  const summary = summaries.find(visible) || summaries[0];
  const anchors = query('main a[href]');
  const textURLs = [];
  for (const main of query('main')) {
    const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const el = node.parentElement;
      if (!el || el.closest('a,script,style,textarea,[contenteditable="true"]')) continue;
      for (const match of node.textContent.matchAll(/https?:\/\/[^\s"'<>\\]+/g)) {
        const range = document.createRange();
        range.setStart(node, match.index);
        range.setEnd(node, match.index + match[0].length);
        const rects = [...range.getClientRects()];
        textURLs.push({ href: match[0], el, range, visible: rects.length > 0 && rects.every(rect => visibleRect(el, rect, true)) });
      }
    }
  }
  if (scrollTo !== undefined) {
    const textURL = textURLs.find(item => item.href === scrollTo);
    const target = scrollTo ? anchors.find(el => el.href === scrollTo) || textURL?.el : summary;
    if (target) {
      for (let parent = target; parent; parent = parent.parentElement || parent.getRootNode()?.host) {
        if (parent.tagName === 'DETAILS' && !parent.open) parent.querySelector(':scope > summary')?.click();
      }
      target.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
      if (textURL && target === textURL.el) {
        for (let parent = target; parent; parent = parent.parentElement || parent.getRootNode()?.host) {
          const style = getComputedStyle(parent), r = textURL.range.getBoundingClientRect(), b = parent.getBoundingClientRect();
          parent.scrollBy({ top: /auto|scroll/.test(style.overflowY) ? r.top + r.height / 2 - b.top - b.height / 2 : 0,
            left: /auto|scroll/.test(style.overflowX) ? r.left + r.width / 2 - b.left - b.width / 2 : 0, behavior: 'instant' });
        }
        const r = textURL.range.getBoundingClientRect();
        window.scrollBy({ top: r.top + r.height / 2 - innerHeight / 2, behavior: 'instant' });
      }
    }
  }
  return { text: document.body.innerText, connected: query('[role="status"]').some(el => el.textContent.trim() === 'Connected'), composer: query('textarea,[contenteditable="true"]').some(el => !el.disabled), summary: summary?.textContent.trim() || '', summaryVisible: !!summary && visible(summary), links: [...anchors.map(el => ({ href: el.href, text: el.textContent, visible: visible(el) })), ...textURLs.map(item => ({ href: item.href, text: item.href, visible: item.visible, source: 'rendered-url-text' }))] };
}

export function showcaseCoverage(observations, finish, finishAt, now) {
  const recent = observations.filter(item => item.at >= Math.max(finishAt, now - 45000));
  const links = finish.urls.map(url => {
    let start, range;
    for (const item of recent) {
      if (item.urls.includes(url)) {
        start ??= item;
        if (item.at - start.at >= 1000) range = { url, from: start.at, to: item.at, firstFrame: start.file, lastFrame: item.file };
      } else start = undefined;
    }
    return range;
  });
  let scoreStart;
  for (const item of recent) {
    if (item.mean === finish.mean && item.scoreVisible) scoreStart ??= item;
    else scoreStart = undefined;
  }
  const last = recent.at(-1);
  const score = scoreStart && last && last.at - scoreStart.at >= 4500 ? { mean: finish.mean, from: scoreStart.at, to: last.at, firstFrame: scoreStart.file, lastFrame: last.file } : null;
  return { links, score, complete: links.every(Boolean) && !!score };
}

export async function captureFinalShowcase({ page, finish, finishAt, capture, readUI, shouldStop = () => false }) {
  const observations = [];
  let nextScrollAt = 0;
  let finalHoldFrom;
  for (;;) {
    if (shouldStop()) throw Error('Recording interrupted');
    if (performance.now() - finishAt > 120000) throw Error('Final viewport could not show five links and official score within one compact clip');
    const ui = await readUI();
    const headline = ui.summary.match(/(?:mean\s*)?([\d,]+(?:\.\d+)?)\s*(?:tok|tokens)/i) || ui.summary.match(/mean\D*([\d,]+)/i);
    const mean = headline ? Number(headline[1].replaceAll(',', '')) : NaN;
    const frame = await capture();
    observations.push({ at: frame.at, file: frame.file, mean: Number.isFinite(mean) ? mean : null, scoreVisible: ui.summaryVisible, urls: finish.urls.filter(url => ui.links.some(link => link.href === url && link.visible)) });
    const coverage = showcaseCoverage(observations, finish, finishAt, frame.at);
    if (coverage.links.every(Boolean) && ui.summaryVisible && mean === finish.mean) finalHoldFrom ??= frame.at;
    else finalHoldFrom = undefined;
    if (coverage.complete && frame.at - finalHoldFrom >= 4500) return { ui, observations, coverage, finalHoldFrom };
    if (performance.now() >= nextScrollAt) {
      const nextUrl = finish.urls.find((url, i) => !coverage.links[i]);
      const targetVisible = nextUrl ? ui.links.some(link => link.href === nextUrl && link.visible) : ui.summaryVisible;
      if (!targetVisible) {
        await page.evaluate(readViewport, nextUrl || null);
        nextScrollAt = performance.now() + 1250;
      }
    }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
}

export function buildViewportEvidence({ presentation, finishAt, originalStart, ended, framesDir, playableClipDuration }) {
  const clipStart = Math.max(originalStart, ended - 55000);
  const ranges = [presentation.coverage.score, ...presentation.coverage.links];
  if (ranges.some(item => !item || item.from < Math.max(finishAt, clipStart) || item.to > ended)) throw Error('Viewport evidence falls outside the final clip');
  const offsets = range => {
    const clipFromSeconds = (range.from - clipStart) / 1000;
    const clipToSeconds = Math.min((range.to - clipStart) / 1000, playableClipDuration - 0.04);
    if (clipFromSeconds < 0 || clipToSeconds - clipFromSeconds < (range.url ? 1 : 4)) throw Error('Encoded clip does not contain the required visible hold');
    return { ...(range.url ? { url: range.url } : { mean: range.mean }), originalFromSeconds: (range.from - originalStart) / 1000, originalToSeconds: clipToSeconds + (clipStart - originalStart) / 1000, clipFromSeconds, clipToSeconds, firstFrameSha256: createHash('sha256').update(fs.readFileSync(path.join(framesDir, range.firstFrame))).digest('hex'), lastFrameSha256: createHash('sha256').update(fs.readFileSync(path.join(framesDir, range.lastFrame))).digest('hex') };
  };
  return { schema_version: 1, verified: true, finishSeconds: (finishAt - originalStart) / 1000, demoStartSeconds: (clipStart - originalStart) / 1000, score: offsets(presentation.coverage.score), links: presentation.coverage.links.map(offsets) };
}

export function shouldRetainVideo(mean, threshold = JSON.parse(
  fs.readFileSync(new URL('../benchmark.json', import.meta.url), 'utf8')).video_threshold_displayed_mean_inclusive) {
  if (!Number.isSafeInteger(threshold) || threshold < 1) throw Error('Invalid displayed mean video threshold');
  return Number.isFinite(mean) && mean >= threshold;
}

async function main() {
const args = process.argv.slice(2);
const option = name => args[args.indexOf(name) + 1];
if (args.includes('--recover-from')) {
  if (!args.includes('--rehearsal') || !args.includes('--dir')) throw Error('Recovery fixture requires --rehearsal --dir <fresh-directory>');
  const source = path.resolve(option('--recover-from'));
  const output = path.resolve(option('--dir'));
  fs.mkdirSync(output, { recursive: false, mode: 0o700 });
  const metadata = JSON.parse(fs.readFileSync(path.join(source, 'recording.json'), 'utf8'));
  const original = path.join(source, 'original.mp4');
  const duration = Number(probeVideo(original).format.duration);
  const encoded = encodeRecording({ dir: output, sourceVideo: original, durationSeconds: duration });
  fs.copyFileSync(path.join(source, 'final.png'), path.join(output, 'final.png'));
  saveJSON(path.join(output, 'recording.json'), { run_id: 'REHEARSAL-recovery', sessionKey: metadata.sessionKey, qualifying: false, verified: false, provisional: true, discarded: false, rehearsal: true, full_run: false, authless: metadata.authless === true, reportedMean: metadata.final_ui_tps ?? metadata.reportedMean, sourceFixture: source, recoveredFromRecordedVideo: true, ...encoded });
  process.exit(0);
}
if (!args.includes('--session-key') || !args.includes('--dir')) throw Error('Usage: node record.mjs --session-key agent:main:<key> --dir <private-directory> [--rehearsal]');
const sessionKey = option('--session-key');
const match = /^agent:([^:]+):(.+)$/.exec(sessionKey);
if (!match) throw Error('Invalid session key');
const dir = path.resolve(option('--dir'));
const rehearsal = args.includes('--rehearsal');
fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
for (const name of ['ready.json', 'finish.json', 'original.mp4', 'recording.json']) if (fs.existsSync(path.join(dir, name))) throw Error(`Use a fresh private directory: ${name} already exists`);
const write = (name, data) => fs.writeFileSync(path.join(dir, name), typeof data === 'string' || Buffer.isBuffer(data) ? data : JSON.stringify(data, null, 2) + '\n', { mode: 0o600 });
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const cacheRoot = path.join(process.env.BOUNTY_ROOT || path.join(os.homedir(), 'Library/Caches/cerebras-speed-bounty/2026-11-22'), 'mean-2000');
const gatewayPort = process.env.BOUNTY_GATEWAY_PORT || '19862';
if (!/^[0-9]{4,5}$/.test(gatewayPort)) throw Error('Invalid gateway port');
const gatewayOrigin = `http://127.0.0.1:${gatewayPort}`;
const profile = path.join(cacheRoot, 'recorder-owned-profile');
fs.mkdirSync(profile, { recursive: true, mode: 0o700 });
const lockPath = path.join(cacheRoot, 'recorder-owned-profile.lock');
let lock;
const framesDir = fs.mkdtempSync(path.join(dir, '.frames-'));
const { omowright } = await loadOmowright();
let browser, page, finish, initial, readyAt, recordingEnded;
let interrupted = false;
let succeeded = false;
let keepProvisionalFrames = false;
let thresholdMet = false;
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { interrupted = true; });
const started = performance.now();
let frameCount = 0;
const frames = [];
async function saveProvisional(reason) {
  keepProvisionalFrames = true;
  let screenshotError;
  try { write('final.png', await page.screenshot()); }
  catch (error) {
    screenshotError = error.message;
    try { if (frames.length) ffmpeg(['-i', path.join(framesDir, frames.at(-1).file), '-frames:v', '1', path.join(dir, 'final.png')]); }
    catch (fallbackError) { screenshotError += `; last-frame recovery: ${fallbackError.message}`; }
  }
  let encoded, encodingError;
  try { encoded = encodeRecording({ dir, framesDir, frames, ended: (recordingEnded ??= performance.now()) }); }
  catch (error) { encodingError = error.message; }
  let originalPlayable = false;
  try { originalPlayable = probeVideo(path.join(dir, 'original.mp4')).streams.some(stream => stream.codec_type === 'video'); } catch {}
  write('recording.json', { run_id: finish?.run_id, sessionKey, qualifying: false, verified: false, provisional: true, discarded: false, reportedMean: finish?.mean, urls: finish?.urls, rehearsal, full_run: false, authless: true, readyAt, reason, rawFramesDirectory: framesDir, ...encoded, originalPlayable, encodingError, screenshotError });
  if (!originalPlayable) throw Error(encodingError || 'Provisional original could not be encoded; raw frames retained');
}
try {
  const lockDeadline = performance.now() + 240000;
  while (lock === undefined) {
    try { lock = fs.openSync(lockPath, 'wx', 0o600); }
    catch (error) {
      if (error.code !== 'EEXIST') throw error;
      const stat = fs.lstatSync(lockPath);
      if (!stat.isFile() || stat.uid !== process.getuid()) throw Error('Recorder profile lock ownership mismatch');
      const owner = fs.readFileSync(lockPath, 'utf8').trim();
      const pid = Number(owner);
      if (!Number.isInteger(pid) || pid < 1) throw Error('Recorder profile lock has no valid owner PID');
      let alive = true;
      try { process.kill(pid, 0); } catch (error) { if (error.code === 'ESRCH') alive = false; else throw error; }
      if (!alive) {
        if (fs.statSync(lockPath).ino === stat.ino && fs.readFileSync(lockPath, 'utf8').trim() === owner) fs.unlinkSync(lockPath);
        continue;
      }
      const command = execFileSync('ps', ['-p', String(pid), '-o', 'command='], { encoding: 'utf8' });
      if (!command.includes('record.mjs')) throw Error('Profile lock belongs to a different live process; refusing to reuse it');
      if (performance.now() >= lockDeadline || interrupted) throw Error('Timed out waiting for the owned recorder profile');
      write('status.json', { stage: 'waiting-for-owned-profile', ownerPid: pid });
      await sleep(500);
    }
  }
  fs.writeFileSync(lock, String(process.pid));
  browser = await omowright.connectPipe({
    browserPath: process.env.RECORDER_CHROMIUM || path.join(os.homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-mac-arm64/chrome-headless-shell'),
    browserArgs: ['--headless', '--no-first-run', `--user-data-dir=${profile}`], storageRoot: profile,
    readinessTimeoutMs: 60000,
    commandTimeoutMs: 90000,
  });
  const route = `${gatewayOrigin}/chat/${encodeURIComponent(match[1])}/~key/${encodeURIComponent(match[2])}`;
  page = await browser.newTab(route);
  const pairingDeadline = performance.now() + 35000;
  let reusedPairing = false;
  do {
    try {
      reusedPairing = await page.evaluate(() => [...document.querySelectorAll('[role="status"]')].some(el => el.textContent.trim() === 'Connected'));
    } catch (error) {
      if (!/Cannot find context with specified id|Execution context was destroyed/i.test(error.message || '')) throw error;
    }
    if (reusedPairing) break;
    await sleep(750);
  } while (performance.now() < pairingDeadline && !interrupted);
  if (!reusedPairing) {
    let auth;
    try {
      const raw = execFileSync(process.env.RECORDER_AUTH_NODE || path.join(os.homedir(), '.nvm/versions/node/v24.20.0/bin/node'), [process.env.RECORDER_AUTH_WRAPPER || path.join(cacheRoot, 'profile.mjs'), 'dashboard', '--json'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 180000 });
      auth = JSON.parse(raw.slice(raw.indexOf('{')));
    } catch { throw Error('Local dashboard bootstrap failed (output suppressed to protect authentication)'); }
    if (new URL(auth.browserUrl).origin !== gatewayOrigin) throw Error('Bootstrap is outside the isolated benchmark origin');
    await page.goto(auth.browserUrl, { waitUntil: 'commit' });
    auth = null;
    await sleep(1500);
    await page.goto(route, { waitUntil: 'commit' });
  }
  write('status.json', { stage: 'chat-navigation-complete' });
  const sid = await page.resolveSessionId();
  await page.cdp.send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1200, deviceScaleFactor: 1, mobile: false }, sid);
  const readUI = () => page.evaluate(readViewport);

  for (let i = 0; i < 120; i++) {
    try {
      initial = await readUI();
    } catch (error) {
      // The chat route can replace its document between the two CDP calls in
      // page.evaluate. Retry this read only; never replay a sidebar click.
      if (i === 119 || !/Cannot find context with specified id|Execution context was destroyed/i.test(error.message || '')) throw error;
      await sleep(500);
      continue;
    }
    if (initial.connected && initial.composer) break;
    if (i === 119) throw Error('Chat did not become connected and ready');
    await sleep(500);
  }
  let sidebarState = await page.evaluate(recordingSidebarState, true);
  if (sidebarState === 'requested') {
    await sleep(350);
    sidebarState = await page.evaluate(recordingSidebarState, false);
  }
  const capture = async () => {
    const at = performance.now();
    const file = `frame-${String(frameCount++).padStart(6, '0')}.jpg`;
    const { data } = await page.cdp.send('Page.captureScreenshot', { format: 'jpeg', quality: 85, captureBeyondViewport: false }, sid);
    fs.writeFileSync(path.join(framesDir, file), Buffer.from(data, 'base64'), { mode: 0o600 });
    frames.push({ file, at });
    return frames.at(-1);
  };
  await capture();
  readyAt = new Date().toISOString();
  write('ready.json', { ready: true, sessionKey, readyAt, rehearsal, capture: 'owned-local-viewport', initialSummary: initial.summary, reusedPairing, sidebarState });
  let finalUI, finishAt;
  while (!interrupted) {
    if (performance.now() - started > 30 * 60 * 1000) throw Error('Recorder timed out after 30 minutes');
    if (!finish && fs.existsSync(path.join(dir, 'finish.json'))) {
      finish = JSON.parse(fs.readFileSync(path.join(dir, 'finish.json'), 'utf8'));
      thresholdMet = shouldRetainVideo(finish.mean, finish.video_threshold_tps) || finish.retain_verified_record === true;
      finishAt = performance.now();
      if (typeof finish.qualifying !== 'boolean') throw Error('finish.qualifying must be boolean');
      if (!finish.qualifying) break;
      if (!Number.isFinite(finish.mean) || !Array.isArray(finish.urls) || finish.urls.length !== 5) throw Error('Qualifying finish requires numeric mean and exactly five URLs');
      if (!rehearsal && !thresholdMet) throw Error('Below-threshold run cannot be qualifying without --rehearsal');
    }
    if (finish?.qualifying) break;
    await capture();
    await sleep(200);
  }
  if (interrupted) throw Error('Recording interrupted');
  if (!finish.qualifying) {
    keepProvisionalFrames = (thresholdMet || finish.preserve_unqualified === true) && finish.discard_unverified !== true;
    if (keepProvisionalFrames) await saveProvisional('Result validation did not qualify');
    else write('recording.json', { run_id: finish.run_id, sessionKey, qualifying: false, provisional: false, discarded: true, reportedMean: finish.mean, rehearsal, full_run: false, authless: true });
  } else {
    const presentation = await captureFinalShowcase({ page, finish, finishAt, capture, readUI, shouldStop: () => interrupted });
    finalUI = presentation.ui;
    recordingEnded = performance.now();
    const originalStart = frames[0].at;
    write('viewport-observations.json', presentation.observations.map(item => ({ ...item, originalSeconds: (item.at - originalStart) / 1000 })));
    write('final.png', await page.screenshot());
    write('ui.txt', omowright.compactSnapshot(await page.snapshot()));
    write('ui.json', finalUI);
    const encoded = encodeRecording({ dir, framesDir, frames, ended: (recordingEnded ??= performance.now()) });
    if (!encoded.demoReady) throw Error(encoded.demoError);
    const duration = encoded.durationSeconds;
    const playableClipDuration = Number(probeVideo(path.join(dir, 'demo.mp4')).format.duration);
    const evidence = buildViewportEvidence({ presentation, finishAt, originalStart, ended: recordingEnded, framesDir, playableClipDuration });
    write('viewport-evidence.json', evidence);
    write('recording.json', { run_id: finish.run_id, sessionKey, qualifying: true, rehearsal, full_run: !rehearsal && !initial.summary, final_ui_tps: finish.mean, authless: true, readyAt, durationSeconds: duration, frameCount, sampling: 'timestamped real-time viewport screenshots; no speed changes', finalHoldSeconds: 4.5, viewportEvidence: 'viewport-evidence.json', demoStartSeconds: Math.max(0, duration - 55), urls: finish.urls });
  }
  succeeded = true;
} catch (error) {
  write('error.json', { error: error.message, rehearsal, sessionKey });
  if (frames.length && thresholdMet && finish?.discard_unverified !== true && !keepProvisionalFrames) {
    try { await saveProvisional(error.message); } catch (recoveryError) { write('recovery-error.json', { error: recoveryError.message }); }
  }
  process.exitCode = 1;
} finally {
  if (frames.length && (!succeeded || keepProvisionalFrames) && !fs.existsSync(path.join(dir, 'capture-timeline.json'))) {
    const ended = performance.now();
    write('capture-timeline.json', { provisional: true, rawFramesDirectory: framesDir, durationSeconds: (ended - frames[0].at) / 1000, frames: frames.map(frame => ({ file: frame.file, seconds: (frame.at - frames[0].at) / 1000 })) });
    fs.writeFileSync(path.join(framesDir, 'concat.txt'), frames.map((frame, i) => `file '${frame.file}'\nduration ${((frames[i + 1]?.at ?? ended) - frame.at) / 1000}\n`).join('') + `file '${frames.at(-1).file}'\n`, { mode: 0o600 });
  }
  try { if (browser) await browser.close(); } finally {
    if (lock !== undefined) { fs.closeSync(lock); fs.unlinkSync(lockPath); }
    if (succeeded && !keepProvisionalFrames) fs.rmSync(framesDir, { recursive: true, force: true });
  }
}

}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
