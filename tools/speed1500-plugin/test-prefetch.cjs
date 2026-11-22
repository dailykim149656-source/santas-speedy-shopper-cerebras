// Offline fixture for the native hook and its Python evidence validator.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRuntime} = require('./index.cjs');
async function main() {
  const [root, id] = process.argv.slice(2);
  const m = JSON.parse(fs.readFileSync(path.join(root,id,'manifest.json')));
  let calls = 0;
  const hooks = createRuntime({root}, async url => {
    calls++;
    const category = new URL(url).searchParams.get('search');
    return {url, status:200, arrayBuffer:async () => Buffer.from(JSON.stringify([
      {name:'Gift ' + category, permalink:'https://aisynthesis.com/product/' + category + '/'}]))};
  });
  const ctx = {runId:id, sessionKey:m.sessionKey, toolAuthority:{
    allows:name => name === 'web_fetch', assertActive() {}}};
  const input = {runId:id, provider:'cerebras', model:'moonshotai-kimi-k3.1-pro-trial', sessionId:'fixture'};
  assert.equal(await hooks.enrich({prompt:m.prompt},{...ctx,sessionKey:'foreign'}),undefined);
  await assert.rejects(hooks.enrich({prompt:'other shopping request'},ctx));
  const first = await hooks.enrich({prompt:m.prompt},ctx);
  await hooks.llmInput({...input,prompt:first.prependContext + '\n' + m.prompt},ctx);
  const retry = await hooks.enrich({prompt:'recovery instructions'},ctx);
  assert.equal(first.prependContext,retry.prependContext);
  await hooks.llmInput({...input,prompt:retry.prependContext + '\nrecovery instructions'},ctx);
  assert.equal(calls,5);
}
main().catch(err => { console.error(err); process.exitCode=1; });
