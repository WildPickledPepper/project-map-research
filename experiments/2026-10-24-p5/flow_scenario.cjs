// Scenario expectations are derived from the public input trace, separately from capture.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

function ns(value) {
  const [whole, fraction = ''] = String(value).split('.');
  return BigInt(whole) * 1000n + BigInt((fraction + '000').slice(0, 3));
}

function expectedFlow(data) {
  const input = JSON.parse(fs.readFileSync(data, 'utf8'));
  const events = Array.isArray(input) ? input : input.traceEvents;
  const selected = events.filter(e => e.ph === 'X' && e.name === 'Enqueue')
    .sort((a, b) => ns(a.ts) < ns(b.ts) ? -1 : 1)[0];
  assert(selected, 'Public fixture must contain an Enqueue slice');
  const starts = events.filter(e => e.ph === 's' && e.pid === selected.pid && e.tid === selected.tid &&
    ns(e.ts) >= ns(selected.ts) && ns(e.ts) < ns(selected.ts) + ns(selected.dur));
  assert(starts.length > 0, 'Independent input must contain a flow beginning in the selected slice');
  return {
    selection: {name: selected.name, pid: String(selected.pid), tid: String(selected.tid),
      start_ns: ns(selected.ts).toString(), duration_ns: ns(selected.dur).toString()},
    flows: starts.map(start => {
      const finish = events.find(e => e.ph === 'f' && String(e.id) === String(start.id) && e.cat === start.cat);
      assert(finish, 'Expected paired flow endpoint in input');
      return {id: String(start.id), category: start.cat,
        from: {pid: String(start.pid), tid: String(start.tid), timestamp_ns: ns(start.ts).toString()},
        to: {pid: String(finish.pid), tid: String(finish.tid), timestamp_ns: ns(finish.ts).toString()}};
    })
  };
}

async function selectFlowSlice({page, expected, expect}) {
  const timeline = page.frameLocator('#Timeline');
  const frame = page.frames().find(f => f.name() === 'Timeline');
  assert(frame, 'Timeline frame exists');
  await timeline.getByTestId('tool-search').click();
  const input = timeline.locator('.insight-category-search-overlay').getByPlaceholder('Please enter').first();
  await input.fill(expected.selection.name);
  await input.press('Enter');
  await expect.poll(() => frame.evaluate(() => globalThis.__projectMapReadSession?.()?.selectedData?.name),
    {timeout: 20000}).toBe(expected.selection.name);
  await expect.poll(() => frame.evaluate(() => globalThis.__projectMapReadSession?.()?.selectedDataUnit?.isTraceLoading),
    {timeout: 20000}).toBe(false);
  await timeline.getByTestId('tool-search').click();
  const lane = timeline.locator('.unit').filter({has: timeline.locator('.chart-selected')});
  await expect(lane).toHaveCount(1);
  if (await frame.evaluate(() => globalThis.__projectMapReadSession().selectedDataUnit.chart.config.isCollapse)) {
    await lane.getByTestId('expand-btn').click();
  }
  await expect.poll(() => frame.evaluate(() => globalThis.__projectMapReadSession().selectedDataUnit.chart.config.isCollapse),
    {timeout: 10000}).toBe(false);
  await expect.poll(() => frame.evaluate(() => globalThis.__projectMapReadSession().selectedDataUnit.isTraceLoading),
    {timeout: 20000}).toBe(false);
  const geometry = await frame.evaluate(() => {
    const session = globalThis.__projectMapReadSession();
    return {selected: session.selectedData, range: session.domainRange, timeOrigin: session.startTime,
      config: session.selectedDataUnit.chart.config};
  });
  assert.equal(String(geometry.selected.processId), expected.selection.pid);
  assert.equal(String(geometry.selected.threadId), expected.selection.tid);
  assert.equal(BigInt(geometry.timeOrigin) + BigInt(geometry.selected.startTime), BigInt(expected.selection.start_ns));
  assert.equal(BigInt(geometry.selected.duration), BigInt(expected.selection.duration_ns));
  const canvas = lane.locator('canvas.drawCanvas').first();
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  assert(box);
  assert.equal(geometry.config.isCollapse, false);
  const x = box.width * (geometry.selected.startTime + geometry.selected.duration / 2 - geometry.range.domainStart) /
    (geometry.range.domainEnd - geometry.range.domainStart);
  const y = (geometry.selected.depth + 0.5) * geometry.config.rowHeight;
  assert(x > 0 && x < box.width && y > 0 && y < box.height, 'Target slice lies inside visible canvas');
  return {frame, canvas, position: {x, y}, geometry};
}

