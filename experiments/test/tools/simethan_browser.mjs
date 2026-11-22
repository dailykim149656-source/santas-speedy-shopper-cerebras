// Transport for record.mjs. The dashboard uses its own chat and speed widgets.
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

// A wrapped anchor's bounding-box center can fall in blank space between lines.
// Check each rendered line, including its clipping ancestors and actual hit target.
function visibleWrappedLinks() {
  return [...document.querySelectorAll('main a[href]')].filter(anchor => {
    const lines = [...anchor.getClientRects()].filter(r => r.width > 0 && r.height > 0);
    return lines.length > 1 && lines.every(r => {
      if (r.top < 0 || r.left < 0 || r.bottom > innerHeight || r.right > innerWidth) return false;
      for (let parent = anchor; parent; parent = parent.parentElement) {
        const s = getComputedStyle(parent), box = parent.getBoundingClientRect();
        if (s.visibility !== 'visible' || s.display === 'none' || Number(s.opacity) === 0) return false;
        if (/(auto|scroll|hidden|clip)/.test(s.overflowX) && (r.left < box.left || r.right > box.right)) return false;
        if (/(auto|scroll|hidden|clip)/.test(s.overflowY) && (r.top < box.top || r.bottom > box.bottom)) return false;
      }
      return [0.08, 0.5, 0.92].every(x =>
        anchor.contains(document.elementFromPoint(r.left + r.width * x, r.top + r.height / 2)));
    });
  }).map(anchor => anchor.href);
}

export async function loadOmowright() {
  const { chromium } = await import(pathToFileURL(process.env.SIMETHAN_PLAYWRIGHT));
  return { omowright: {
    compactSnapshot: snapshot => snapshot,
    async connectPipe({ browserPath }) {
      const browser = await chromium.launch({ executablePath: browserPath, headless: true });
      return {
        close: () => browser.close(),
        async newTab(route) {
          const origin = 'http://127.0.0.1:19873';
          const requested = new URL(route);
          const match = /^\/chat\/([^/]+)\/~key\/([^/]+)$/.exec(requested.pathname);
          if (requested.origin !== origin || !match) throw Error('Unexpected dashboard session route');
          const sessionKey = 'agent:' + decodeURIComponent(match[1]) + ':' + decodeURIComponent(match[2]);
          const dashboard = new URL('/chat', origin);
          dashboard.searchParams.set('session', sessionKey);
          // An explicit incognito context keeps browser session storage in memory. No token in URLs,
          // subprocess arguments, permanent browser profiles, traces or exported browser state.
          const context = await browser.newContext({ viewport: { width: 1600, height: 1200 } });
          const token = (await fs.readFile(path.join(process.env.SIMETHAN_STATE, 'gateway-token'), 'utf8')).trim();
          if (!token) throw Error('Missing local gateway credential');
          await context.addInitScript(({ expectedOrigin, credential }) => {
            if (window === window.top && location.origin === expectedOrigin) {
              window.__OPENCLAW_NATIVE_CONTROL_AUTH__ = {
                gatewayUrl: 'ws://127.0.0.1:19873', token: credential
              };
            }
          }, { expectedOrigin: origin, credential: token });
          const tab = await context.newPage();
          const session = await context.newCDPSession(tab);
          // The local HTTP server serves /chat. Its UI resolves the exact key to the canonical session path.
          await tab.goto(dashboard.href, { waitUntil: 'commit' });
          return {
            resolveSessionId: async () => undefined,
            cdp: { send: (method, params) => session.send(method, params) },
            async evaluate(fn, arg) {
              const ui = await tab.evaluate(fn, arg);
              if (fn.name === 'readViewport' && ui.links.some(link => !link.visible && !link.source)) {
                const wrapped = new Set(await tab.evaluate(visibleWrappedLinks));
                for (const link of ui.links) if (!link.source && wrapped.has(link.href)) link.visible = true;
              }
              return ui;
            },
            goto: (url, options) => tab.goto(url, options),
            screenshot: () => tab.screenshot(),
            snapshot: () => tab.locator('body').ariaSnapshot()
          };
        }
      };
    }
  } };
}
