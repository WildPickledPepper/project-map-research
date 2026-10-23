// Exercise the real browser and server on a public, copied Insight trace sample.
const fs = require('node:fs');
const path = require('node:path');
const [source, output, url, data] = process.argv.slice(2);
const { chromium, expect } = require(path.join(source, 'e2e/node_modules/@playwright/test'));

async function main() {
  const browser = await chromium.launch({headless: true});
  const context = await browser.newContext({viewport: {width: 1600, height: 1000}, locale: 'en-US'});
  await context.tracing.start({screenshots: true, snapshots: true, sources: true});
  const page = await context.newPage();
  const events = [], errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('websocket', ws => {
    for (const direction of ['framesent', 'framereceived']) {
      ws.on(direction, frame => {
        const raw = typeof frame.payload === 'string' ? frame.payload : frame.payload.toString();
        let message;
        try { message = JSON.parse(raw); } catch { message = {unparsed: raw}; }
        events.push({direction, socket: ws.url(), at: new Date().toISOString(), message});
      });
    }
  });
  let failure = null;
  try {
    await page.goto(url);
    await page.locator('.btn-import').waitFor({state: 'visible', timeout: 30000});
    await page.locator('.btn-import').click();
    const input = page.getByTestId('filePathInput');
    await input.fill(data);
    await input.press('Enter');
    const confirm = page.getByRole('button', {name: 'Confirm', exact: true});
    await expect(confirm).toBeEnabled({timeout: 15000});
    await confirm.click();
    await expect.poll(() => events.some(e => e.direction === 'framereceived' && e.message.event === 'allPagesSuccess'),
      {timeout: 90000, message: 'Real server must complete imported trace parsing'}).toBeTruthy();
    const timeline = page.frameLocator('#Timeline');
    await timeline.locator('#main-container').waitFor({state: 'visible', timeout: 30000});
    await expect(timeline.locator('#unitWrapperScroller')).toContainText(/Ascend|Python|Process|Thread|CPU|NPU/i, {timeout: 30000});
    await page.screenshot({path: path.join(output, 'loaded.png'), fullPage: true});
  } catch (error) {
    failure = String(error.stack || error);
    await page.screenshot({path: path.join(output, 'failed.png'), fullPage: true}).catch(() => {});
  } finally {
    fs.writeFileSync(path.join(output, 'browser-events.json'), JSON.stringify({events, errors}, null, 2));
    fs.writeFileSync(path.join(output, 'page-text.txt'), await page.locator('body').innerText().catch(() => 'unavailable'));
    fs.writeFileSync(path.join(output, 'boot-result.json'), JSON.stringify({
      evidence_kind: 'real_Insight_browser_import', passed: !failure, failure,
      browser: browser.version(), event_count: events.length, page_errors: errors,
      received_events: [...new Set(events.filter(e => e.direction === 'framereceived').map(e => e.message.event).filter(Boolean))],
      observed_commands: [...new Set(events.map(e => e.message.command).filter(Boolean))],
      scope: 'R01 preparation: UI import and timeline availability; unit/flows state assertions remain separate'
    }, null, 2));
    try {
      await context.tracing.stop({path: path.join(output, 'playwright-trace.zip')});
    } finally {
      await browser.close();
    }
  }
  if (failure) throw new Error(failure);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
