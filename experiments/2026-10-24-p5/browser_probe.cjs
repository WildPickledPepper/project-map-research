// Installed before application scripts in the isolated experiment browser.
async function installProbe(context, runId) {
  await context.addInitScript(({runId}) => {
    const events = [], diagnostics = [], traces = new WeakMap();
    let sequence = 0, action = 'unspecified';
    const frame = () => window === window.top ? 'framework' : window.name || 'unnamed-frame';
    const clone = value => value === undefined ? null : JSON.parse(JSON.stringify(value));
    const state = session => session ? clone({
      name: session.name, id: session.id, project: session.activeDataSource?.projectName,
      selectedData: session.selectedData, singleLinkLine: session.singleLinkLine,
      linkLines: session.linkLines, drawLineMode: session.drawLineMode, renderTrigger: session.renderTrigger
    }) : null;
    const event = (stage, fields) => {
      try {
        events.push({...clone(fields), stage, run_id: runId, frame: frame(), action,
          event_id: `${runId}:${frame()}:${++sequence}`, observed_at: new Date().toISOString()});
      } catch (error) { diagnostics.push({stage, error: String(error)}); }
    };
    globalThis.__projectMapProbe = {
      events, diagnostics,
      setAction(value) { action = value; },
      event,
      begin(params) {
        const traceId = `${runId}:${frame()}:${action}:${sequence + 1}`;
        event('api.begin', {trace_id: traceId, command: 'unit/flows', params});
        return traceId;
      },
      resolved(traceId, result) {
        if (result && typeof result === 'object') traces.set(result, traceId);
        event('api.resolved', {trace_id: traceId, result});
      },
      stateApplied(result, session, source) {
        try { event('state.applied', {trace_id: traces.get(result), source, state: state(session)}); }
        catch (error) { diagnostics.push({stage: 'state.applied', error: String(error)}); }
      },
      readState() { return state(globalThis.__projectMapReadSession?.()); }
    };
  }, {runId});
}

async function collectProbe(page) {
  const frames = [];
  for (const frame of page.frames()) {
    try {
      const data = await frame.evaluate(() => globalThis.__projectMapProbe ? {
        events: globalThis.__projectMapProbe.events,
        diagnostics: globalThis.__projectMapProbe.diagnostics,
        state: globalThis.__projectMapProbe.readState()
      } : null);
      if (data) frames.push({name: frame.name(), ...data});
    } catch (error) { frames.push({name: frame.name(), capture_error: String(error)}); }
  }
  return frames;
}

module.exports = { installProbe, collectProbe };
