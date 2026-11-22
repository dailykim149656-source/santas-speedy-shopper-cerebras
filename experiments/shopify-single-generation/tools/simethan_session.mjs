import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile,spawn} from 'node:child_process';
import {setTimeout as delay} from 'node:timers/promises';
import {promisify} from 'node:util';
const execute = promisify(execFile);

export async function prepareShoppingSession({slot, state, port, directory, deadlineTime}) {
  if (!Number.isFinite(deadlineTime) || Date.now() >= deadlineTime) throw Error('Deadline before Shopify search');
  const sessions = path.join(directory, 'sessions');
  await fs.mkdir(sessions, {recursive:true, mode:0o700});
  await fs.writeFile(path.join(sessions, slot.id + '.json'), JSON.stringify({
    id:slot.id, sessionKey:slot.sessionKey, freshEmptySession:true, createdAt:Date.now()
  }), {flag:'wx', mode:0o600});
  const folder=path.join(directory,slot.id);
  await fs.mkdir(folder,{recursive:true,mode:0o700});
  await fs.copyFile(path.join(sessions,slot.id+'.json'),path.join(folder,'session.json'));
  const film=fileURLToPath(new URL('./simethan_film.py',import.meta.url));
  let recording=false;
  const postRunOnly=await fs.access(path.join(directory,'post-run-video-only.json')).then(()=>true,()=>false);
  if (!postRunOnly && await fs.access(film).then(()=>true,()=>false)) {
    const log = await fs.open(path.join(folder,'film.log'),'ax',0o600);
    const env={...process.env};
    delete env.CEREBRAS_API_KEY;
    const watcher=spawn('python3',['-B',film,'--out',directory,'--state',state,'--port',String(port),'--id',slot.id,'--session-key',slot.sessionKey],{env,stdio:['ignore',log.fd,log.fd]});
    watcher.unref();
    await log.close();
    recording=true;
  }
  const helper = fileURLToPath(new URL('./simethan_prefetch.cjs', import.meta.url));
  try {
    await execute(process.execPath,[helper,directory,slot.id],{
      timeout:Math.max(1, Math.min(35000,deadlineTime-Date.now())),
      env:{...process.env,PREFETCH_DEADLINE_MS:String(deadlineTime)}
    });
  } catch {
    throw Error('Shopify lookup failed before model dispatch');
  }
  const receipt = JSON.parse(await fs.readFile(path.join(directory,slot.id,'prefetch.json'),'utf8'));
  if (!receipt.valid || receipt.id!==slot.id || receipt.products?.length!==5) throw Error('Incomplete fresh Shopify receipts');
  if (recording) {
    const until=Math.min(Date.now()+9000,deadlineTime);
    while (Date.now()<until && !await fs.access(path.join(folder,'media/ready.json')).then(()=>true,()=>false)) await delay(200);
  }
  if (Date.now()>=deadlineTime) throw Error('Deadline before model dispatch');
  const target = path.join(directory,'active.json');
  await fs.writeFile(target+'.tmp', JSON.stringify({id:slot.id,prompt:slot.prompt,deadline:new Date(deadlineTime).toISOString(),deadlineMs:deadlineTime}), {mode:0o600});
  await fs.rename(target+'.tmp',target);
}
