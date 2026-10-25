const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const [source, output, url, data, scenario, pageSize, fault] = process.argv.slice(2);
const {chromium, expect} = require(path.join(source, 'e2e/node_modules/@playwright/test'));
const expectedInput = JSON.parse(fs.readFileSync(path.join(output,'expected.json'),'utf8'));

function validateBlocks(blocks, device='0') {
  const expected=expectedInput.devices[device];
  const expectedKeys=[...expected.positive_lifetimes,...expected.initial_lifetimes]
    .map(x=>`${x.address}:${x.alloc}:${x.free}`).sort();
  const actualKeys=blocks.map(x=>`${x.addr}:${x.allocEventId}:${x.freeEventId}`).sort();
  assert.ok(JSON.stringify(actualKeys)===JSON.stringify(expectedKeys),`Independent allocation-lifetime multiset must equal Worker handoff (device ${device}, expected ${expectedKeys.length}, actual ${actualKeys.length})`);
  return {device,expected_blocks:expected.expected_blocks,actual_blocks:blocks.length,identity_fields:['address','allocEventId','freeEventId']};
}

async function resource(frame,label) {
  return frame.evaluate(async label=>{
    const files=[];
    async function list(directory,prefix='') {
      for await (const [name,handle] of directory.entries()) {
        if(handle.kind==='directory')await list(handle,prefix+name+'/');
        else {const file=await handle.getFile();files.push({name:prefix+name,bytes:file.size});}
      }
    }
    try {await list(await navigator.storage.getDirectory());}
    catch(error){return {label,error:String(error)};}
    return {label,files,entry_count:files.length,file_bytes:files.reduce((n,f)=>n+f.bytes,0),
      js_heap:performance.memory ? {used:performance.memory.usedJSHeapSize,total:performance.memory.totalJSHeapSize} : null};
  },label);
}

async function install(context) {
  await context.addInitScript(({pageSize, fault, run}) => {
    const events = []; let sequence = 0; const traces = new WeakMap(), pending = new Map();
    const clone = value => JSON.parse(JSON.stringify(value, (k,v) => typeof v === 'bigint' ? String(v) : v));
    const event = (stage, fields = {}) => {
      if (stage === 'connector.response') {
        const trace = pending.get(fields.id);
        if (trace && fields.response?.body && typeof fields.response.body === 'object') {
          traces.set(fields.response.body, trace);
        }
      }
      try { events.push({stage, ...clone(fields), frame: window.name || 'framework', event_id: `${run}:${window.name}:${++sequence}`, at: performance.now()}); }
      catch (error) { events.push({stage:'probe.error', error:String(error)}); }
    };
    globalThis.__a5 = {events, event, begin(command, params, id) {
      const trace = `${run}:${window.name}:request:${sequence+1}`;
      pending.set(id, trace); event('request.begin', {command, params, id, trace_id:trace}); return trace;
    }, trace:object => traces.get(object)};
    globalThis.__projectMapProbe = {event};
    globalThis.__a5PageSize = Number(pageSize);
    globalThis.__a5FaultDropBlock = fault === 'fault';
    for (const name of ['requestDataDebounced', 'requestData']) {
      let fn;
      Object.defineProperty(window, name, {configurable:true, get:()=>fn, set(value) {
        fn = typeof value !== 'function' ? value : new Proxy(value, {apply(target, receiver, args) {
          const id = `${name}:${sequence+1}`; event('schedule.call', {name,id,command:args[0],params:args[1]});
          const result = Reflect.apply(target,receiver,args);
          result?.then(value => event('schedule.resolved',{id,trace_id:traces.get(value)}), error => event('schedule.rejected',{id,error:String(error)}));
          return result;
        }});
      }});
    }
    // Observe the actual Worker boundary, before buffers detach and after completion messages.
    const NativeWorker = globalThis.Worker;
    globalThis.Worker = class extends NativeWorker {
      constructor(...args) {
        super(...args);
        globalThis.__a5Workers ??= []; this.__a5Id=globalThis.__a5Workers.length;
        globalThis.__a5Workers.push(this);
        this.addEventListener('message', e => event('worker.received', {worker_id:this.__a5Id,message:e.data}));
        this.addEventListener('error', e => event('worker.error', {worker_id:this.__a5Id,message:e.message}));
      }
      postMessage(message, transfer) {
        const buffers = Array.isArray(transfer) ? transfer.filter(x => x instanceof ArrayBuffer) : [];
        const bytes = buffers.reduce((n,b) => n+b.byteLength, 0);
        event('worker.sent', {worker_id:this.__a5Id,type:message.type, generation:message.generation, requestId:message.requestId,
          fileHash:message.fileHash, transfer_buffers:buffers.length, transfer_bytes:bytes});
        const result = super.postMessage(message, transfer);
        if (buffers.length) event('worker.transferred', {worker_id:this.__a5Id,type:message.type, generation:message.generation,
          sender_remaining_bytes:buffers.reduce((n,b) => n+b.byteLength, 0)});
        return result;
      }
    };
  }, {pageSize, fault, run:path.basename(output)});
}

