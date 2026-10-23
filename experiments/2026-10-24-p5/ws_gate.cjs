// Playwright's real-server WebSocket routing controls delivery, retaining original message bytes.
async function installGate(context, runId, events, connections) {
  const audit = [], held = [];
  let selectedCommand = null, hold = false;
  const mark = (phase, fields = {}) => audit.push({sequence: audit.length + 1, phase, ...fields});
  const decode = raw => { try { return JSON.parse(raw.toString()); } catch { return {unparsed: raw.toString()}; } };
  await context.routeWebSocket(/.*/, route => {
    const server = route.connectToServer();
    const connection = {id: `${runId}:socket:${connections.length + 1}`, url: route.url(), closed: false};
    connections.push(connection);
    const requests = new Map();
    const record = (direction, message) => events.push({direction, connection_id: connection.id,
      socket: connection.url, at: new Date().toISOString(), message, capture_source: 'Playwright real-server route'});
    route.onMessage(raw => {
      const message = decode(raw);
      if (message.type === 'request') requests.set(message.id, message);
      record('framesent', message);
      server.send(raw);
    });
    server.onMessage(raw => {
      const message = decode(raw);
      const request = requests.get(message.requestId);
      if (hold && message.type === 'response' && request?.command === selectedCommand) {
        held.push({raw, message, request, connection_id: connection.id, deliver: () => {
          record('framereceived', message); route.send(raw);
        }});
        mark('held', {request_id: message.requestId, trace_id: request.params?.__projectMapTrace,
          project: request.projectName, connection_id: connection.id});
      } else {
        record('framereceived', message);
        route.send(raw);
      }
    });
    route.onClose((code, reason) => { connection.closed = true; server.close({code, reason}); });
    server.onClose((code, reason) => { connection.closed = true; route.close({code, reason}); });
  });
  return {
    audit, held, mark,
    arm(command) { selectedCommand = command; hold = true; mark('armed', {command}); },
    releaseAll() {
      hold = false;
      for (const item of held) {
        if (item.released) throw new Error('Cannot release the same held response twice');
        mark('released', {request_id: item.message.requestId, connection_id: item.connection_id});
        item.deliver(); item.released = true;
      }
    }
  };
}

module.exports = {installGate};
