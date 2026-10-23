const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {expectedFlow, selectFlowSlice, assertFlowResponse} = require('./flow_scenario.cjs');

async function runParallel({page, events, source, output, data, gate}) {
  const {expect} = require(path.join(source, 'e2e/node_modules/@playwright/test'));
  const expected = [expectedFlow(data, 0), expectedFlow(data, 1)];
  fs.writeFileSync(path.join(output, 'expected-flows.json'), JSON.stringify(expected, null, 2));
  const selections = [];
  gate.arm('unit/flows');
  for (let i = 0; i < expected.length; i++) {
    const target = await selectFlowSlice({page, expected: expected[i], expect});
    selections.push(target.geometry);
    await target.frame.evaluate(action => globalThis.__projectMapProbe.setAction(action), `parallel-click-${i + 1}`);
    await target.canvas.click({position: target.position});
    await expect.poll(() => gate.held.length, {timeout: 20000}).toBe(i + 1);
  }
  assert.equal(events.filter(event => event.direction === 'framereceived' && event.message.command === 'unit/flows').length, 0);
  assert.equal(new Set(gate.held.map(item => item.request.id)).size, 2);
  assert.equal(new Set(gate.held.map(item => item.request.params.__projectMapTrace)).size, 2);
  assert.notEqual(gate.held[0].request.params.id, gate.held[1].request.params.id);
  gate.mark('two_distinct_requests_pending_before_delivery', {request_ids: gate.held.map(item => item.request.id)});
  gate.releaseAll();
  const frame = page.frames().find(item => item.name() === 'Timeline');
  await expect.poll(() => frame.evaluate(() => globalThis.__projectMapProbe.events.filter(event =>
    event.stage === 'state.applied').length), {timeout: 15000}).toBe(2);
  const captured = await frame.evaluate(() => globalThis.__projectMapProbe.events);
  const rows = gate.held.map((item, i) => {
    const actual = assertFlowResponse(item.message, expected[i], selections[i].timeOrigin);
    const traceId = item.request.params.__projectMapTrace;
    const resolved = captured.filter(event => event.stage === 'api.resolved' && event.trace_id === traceId);
    const applied = captured.filter(event => event.stage === 'state.applied' && event.trace_id === traceId);
    assert.equal(resolved.length, 1); assert.equal(applied.length, 1);
    assert.deepEqual(resolved[0].result, item.message.body);
    const lines = Object.values(applied[0].state.singleLinkLine).flat();
    assert.equal(lines.length, actual.length);
    for (const flow of actual) {
      assert(lines.some(line => line.from.timestamp === flow.from.timestamp && line.to.timestamp === flow.to.timestamp &&
        line.from.id === flow.from.id && line.to.id === flow.to.id), 'Each API result must reach its own state assignment');
    }
    return {request_id: item.request.id, trace_id: traceId, selected_slice_id: item.request.params.id,
      independent_expected: expected[i], adopted_flow_from_timestamps: lines.map(line => line.from.timestamp)};
  });
  const finalState = await frame.evaluate(() => globalThis.__projectMapProbe.readState());
  assert.equal(finalState.selectedData.id, gate.held[1].request.params.id);
  assert.deepEqual(Object.values(finalState.singleLinkLine).flat().map(line => line.from.timestamp), rows[1].adopted_flow_from_timestamps);
  fs.writeFileSync(path.join(output, 'scenario-result.json'), JSON.stringify({scenario: 'parallel', passed: true,
    scope: 'Two distinct UI requests outstanding across asynchronous boundaries; responses delivered in request order',
    rows, finalState, delivery_control: gate.audit}, null, 2));
  await page.screenshot({path: path.join(output, 'parallel.png'), fullPage: true});
}

module.exports = {runParallel};
