// Mock Cerebras chat completions for the relay integration test. Records every body it receives.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
const [port, dir, fail429] = [Number(process.argv[2]), process.argv[3], Number(process.argv[4] || 0)];
fs.mkdirSync(dir, {recursive: true});
let n = 0, failed = 0;
const textOf = c => typeof c === 'string' ? c : Array.isArray(c) ? c.map(p => p?.text ?? '').join('') : '';
http.createServer((req, res) => {
  const chunks = [];
  req.on('data', c => chunks.push(c));
  req.on('end', () => {
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    n += 1;
    fs.writeFileSync(path.join(dir, `req-${String(n).padStart(2, '0')}.json`), JSON.stringify({headers: req.headers, body}, null, 1));
    if (failed < fail429) {
      failed += 1;
      res.writeHead(429, {'content-type': 'application/json'});
      return res.end(JSON.stringify({message: "We're experiencing high traffic right now! Please try again soon.", type: 'too_many_requests_error', code: 'queue_exceeded'}));
    }
    res.writeHead(200, {'content-type': 'text/event-stream'});
    const send = obj => res.write('data: ' + JSON.stringify({id: 'chatcmpl-mock' + n, object: 'chat.completion.chunk', created: 1, model: body.model, ...obj}) + '\n\n');
    const tools = body.messages.filter(m => m.role === 'tool');
    if (!tools.length) {
      const user = textOf(body.messages.find(m => m.role === 'user').content);
      const urls = [...user.matchAll(/\{"url":"([^"]+)"\}/g)].map(m => m[1]);
      send({choices: [{index: 0, delta: {role: 'assistant', reasoning: 'Fetch five.'}, finish_reason: null}]});
      urls.forEach((url, i) => send({choices: [{index: 0, delta: {tool_calls: [{index: i, id: 'call_' + i, type: 'function', function: {name: 'web_fetch', arguments: JSON.stringify({url})}}]}, finish_reason: null}]}));
      send({choices: [{index: 0, delta: {}, finish_reason: 'tool_calls'}]});
      send({choices: [], usage: {prompt_tokens: 900, completion_tokens: 400, total_tokens: 1300}, time_info: {queue_time: 0.001, prompt_time: 0.01, completion_time: 0.4, total_time: 0.42}});
    } else {
      const lines = tools.map((t, i) => {
        const inner = JSON.parse(textOf(t.content)).text;
        const name = /"name":\s*"([^"]+)"/.exec(inner)?.[1];
        const link = /"permalink":\s*"([^"]+)"/.exec(inner)?.[1];
        return `${i + 1}. [${name}](${link})`;
      });
      send({choices: [{index: 0, delta: {role: 'assistant', content: lines.join('\n')}, finish_reason: null}]});
      send({choices: [{index: 0, delta: {}, finish_reason: 'stop'}]});
      send({choices: [], usage: {prompt_tokens: 2000, completion_tokens: 161, total_tokens: 2161}, time_info: {queue_time: 0.001, prompt_time: 0.01, completion_time: 0.1, total_time: 0.12}});
    }
    res.end('data: [DONE]\n\n');
  });
}).listen(port, '127.0.0.1', () => console.log('mock listening', port));
