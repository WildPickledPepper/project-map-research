const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {expectedFlow, selectFlowSlice} = require('./flow_scenario.cjs');

async function waitProject(page, project, events, after, expect) {
  const timeline = page.frames().find(frame => frame.name() === 'Timeline');
  await expect.poll(() => events.slice(after).some(event => event.direction === 'framereceived' &&
    event.message.event === 'allPagesSuccess'), {timeout: 30000}).toBe(true);
  await expect.poll(() => page.evaluate(() => globalThis.__projectMapProbe.readState()?.project),
    {timeout: 15000}).toBe(project);
  await expect.poll(() => timeline.evaluate(() => globalThis.__projectMapProbe.readState()?.project),
    {timeout: 15000}).toBe(project);
  await expect(page.frameLocator('#Timeline').locator('#unitWrapperScroller')).toContainText(/Python|CPU|NPU/, {timeout: 15000});
}

async function importProject({page, project, events, expect}) {
  const after = events.length;
  await page.locator('.btn-import').click();
  const input = page.getByTestId('filePathInput');
  await input.fill(project); await input.press('Enter');
  const confirm = page.getByRole('button', {name: 'Confirm', exact: true});
  await expect(confirm).toBeEnabled({timeout: 15000}); await confirm.click();
  await waitProject(page, project, events, after, expect);
}

async function switchProject({page, project, events, expect}) {
  const after = events.length;
  const row = page.getByRole('tree').locator('.leaf-node .content-text').filter({hasText: project});
  await expect(row).toHaveCount(1);
  await row.click();
  await waitProject(page, project, events, after, expect);
}

async function runLate({page, events, source, output, data, gate}) {
  const {expect} = require(path.join(source, 'e2e/node_modules/@playwright/test'));
  const projectA = data;
  const projectB = path.join(output, 'data/project-B/trace_view.json');
  const expected = expectedFlow(data);
  fs.writeFileSync(path.join(output, 'expected-flow.json'), JSON.stringify(expected, null, 2));
  await importProject({page, project: projectB, events, expect});
  await switchProject({page, project: projectA, events, expect});
  const target = await selectFlowSlice({page, expected, expect});
  await target.frame.evaluate(() => globalThis.__projectMapProbe.setAction('late-A-click'));
  gate.arm('unit/flows');
  await target.canvas.click({position: target.position});
  await expect.poll(() => gate.held.length, {timeout: 20000}).toBe(1);
  const held = gate.held[0];
  assert.equal(held.request.projectName, projectA);
  assert.equal(held.message.result, true);
  assert.equal(held.message.body.unitAllFlows.flatMap(group => group.flows).length, expected.flows.length);
  assert(!events.some(event => event.direction === 'framereceived' && event.message.command === 'unit/flows'),
    'A response remains held outside the browser');
  await page.evaluate(() => globalThis.__projectMapProbe.setAction('switch-to-B'));
  await switchProject({page, project: projectB, events, expect});
  const before = await target.frame.evaluate(() => globalThis.__projectMapProbe.readState());
  assert.equal(before.project, projectB);
  assert.deepEqual(before.singleLinkLine, {});
  assert.equal(before.selectedData, undefined);
  gate.mark('B_state_verified_before_release', {project: projectB});
  gate.releaseAll();
  await expect.poll(() => page.evaluate(requestId => globalThis.__projectMapProbe.events.some(event =>
    event.requestId === requestId && ['response.discarded', 'response.delivered'].includes(event.stage)), held.request.id),
    {timeout: 15000}).toBe(true);
  // Allow the response's Promise/postMessage/render work to settle before reading final live state.
  await target.frame.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const after = await target.frame.evaluate(() => globalThis.__projectMapProbe.readState());
  const decisions = await page.evaluate(requestId => globalThis.__projectMapProbe.events.filter(event =>
    event.requestId === requestId && event.command === 'unit/flows'), held.request.id);
  const result = {scenario: 'late', passed: false, projectA, projectB, request_id: held.request.id,
    trace_id: held.request.params.__projectMapTrace, before, after, decisions, gate_audit: gate.audit,
    invariant: 'After project B is active, delivery of A must leave B selection and flow state unchanged'};
  fs.writeFileSync(path.join(output, 'scenario-result.json'), JSON.stringify(result, null, 2));
  assert.equal(after.project, projectB, 'B must remain active');
  assert.deepEqual(after.singleLinkLine, before.singleLinkLine, 'Late A response must not change B flow lines');
  assert.deepEqual(after.selectedData, before.selectedData, 'Late A response must not change B selection');
  assert.equal(after.drawLineMode, before.drawLineMode, 'Late A response must not change B drawing mode');
  assert(decisions.some(event => event.stage === 'response.discarded'), 'Real project guard discards A response');
  assert(!decisions.some(event => event.stage === 'response.delivered'), 'A response is not handed to the API callback');
  const applied = await target.frame.evaluate(traceId => globalThis.__projectMapProbe.events.filter(event =>
    event.trace_id === traceId && ['api.resolved', 'state.applied'].includes(event.stage)), result.trace_id);
  assert.equal(applied.length, 0, 'Discarded A response does not reach API/state adoption');
  result.passed = true;
  fs.writeFileSync(path.join(output, 'scenario-result.json'), JSON.stringify(result, null, 2));
  await page.screenshot({path: path.join(output, 'late-response.png'), fullPage: true});
}

module.exports = {runLate, importProject, switchProject};