async function runNormal({page, events, source, output, data}) {
  const {expect} = require(path.join(source, 'e2e/node_modules/@playwright/test'));
  const expected = expectedFlow(data);
  fs.writeFileSync(path.join(output, 'expected-flow.json'), JSON.stringify(expected, null, 2));
  const target = await selectFlowSlice({page, expected, expect});
  fs.writeFileSync(path.join(output, 'selected-geometry.json'), JSON.stringify(target.geometry, null, 2));
  await target.frame.evaluate(() => globalThis.__projectMapProbe.setAction('normal-click'));
  const after = events.length;
  await target.canvas.click({position: target.position});
  await expect.poll(() => target.frame.evaluate(() => globalThis.__projectMapProbe.events.filter(e =>
    e.stage === 'state.applied' && e.action === 'normal-click').length), {timeout: 20000}).toBeGreaterThan(0);
  const requests = events.slice(after).filter(e => e.direction === 'framesent' && e.message.command === 'unit/flows');
  assert(requests.length > 0, 'Actual canvas click sent unit/flows');
  const request = requests[0].message;
  const response = events.find(e => e.direction === 'framereceived' && e.message.requestId === request.id &&
    e.message.command === request.command)?.message;
  assert(response?.result, 'Server accepted traced request');
  const state = await target.frame.evaluate(() => globalThis.__projectMapProbe.readState());
  const actualFlows = response.body.unitAllFlows.flatMap(group => group.flows.map(flow => ({...flow, group: group.cat})));
  assert.equal(actualFlows.length, expected.flows.length, 'Returned flow count matches the selected public input slice');
  for (const expectedItem of expected.flows) {
    // TextTraceDatabase::AssembleUnitFlowsBody does not populate UnitSingleFlow.id.
    // Match the independent input's category and both endpoint identities/times.
    const actual = actualFlows.find(flow => flow.group === expectedItem.category && ['from', 'to'].every(side =>
      String(flow[side].pid) === expectedItem[side].pid && String(flow[side].tid) === expectedItem[side].tid &&
      BigInt(target.geometry.timeOrigin) + BigInt(flow[side].timestamp) === BigInt(expectedItem[side].timestamp_ns)));
    assert(actual, 'Expected input flow must be returned: ' + expectedItem.id);
    assert.equal(actual.group, expectedItem.category);
    for (const side of ['from', 'to']) {
      assert.equal(String(actual[side].pid), expectedItem[side].pid);
      assert.equal(String(actual[side].tid), expectedItem[side].tid);
      assert.equal(BigInt(target.geometry.timeOrigin) + BigInt(actual[side].timestamp), BigInt(expectedItem[side].timestamp_ns));
    }
  }
  assert.equal(state.drawLineMode, 'single');
  assert.equal(state.selectedData.id, request.params.id);
  assert.equal(state.selectedData.cardId, request.params.rankId);
  const finalLines = Object.values(state.singleLinkLine).flat();
  assert.equal(finalLines.length, actualFlows.length);
  for (const actual of actualFlows) {
    assert(finalLines.some(line => line.category === actual.cat && line.cardId === request.params.rankId &&
      line.from.id === actual.from.id && line.to.id === actual.to.id &&
      line.from.timestamp === actual.from.timestamp && line.to.timestamp === actual.to.timestamp),
      'Final state must contain each returned flow for this rank');
  }
  await page.screenshot({path: path.join(output, 'flow.png'), fullPage: true});
  fs.writeFileSync(path.join(output, 'scenario-result.json'), JSON.stringify({scenario: 'normal', passed: true,
    request_id: request.id, trace_id: request.params.__projectMapTrace, project: request.projectName,
    input_expected: expected, returned_flow_count: actualFlows.length, final_line_count: finalLines.length,
    state, assertion_source: 'public input events plus independent live frontend state'}, null, 2));
}

module.exports = {expectedFlow, selectFlowSlice, runNormal};
