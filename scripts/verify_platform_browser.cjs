/* Browser smoke checks with saved public data and controlled failure responses.
 * Set NODE_PATH to a Playwright installation and REGINTEL_VERIFY_PYTHON to Python.
 * No production cache is changed; the isolated HTTP server is stopped on exit.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const playwrightPath = require.resolve('playwright', {paths:[
    __dirname, path.resolve(path.dirname(process.execPath),'..'),
]});
const {chromium} = require(playwrightPath);

const root = path.resolve(__dirname, '..');
const output = path.join(root, 'tmp', 'verification-2026-10-22');
const port = Number(process.env.REGINTEL_VERIFY_PORT || 8183);
const base = `http://127.0.0.1:${port}`;
const findings = [];
const errors = [];
let browser;
fs.mkdirSync(output, {recursive:true});

const serverCode = String.raw`
import json
import sys
from pathlib import Path
from unittest.mock import patch
from regintel import web

snapshot = json.loads(Path('regintel_cache_v10.json').read_text(encoding='utf-8'))
snapshot['ai'] = {**snapshot.get('ai', {}), 'enabled': False}
snapshot['manual_refresh_limited'] = False
snapshot['manual_retry_after_seconds'] = 0
with patch.object(web, 'refresh_data', return_value=snapshot):
    server = web.RegIntelHTTPServer(('127.0.0.1', int(sys.argv[1])), web.Handler)
    print('verification server ready', flush=True)
    server.serve_forever()
`;
const bundledPython = path.resolve(path.dirname(process.execPath),'..','..','python','python.exe');
const server = spawn(process.env.REGINTEL_VERIFY_PYTHON || (fs.existsSync(bundledPython) ? bundledPython : 'python'),
    ['-X','utf8','-u','-c',serverCode,String(port)], {cwd:root, windowsHide:true});
let serverLog = '';
server.stdout.on('data', data => {serverLog += data;});
server.stderr.on('data', data => {serverLog += data;});

async function ready(){
    for(let attempt=0;attempt<60;attempt++){
        if(server.exitCode !== null) throw new Error(`Verification server exited: ${serverLog}`);
        try{if((await fetch(`${base}/api/health`)).ok) return;}catch(_){ /* Wait for our own server. */ }
        await new Promise(resolve=>setTimeout(resolve,100));
    }
    throw new Error(`Verification server did not start: ${serverLog}`);
}

async function page(){
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    page.on('pageerror', error=>errors.push(error.message));
    return page;
}

async function check(name, run){
    const started=Date.now();
    console.log(`CHECK ${name}`);
    try{
        const details=await run();
        findings.push({name,passed:true,seconds:(Date.now()-started)/1000,...details});
        console.log(`PASS ${name}`);
    }catch(error){
        findings.push({name,passed:false,error:error.message});
        const tabs=browser.contexts().flatMap(context=>context.pages());
        if(tabs.length) await tabs.at(-1).screenshot({path:path.join(output,'failed-check.png'),timeout:5000}).catch(()=>{});
        throw error;
    }
}

