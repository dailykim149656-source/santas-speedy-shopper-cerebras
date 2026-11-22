import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {readViewport, showcaseCoverage} from '../../../tools/record.mjs';
import {loadOmowright} from '~/.codex/plugins/cache/sisyphuslabs/omo/5.1.30/skills/browser/scripts/omowright.mjs';
const dir=path.dirname(fileURLToPath(import.meta.url)), profile=fs.mkdtempSync(path.join(os.tmpdir(),'gift8-dom-qa-'));
const {omowright}=await loadOmowright();
const browser=await omowright.connectPipe({browserPath:path.join(os.homedir(),'Library/Caches/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-mac-arm64/chrome-headless-shell'),browserArgs:['--headless','--no-first-run',`--user-data-dir=${profile}`],storageRoot:profile});
const checks=[];
try {
 const page=await browser.newTab(pathToFileURL(path.join(dir,'dom-fixture.html')).href);
 const sid=await page.resolveSessionId();
 await page.cdp.send('Emulation.setDeviceMetricsOverride',{width:1200,height:900,deviceScaleFactor:1,mobile:false},sid);
 let ui=await page.evaluate(readViewport);
 fs.writeFileSync(path.join(dir,'dom-initial.json'),JSON.stringify(ui,null,2));
 const isVisible=(ui,s)=>ui.links.some(x=>x.href===`https://fixture.invalid/${s}`&&x.visible);
 for(const s of ['anchor','visible-json']) {assert.ok(isVisible(ui,s),s);checks.push(`${s}: visible`);}
 for(const s of ['hidden','invisible','transparent','clipped-url','occluded','collapsed','scrollable']) {assert.ok(!isVisible(ui,s),s);checks.push(`${s}: excluded`);}
 fs.writeFileSync(path.join(dir,'dom-initial.png'),await page.screenshot());
 await page.evaluate(readViewport,'https://fixture.invalid/collapsed');
 ui=await page.evaluate(readViewport);assert.ok(isVisible(ui,'collapsed'));checks.push('native collapsed details: expanded and visible');
 fs.writeFileSync(path.join(dir,'dom-expanded.png'),await page.screenshot());
 await page.evaluate(readViewport,'https://fixture.invalid/scrollable');
 ui=await page.evaluate(readViewport);assert.ok(isVisible(ui,'scrollable'));checks.push('overflow scroller: exact URL visible after scroll');
 fs.writeFileSync(path.join(dir,'dom-scrolled.png'),await page.screenshot());
 await page.evaluate(readViewport,null);
 ui=await page.evaluate(readViewport);assert.equal(ui.summaryVisible,true);checks.push('official summary remains visible');
 const urls=Array.from({length:5},(_,i)=>`https://fixture.invalid/${i}`),finish={urls,mean:1700};
 const observations=[0,1000,4500].map(at=>({at,file:`fixture-${at}.png`,urls,mean:1700,scoreVisible:true}));
 assert.equal(showcaseCoverage(observations,finish,0,4500).complete,true);
 assert.equal(showcaseCoverage(observations.map(x=>({...x,urls:urls.slice(0,4)})),finish,0,4500).complete,false);
 checks.push('coverage helper requires all five URL holds and score hold');
 fs.writeFileSync(path.join(dir,'dom-results.json'),JSON.stringify({fixtureOnly:true,checks,pass:true},null,2));
 console.log(JSON.stringify({pass:true,checks}));
} finally {await browser.close();fs.rmSync(profile,{recursive:true,force:true});}
