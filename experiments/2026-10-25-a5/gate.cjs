// Control actual backend bytes at a recorded Playwright delivery boundary.
async function install(context, wire) {
  const audit=[], held=[]; let armed=null;
  await context.routeWebSocket(/.*/, route => {
    const server=route.connectToServer();const requests=new Map();
    const connection='socket:'+wire.filter(e=>e.stage==='socket.open').length;
    wire.push({stage:'socket.open',connection});
    const decode=raw=>JSON.parse(String(raw));
    route.onMessage(raw=>{
      const message=decode(raw);if(message.type==='request')requests.set(message.id,message);
      wire.push({direction:'framesent',connection,message});server.send(raw);
    });
    server.onMessage(raw=>{
      const message=decode(raw), request=requests.get(message.requestId);
      if (armed && message.type==='response' && request?.command===armed.command &&
          (!armed.page || request.params?.currentPage===armed.page)) {
        const mode=armed.mode;armed=null;
        audit.push({stage:mode,request_id:message.requestId,request});
        if(mode==='hold') {
          held.push({request,message,release:()=>{wire.push({direction:'framereceived',connection,message});route.send(raw);}});return;
        }
        if(mode==='fail') {
          const failed={...message,result:false,body:undefined,error:{code:9001,message:'A5 controlled response failure'}};
          wire.push({direction:'framereceived',connection,message:failed,original_backend_response:message});
          route.send(JSON.stringify(failed));return;
        }
      }
      wire.push({direction:'framereceived',connection,message});route.send(raw);
    });
    route.onClose((code,reason)=>server.close({code,reason}));
    server.onClose((code,reason)=>route.close({code,reason}));
  });
  return {audit,held,arm(command,mode='hold',page){armed={command,mode,page};audit.push({stage:'armed',...armed});},
    release(){for(const item of held){if(item.released)continue;item.release();item.released=true;audit.push({stage:'released',request_id:item.message.requestId});}}};
}
module.exports={install};