async function main(){
    await ready();
    browser=await chromium.launch({channel:'chrome',headless:true});

    await check('initial API failure ends the loading state and permits retry',async()=>{
        const tab=await page();
        await tab.route('**/api/events',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
        await tab.goto(base);
        await tab.waitForFunction(()=>document.getElementById('connectionNotice').classList.contains('error'));
        const detail=await tab.locator('#eventDetail').innerText();
        assert.doesNotMatch(detail,/正在取得|載入中|讀取中/,'A failed initial load must not keep displaying a loading message');
        assert.match(detail,/無法取得|無法載入|重新/);
        assert.equal(await tab.locator('#refreshBtn').isEnabled(),true);
        await tab.screenshot({path:path.join(output,'failure-state.png')});
        await tab.unroute('**/api/events');
        await tab.locator('#retryLoadEvents').click();
        await tab.waitForSelector('#eventList .d-row');
        await tab.close();
    });

    await check('saved public data loads and search, paging, filters, navigation and source modal work',async()=>{
        const tab=await page();
        await tab.goto(base);
        await tab.waitForSelector('#eventList .d-row');
        const count=await tab.evaluate(()=>state.events.length);
        assert.ok(count>100);
        assert.equal(await tab.locator('#eventList .d-row').count(),25);
        await tab.locator('#eventPagination [data-page-next]').click();
        assert.match(await tab.locator('#eventPagination').innerText(),/第 26/);
        await tab.locator('#search').fill('絕對不存在的監理搜尋詞');
        assert.equal(await tab.locator('#eventList .d-row').count(),0);
        assert.match(await tab.locator('#eventDetail').innerText(),/篩選/);
        await tab.locator('#search').fill('');
        await tab.locator('#advancedFilterButton').click();
        await tab.locator('#typeFilterOptions label').filter({hasText:'裁罰'}).click();
        assert.equal(await tab.evaluate(()=>ledgerEvents().every(event=>sourceType(event)==='裁罰')),true);
        await tab.locator('#clearAdvancedFilters').click();
        await tab.locator('#applyAdvancedFilters').click();
        await tab.locator('#sourcesBtn').click();
        assert.equal(await tab.locator('#sourcesModal').isVisible(),true);
        assert.ok(await tab.locator('#sourceStatusList .source-group').count()>0);
        await tab.locator('#closeSources').click();
        assert.equal(await tab.locator('.shell').evaluate(element=>element.inert),false);
        await tab.locator('.d-header button[data-view="management"]').click();
        await tab.locator('#priorityList input[data-management-event]').first().check();
        assert.match(await tab.locator('#managementSelectionCount').innerText(),/已選 1/);
        await tab.locator('.d-header button[data-view="qa"]').click();
        assert.equal(await tab.locator('#qaForm').isVisible(),true);
        await tab.locator('.d-header button[data-view="intel"]').click();
        await tab.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
        await tab.setViewportSize({width:390,height:844});
        await tab.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
        const overflow=await tab.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);
        assert.equal(overflow,false,'The mobile page should fit the viewport');
        await tab.close();
        return {events:count};
    });

    await check('AI completion updates active filters, counts and the selected detail',async()=>{
        const tab=await page();
        const pending={analysis_mode:'規則備援',risk_level:'中',importance:'一般',responsible_department:'法令遵循'};
        const completed={...pending,analysis_mode:'AI 深度分析',risk_level:'高',responsible_department:'財務／會計',
            summary:'測試用已核對分析。',support_review:{version:'browser-test',requested:0,supported:0,withheld:0,unverified:0,sources:[],checks:[]}};
        await tab.route('**/api/events',route=>route.fulfill({json:{events:[
            {id:'analysis-a',title:'分析前的事件',source_key:'reg_news',published_at:'2026-10-22',analysis:pending},
            {id:'analysis-b',title:'保留在篩選中的事件',source_key:'reg_news',published_at:'2026-10-21',analysis:pending},
        ],sources:{},ai:{enabled:true},history:{sources:{}}}}));
        let release;
        const gate=new Promise(resolve=>{release=resolve;});
        await tab.route('**/api/analyze?**',async route=>{
            await gate;
            const id=new URL(route.request().url()).searchParams.get('id');
            await route.fulfill({json:{ai_used:true,analysis:id==='analysis-a'?completed:{...pending,analysis_mode:'AI 深度分析',support_review:completed.support_review}}});
        });
        await tab.goto(base);
        await tab.waitForSelector('#eventList .d-row');
        await tab.locator('#advancedFilterButton').click();
        await tab.locator('#riskFilterOptions label').filter({hasText:'中'}).click();
        assert.equal(await tab.locator('#eventList .d-row').count(),2);
        release();
        await tab.waitForFunction(()=>state.events.find(event=>event.id==='analysis-a').analysis.risk_level==='高');
        await tab.waitForTimeout(100);
        assert.equal(await tab.locator('#eventList .d-row').count(),1,'An event whose updated risk no longer matches must leave the filtered list');
        assert.match(await tab.locator('#ledgerResultCount').innerText(),/1 筆/);
        assert.equal(await tab.evaluate(()=>state.selected),'analysis-b');
        await tab.close();
    });

    await check('management selection changes retain the old scope until the latest report completes',async()=>{
        const tab=await page();
        const requests=[];
        let release;
        const gate=new Promise(resolve=>{release=resolve;});
        await tab.route('**/api/management-summary',async route=>{
            const ids=route.request().postDataJSON().event_ids;
            requests.push(ids);
            if(requests.length===2) await gate;
            await route.fulfill({json:{ok:true,summary:{headline:'瀏覽器測試摘要',summary:'彙整所選來源的測試內容。',
                priority_events:[{title:'優先事項',reason:'測試用途'}],priority_actions:['確認適用條件'],
                source_events:ids.map(id=>({id,title:id,source:'測試來源'})),
            }}});
        });
        await tab.goto(base);
        await tab.waitForSelector('#eventList .d-row');
        await tab.locator('.d-header button[data-view="management"]').click();
        const inputs=tab.locator('#priorityList input[data-management-event]');
        await inputs.nth(0).check();
        await tab.locator('#reportBtn').click();
        await tab.waitForFunction(()=>document.getElementById('reportBox').innerText.includes('本次彙整 1 筆資訊'));
        assert.match(await tab.locator('#reportBox').innerText(),/AI 產生/);
        const pending=tab.waitForRequest('**/api/management-summary');
        await inputs.nth(1).check();
        assert.match(await tab.locator('#managementReportStatus').innerText(),/選取已變更/);
        assert.match(await tab.locator('#reportBox').innerText(),/本次彙整 1 筆資訊/);
        assert.equal(await tab.locator('#reportBox').getAttribute('data-selection-match'),'false');
        await pending;
        release();
        await tab.waitForFunction(()=>document.getElementById('reportBox').innerText.includes('本次彙整 2 筆資訊'));
        assert.equal(requests[1].length,2);
        assert.equal(await tab.locator('#reportBox').getAttribute('data-selection-match'),'true');
        assert.equal(await tab.locator('#managementReportStatus').isVisible(),false);
        await tab.locator('#clearManagementSelection').click();
        assert.match(await tab.locator('#reportBox').innerText(),/尚未選取資訊/);
        assert.equal(await tab.locator('#reportBtn').isEnabled(),false);
        await tab.close();
    });

    if(process.argv.includes('--live-qa')) await check('the unified question flow reaches local Ollama and renders a source-backed answer',async()=>{
        const tab=await page();
        await tab.goto(base);
        await tab.waitForSelector('#eventList .d-row');
        await tab.locator('.d-header button[data-view="qa"]').click();
        await tab.locator('#qaQuestion').fill('保險經紀人管理規則規範哪些事項？');
        const pending=tab.waitForResponse(response=>response.url().endsWith('/api/regulatory-qa'),{timeout:180000});
        await tab.locator('#qaSubmit').click();
        const response=await pending;
        const payload=await response.json();
        fs.writeFileSync(path.join(output,'live-qa.json'),JSON.stringify(payload,null,2));
        assert.equal(response.status(),200);
        assert.equal(payload.ok,true);
        assert.equal(payload.answer.status,'answered');
        assert.ok(payload.answer.claims.length>0);
        assert.ok(payload.answer.sources.length>0);
        await tab.waitForFunction(()=>document.getElementById('qaResult').getAttribute('aria-busy')==='false');
        assert.match(await tab.locator('#qaResult').innerText(),/法規依據|其他官方資料/);
        await tab.screenshot({path:path.join(output,'live-qa.png'),fullPage:true});
        await tab.locator('#qaNewQuestion').click();
        assert.equal(await tab.locator('#qaQuestion').inputValue(),'');
        assert.equal(await tab.locator('#qaConversation').isVisible(),false);
        await tab.close();
        return {status:payload.answer.status,claims:payload.answer.claims.length,sources:payload.answer.sources.length,
            timing:payload.answer.timing};
    });

    assert.deepEqual(errors,[],'The browser should not report unhandled JavaScript errors');
}

main().catch(error=>{console.error(error.message);process.exitCode=1;}).finally(async()=>{
    if(browser) await browser.close();
    server.kill();
    fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify({findings,errors},null,2));
    fs.writeFileSync(path.join(output,'server.log'),serverLog);
});
