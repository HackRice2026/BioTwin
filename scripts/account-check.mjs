import {chromium} from '../frontend/node_modules/playwright-core/index.mjs';
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://localhost:8000');
  await page.getByRole('button',{name:'Connect your own story',exact:false}).click();
  await page.getByLabel('Your name',{exact:true}).fill('Browser Test');
  await page.getByLabel('Email',{exact:true}).fill(`test-${Date.now()}@biotwin.invalid`);
  await page.getByLabel('Password',{exact:true}).fill('biotwin-local-test-password');
  await page.getByLabel('I am 18 or older.',{exact:true}).check();
  await page.getByRole('button',{name:'Create my twin',exact:true}).click();
  await page.getByText('Personal workspace',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Connections',exact:true}).click();
  const [chooser]=await Promise.all([page.waitForEvent('filechooser'),page.getByRole('button',{name:'Import Garmin data',exact:true}).click()]);
  await chooser.setFiles('fixtures/golden/generated-recovery.fit');
  await page.getByText('Imported 37 measurements · 0 duplicates skipped.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Signals',exact:true}).click();
  await page.getByRole('heading',{name:'Heart rate',exact:true}).waitFor();
  await page.screenshot({path:'test-results/imported-signals.png',fullPage:true});
  await page.getByRole('button',{name:'Connections',exact:true}).click();
  await page.getByRole('button',{name:'Delete account',exact:true}).click();
  await page.getByRole('button',{name:'Delete permanently',exact:true}).click();
  await page.getByText('Account and data deleted.',{exact:true}).waitFor();
  if(errors.length)throw new Error(errors.join('\n'));
  console.log('Browser account creation, original FIT import, signals rendering and account deletion passed.');
}finally{await browser.close();}
