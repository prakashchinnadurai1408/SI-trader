const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const {mkdtempSync, rmSync, mkdirSync} = require('node:fs');
const {tmpdir} = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const folder = mkdtempSync(path.join(tmpdir(), 'si-browser-'));
  const server = spawn(process.env.PYTHON || 'python', ['-B', '-u', '-m', 'tests.browser_server'], {
    env: {...process.env, SI_TRADER_MODE:'local', SI_TRADER_LLM_HOME:folder, SI_TRADER_STRATEGY_BUNDLE:''}, stdio:['ignore','pipe','pipe']
  });
  let browser; let logs = '';
  server.stderr.on('data', data => { logs += data.toString(); });
  try {
    const urls = await new Promise((resolve, reject) => {
      let out=''; const timer=setTimeout(()=>reject(Error('Server startup timed out: '+logs)),60000);
      server.once('exit', code=>{clearTimeout(timer);reject(Error('Server exited '+code+': '+logs));});
      server.stdout.on('data', data=>{out+=data.toString(); if(out.includes('\n')){clearTimeout(timer);resolve(JSON.parse(out.split('\n')[0]));}});
    });
    browser = await chromium.launch({headless:true, ...(process.env.SI_TEST_BROWSER ? {executablePath:process.env.SI_TEST_BROWSER} : {})});
    const context = await browser.newContext({ignoreHTTPSErrors:true});
    const page = await context.newPage(); const errors=[]; page.on('pageerror', e=>errors.push(e.message));
    page.setDefaultTimeout(15000);
    await page.route('**/api/models', route=>route.fulfill({json:{models:[],profiles:[],providers:[],error:''}}));
    await page.goto(urls.local);
    await page.locator('#email').fill('trader@example.com'); await page.locator('#password').fill('WeeklyDemo123!');
    await page.locator('#signin button').click(); await page.locator('#code').fill('123456'); await page.locator('#mfa button').click();
    await page.getByRole('button',{name:'Open paper dashboard',exact:true}).click();
    await page.getByRole('button',{name:'Monthly',exact:true}).click();
    assert(await page.locator('[name=includeAI]').isEnabled());
    await page.locator('#monthly-start').fill('2099-01');await page.locator('#monthly-end').fill('2099-02');
    let requests=0;page.on('request',r=>{if(r.url().endsWith('/api/monthly-comparison'))requests++;});
    await page.getByRole('button',{name:'Check data readiness',exact:true}).click();
    assert.match(await page.locator('#monthly-date-validation').innerText(),/incomplete/);assert.equal(requests,0);
    await page.locator('#monthly-start').fill('2019-01');await page.locator('#monthly-end').fill('2023-12');
    await page.getByRole('button',{name:'Check data readiness',exact:true}).click();
    await page.getByText('Research bundle needs attention.',{exact:true}).waitFor();
    await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=390));
    await page.goto(urls.hosted);
    await page.getByText('Hosted workspace · operator sign-in',{exact:true}).waitFor();
    assert(!await page.getByText('Local demo.',{exact:false}).count());
    await page.locator('#email').fill('operator@example.com');await page.locator('#password').fill('WrongPassword123!');await page.locator('#signin button').click();
    await page.getByText('Invalid sign-in details.',{exact:true}).waitFor();
    await page.locator('#password').fill('FixturePassword123!');await page.locator('#signin button').click();
    await page.getByRole('button',{name:'Open paper dashboard',exact:true}).click();
    await page.getByRole('button',{name:'Sign out',exact:true}).click();
    await page.locator('#signin').waitFor();
    assert.deepEqual(errors,[]);
    mkdirSync('test-results',{recursive:true});
    await page.screenshot({path:'test-results/hosted-signin.png',fullPage:true});
    console.log('Browser PASS: local sign-in, monthly validation/readiness, mobile layout, HTTPS hosted sign-in/error/logout.');
  } finally {
    if(browser) await browser.close();
    server.kill();
    await new Promise(resolve => {if(server.exitCode!==null)resolve();else server.once('exit',resolve);});
    rmSync(folder,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
