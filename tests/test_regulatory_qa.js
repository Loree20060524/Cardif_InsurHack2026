const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function boot(fetch){
    const elements = Object.fromEntries(['qaForm', 'qaQuestion', 'qaType', 'qaDateFrom', 'qaDateTo', 'qaSubmit', 'qaStatus', 'qaResult'].map(id => [id, {
        value:'', textContent:'', innerHTML:'', disabled:false, attributes:{},
        addEventListener(){}, focus(){}, setAttribute(name, value){this.attributes[name] = value;},
    }]));
    elements.qaType.value = '全部';
    const context = vm.createContext({document:{getElementById:id=>elements[id]}, fetch, URL});
    for(const file of ['core.js', 'regulatory-qa.js']) vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'assets', 'js', file), 'utf8'), context);
    vm.runInContext("state.view = 'qa';", context);
    return {elements, context, run:code=>vm.runInContext(code, context)};
}

function answer(){
    return {status:'answered', question:'投資內控', filters:{type:'全部', date_from:'', date_to:''},
        claims:[{text:'<img src=x onerror=alert(1)>', kind:'fact', citations:[{source_id:'S1', quote:'官方原文指出應保存投資決策與覆核紀錄。'}]}],
        sources:[{source_id:'S1', title:'官方投資管理規範', source:'金管會', date:'2026-10-02', date_label:'發布日期', url:'https://www.fsc.gov.tw/example?a=1&b=2'}],
        missing_information:[], scope:{documents:20, retrieved_documents:1, passages:1}, timing:{total_seconds:1.5}};
}

test('answers escape model content and display exact quoted evidence and safe official links', () => {
    const app = boot();
    app.context.fixture = answer();
    app.run('renderQAAnswer(fixture);');
    const html = app.elements.qaResult.innerHTML;
    assert.ok(!html.includes('<img'));
    assert.match(html, /&lt;img/);
    assert.match(html, /官方原文指出應保存投資決策與覆核紀錄/);
    assert.match(html, /rel="noopener noreferrer"/);
    assert.equal(app.run("qaOfficialLink({url:'javascript:alert(1)'})"), '');
    assert.equal(app.run("qaOfficialLink({url:'https://user:password@example.com'})"), '');
});

test('submission sends the question and date filters, prevents duplicate requests, and restores controls', async () => {
    let requests = 0, body, resolve;
    const pending = new Promise(done => {resolve = done;});
    const app = boot(async (_url, options) => {requests++; body = JSON.parse(options.body); return pending;});
    Object.assign(app.elements.qaQuestion, {value:'投資內控'});
    app.elements.qaDateFrom.value = '2026-10-01';
    const operation = app.run('submitRegulatoryQuestion({preventDefault(){}})');
    await app.run('submitRegulatoryQuestion({preventDefault(){}})');
    assert.equal(requests, 1);
    assert.equal(app.elements.qaSubmit.disabled, true);
    assert.deepEqual(body, {question:'投資內控', filters:{type:'全部', date_from:'2026-10-01', date_to:''}});
    resolve({ok:true, json:async()=>({ok:true, answer:answer()})});
    await operation;
    assert.equal(app.elements.qaSubmit.disabled, false);
    assert.equal(app.elements.qaResult.attributes['aria-busy'], 'false');
    assert.match(app.elements.qaStatus.textContent, /回答完成/);
});

test('failed requests preserve input and permit retry; invalid dates are rejected before sending', async () => {
    let requests = 0;
    const app = boot(async () => {requests++; return {ok:false, json:async()=>({ok:false, error:'模型尚未啟動'})};});
    app.elements.qaQuestion.value = '投資內控';
    await app.run('submitRegulatoryQuestion({preventDefault(){}})');
    assert.equal(app.elements.qaQuestion.value, '投資內控');
    assert.equal(app.elements.qaSubmit.disabled, false);
    assert.equal(app.elements.qaStatus.textContent, '模型尚未啟動');
    app.elements.qaDateFrom.value = '2026-10-02';
    app.elements.qaDateTo.value = '2026-10-01';
    await app.run('submitRegulatoryQuestion({preventDefault(){}})');
    assert.equal(requests, 1);
    assert.match(app.elements.qaStatus.textContent, /開始日期/);
});