async function main() {
  const browser = await chromium.launch({headless:true, args:['--enable-precise-memory-info']});
  const context = await browser.newContext({viewport:{width:1600,height:1000}, locale:'en-US'});
  await install(context);
  const page = await context.newPage(); const wire = [], errors = [];
  const gate = await require('./gate.cjs').install(context,wire);
  page.on('pageerror', e => errors.push(String(e)));
  page.on('websocket', ws => {
    return; // The explicit gate records forwarding and delivery rather than incoming held bytes.
    const connection = 'socket:'+wire.filter(e => e.stage==='socket.open').length;
    wire.push({stage:'socket.open',connection});
    for (const direction of ['framesent','framereceived']) ws.on(direction, f => {
      try { wire.push({direction, connection, message:JSON.parse(String(f.payload))}); }
      catch { wire.push({direction,connection,unparsed:String(f.payload).slice(0,250)}); }
    });
  });
  let failure = null; const checks = {}, frames = [], resources=[];
  try {
    await page.goto(url);
    await page.frameLocator('#Timeline').locator('#main-container').waitFor({state:'attached',timeout:30000});
    await page.locator('.btn-import').click();
    await page.getByTestId('filePathInput').fill(data);
    await page.getByTestId('filePathInput').press('Enter');
    const confirm = page.getByRole('button',{name:'Confirm',exact:true});
    await expect(confirm).toBeEnabled({timeout:15000}); await confirm.click();
    await expect.poll(() => wire.some(e => e.message?.event === (scenario.startsWith('communication') ? 'allPagesSuccess' : 'parse/leaksMemoryCompleted')), {timeout:90000}).toBeTruthy();
    const communication = scenario.startsWith('communication');
    await page.getByRole('menuitem', {name:communication ? /communication/i : 'MemScope', exact:!communication}).click();
    const frame = page.frameLocator(communication ? '#Communication' : '#MemScope');
    if (communication) {
      await expect.poll(async () => (await frame.locator('body').innerText()).includes('Step'), {timeout:30000}).toBeTruthy();
      await expect.poll(() => wire.some(e => e.direction==='framereceived' && e.message?.command==='communication/duration/iterations'), {timeout:30000}).toBeTruthy();
      await expect.poll(async () => frame.locator('#step-select').getAttribute('value'), {timeout:30000}).not.toBeNull();
      checks.imported = true;
      await expect.poll(async()=>frame.locator('body').evaluate(()=>globalThis.__a5.events.filter(e=>e.stage==='consumer.iterations').length),{timeout:30000}).toBeGreaterThan(0);
      checks.iterations=await frame.locator('body').evaluate(()=>globalThis.__a5.events.filter(e=>e.stage==='consumer.iterations').at(-1));
      assert.deepEqual(checks.iterations.compareOptions.map(x=>x.value),expectedInput.communication_steps);
      if(scenario==='communication-scheduling') {
        const state=await frame.locator('body').evaluate(async()=>{
          const tasks=[];const track=(name,promise)=>{
            const task={name,status:'pending'};tasks.push(task);
            promise.then(value=>{task.status='resolved';task.value=value;},error=>{task.status='rejected';task.error=String(error);});
          };
          globalThis.__a5.event('driver.action',{action:'three identical iteration calls',provenance:'direct exported API control after real UI import'});
          for(let i=0;i<3;i++)track('trailing-'+i,globalThis.__a5Queries.queryIterations({isCompare:false}));
          await new Promise(r=>setTimeout(r,900));
          const iterations=JSON.parse(JSON.stringify(tasks));
          const p={iterationId:'2',baselineIterationId:'',isCompare:false};
          for(let i=0;i<3;i++)track('leading-'+i,globalThis.__a5Queries.queryStages(p));
          await new Promise(r=>setTimeout(r,900));
          const trailingBefore=globalThis.__a5.events.filter(e=>e.stage==='request.begin').length;
          track('cancel-trailing',globalThis.__a5Queries.queryIterations({isCompare:false}));
          globalThis.requestDataDebounced.cancel();
          await new Promise(r=>setTimeout(r,450));
          const cancelledTrailingSent=globalThis.__a5.events.filter(e=>e.stage==='request.begin').length-trailingBefore;
          track('cancel-leading-0',globalThis.__a5Queries.queryStages(p));
          track('cancel-leading-1',globalThis.__a5Queries.queryStages(p));
          globalThis.__a5Queries.queryStages.cancel();
          await new Promise(r=>setTimeout(r,450));
          track('flush-trailing',globalThis.__a5Queries.queryIterations({isCompare:false}));
          globalThis.requestDataDebounced.flush();
          await new Promise(r=>setTimeout(r,500));
          return {iterations,tasks,cancelledTrailingSent,pendingKeys:globalThis.requestDataDebounced.getPendingKeys()};
        });
        checks.scheduling=state;
        assert.equal(state.iterations.filter(t=>t.status==='resolved').length,1,'Trailing replacement resolves the final caller under the current implementation');
        assert.equal(state.iterations.filter(t=>t.status==='pending').length,2,'Keep replaced unresolved callers visible');
        assert.equal(state.tasks.filter(t=>t.name.startsWith('leading')&&t.status==='resolved').length,3);
        assert.equal(state.cancelledTrailingSent,0);
        assert.equal(state.tasks.find(t=>t.name==='cancel-trailing').status,'pending');
        assert.equal(state.tasks.filter(t=>t.name.startsWith('cancel-leading')&&t.status==='rejected').length,2);
        assert.equal(state.tasks.find(t=>t.name==='flush-trailing').status,'resolved');
      }
    } else {
      const graph = frame.getByTestId('blockDiagramSection');
      await expect(graph).toHaveAttribute('data-loading-blocks','false',{timeout:90000});
      await expect(graph).toHaveAttribute('data-progressive-render-percent','100',{timeout:90000});
      checks.imported = true;
      checks.graph_attributes = await graph.evaluate(e => Object.fromEntries([...e.attributes].filter(a=>a.name.startsWith('data-')).map(a=>[a.name,a.value])));
      const target=page.frames().find(f=>f.name()==='MemScope');
      const initialDevice=await target.evaluate(()=>globalThis.__a5Session().deviceId);
      resources.push(await resource(target,'initial build complete'));
      if(!scenario.startsWith('memscope')) {
        const handoff=await target.evaluate(()=>globalThis.__a5.events.filter(e=>e.stage==='worker.handoff').at(-1));
        checks.blocks=validateBlocks(handoff.data.blocks,initialDevice);
      } else {
        const handoff=await target.evaluate(()=>globalThis.__a5.events.filter(e=>e.stage==='worker.handoff').at(-1));
        const selected=await target.evaluate(()=>({deviceId:globalThis.__a5Session().deviceId,eventType:globalThis.__a5Session().eventType}));
        const expected=expectedInput.memscope[`${selected.deviceId}:${selected.eventType}`];
        assert.deepEqual(handoff.data.blocks.map(b=>`${b.addr}:${b.size}`).sort(),expected.map(b=>`${b[0]}:${b[1]}`).sort());
        checks.blocks={...selected,expected_blocks:expected.length,actual_blocks:handoff.data.blocks.length,identity_fields:['address','size']};
      }
      const remove=async()=>target.evaluate(async()=>{
        const cache=globalThis.__a5.events.filter(e=>e.stage==='cache.result').at(-1);
        const last=globalThis.__a5.events.filter(e=>e.stage==='worker.sent'&&e.type==='setMemoryBlockData').at(-1);
        const generation=Math.max(...globalThis.__a5.events.filter(e=>e.stage==='worker.sent'&&e.generation!==undefined).map(e=>e.generation))+1;
        globalThis.__a5.event('driver.action',{action:'destroy active graph then remove persistent cache',fileHash:cache.cacheFileHash,provenance:'explicit Worker lifecycle control'});
        globalThis.__a5Workers[last.worker_id].postMessage({type:'destroy',generation});
        await globalThis.__a5RemoveCache({fileHash:cache.cacheFileHash});
      });
      const reload=async()=>target.evaluate(async()=>{
        globalThis.__a5.event('driver.action',{action:'reload blocks',provenance:'direct exported loader control'});
        await globalThis.__a5ReloadBlocks(globalThis.__a5Session());
      });
      if(scenario==='snapshot-cache') {
        let before=wire.filter(e=>e.direction==='framesent'&&e.message?.command==='Memory/snapshot/blocks').length;
        await reload();
        let after=wire.filter(e=>e.direction==='framesent'&&e.message?.command==='Memory/snapshot/blocks').length;
        checks.cache_hit_avoids_blocks_fetch=before===after;assert.equal(before,after,'Cache hit must avoid blocks network fetch');
        resources.push(await resource(target,'cache hit complete'));
        await remove();resources.push(await resource(target,'cache removal complete'));
        await reload();resources.push(await resource(target,'cache rebuild complete'));
        checks.cache_statuses=await target.evaluate(()=>globalThis.__a5.events.filter(e=>e.stage==='cache.result').map(e=>e.cacheStatus));
        assert.deepEqual(checks.cache_statuses.slice(-3),['miss','hit','miss']);
        checks.rebuilt=validateBlocks(await target.evaluate(()=>globalThis.__a5.events.filter(e=>e.stage==='worker.handoff').at(-1).data.blocks));
      } else if(scenario==='snapshot-replacement') {
        const nextDevice=initialDevice==='0'?'1':'0';
        await remove();gate.arm('Memory/snapshot/blocks','hold',2);
        const oldReload=reload();
        await expect.poll(()=>gate.held.length,{timeout:30000}).toBe(1);
        const input=frame.locator('#select-deviceId');
        await input.locator('xpath=ancestor::*[contains(concat(" ",normalize-space(@class)," ")," ant-select ")][1]').locator('.ant-select-selector').click();
        await frame.locator('.ant-select-dropdown:visible').getByTitle(nextDevice,{exact:true}).click();
        await input.press('Escape');await page.mouse.click(0,0);
        await expect.poll(async()=>target.evaluate(device=>globalThis.__a5.events.filter(e=>e.stage==='load.adopted'&&e.deviceId===device).length,nextDevice),{timeout:90000}).toBeGreaterThan(0);
        const stable=await target.evaluate(()=>globalThis.__a5Session().loadedMemoryBlockContextKey);
        gate.release();await oldReload;
        checks.stale_discard=await target.evaluate(()=>globalThis.__a5.events.some(e=>e.stage==='load.error'&&e.superseded));
        assert.equal(checks.stale_discard,true);
        assert.equal(await target.evaluate(()=>globalThis.__a5Session().loadedMemoryBlockContextKey),stable);
        checks.new_device=validateBlocks(await target.evaluate(()=>globalThis.__a5.events.filter(e=>e.stage==='worker.handoff').at(-1).data.blocks),nextDevice);
      } else if(scenario==='snapshot-failure') {
        await remove();gate.arm('Memory/snapshot/blocks','fail',1);
        const before=await target.evaluate(()=>globalThis.__a5.events.filter(e=>e.stage==='load.adopted').length);
        await reload();
        checks.failure=await target.evaluate(()=>({loading:globalThis.__a5Session().loadingBlocks,errors:globalThis.__a5.events.filter(e=>e.stage==='load.error'),adopted:globalThis.__a5.events.filter(e=>e.stage==='load.adopted').length}));
        assert.equal(checks.failure.loading,false);assert.equal(checks.failure.adopted,before);assert.ok(checks.failure.errors.length>0);
      }
    }
    await page.waitForTimeout(500);
    checks.capabilities = await page.evaluate(() => ({secureContext:isSecureContext, isolated:crossOriginIsolated,
      sharedArrayBuffer:typeof SharedArrayBuffer, worker:typeof Worker, offscreenCanvas:typeof OffscreenCanvas,
      js_heap:performance.memory ? {used:performance.memory.usedJSHeapSize,total:performance.memory.totalJSHeapSize,limit:performance.memory.jsHeapSizeLimit} : null}));
    await page.screenshot({path:path.join(output,'loaded.png'),fullPage:true});
  } catch (error) {
    failure = String(error.stack || error);
    await page.screenshot({path:path.join(output,'failed.png'),fullPage:true}).catch(()=>{});
  } finally {
    for (const frame of page.frames()) {
      try {
        frames.push({name:frame.name(), url:frame.url(), text:await frame.locator('body').innerText(),
          probe:await frame.evaluate(() => globalThis.__a5?.events ?? [])});
      } catch(e) {frames.push({name:frame.name(),error:String(e)});}
    }
    fs.writeFileSync(path.join(output,'wire.json'),JSON.stringify(wire,null,2));
    fs.writeFileSync(path.join(output,'frames.json'),JSON.stringify(frames,null,2));
    fs.writeFileSync(path.join(output,'resources.json'),JSON.stringify(resources,null,2));
    fs.writeFileSync(path.join(output,'gate.json'),JSON.stringify({audit:gate.audit,held:gate.held.map(({request,message,released})=>({request,message,released}))},null,2));
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({scenario,page_size:Number(pageSize),fault,passed:!failure,failure,checks,errors,browser:browser.version()},null,2));
    await browser.close();
  }
  if (failure) throw Error(failure);
}
main().catch(e => {console.error(e);process.exitCode=1;});
