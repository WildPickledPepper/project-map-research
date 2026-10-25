const fs=require('node:fs'),path=require('node:path');
const [source,output]=process.argv.slice(2);
const {chromium}=require(path.resolve(source,'e2e/node_modules/playwright'));
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage();
    const capabilities=await page.evaluate(()=>({context:location.href,worker:typeof Worker,offscreenCanvas:typeof OffscreenCanvas,
      webgl2:!!document.createElement('canvas').getContext('webgl2'),sharedArrayBuffer:typeof SharedArrayBuffer,
      secureContext:isSecureContext,crossOriginIsolated}));
    const result={evidence_kind:'executed_headless_browser_environment_probe',browser_version:browser.version(),capabilities,
      product_scenarios_executed:0,scope:'about:blank probe; product headers, OPFS storage and Worker rendering require a served-product scenario'};
    fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
