const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness(fetch){
    const body = {innerHTML:'', querySelectorAll(){return [];}, querySelector(){return null;}};
    const context = vm.createContext({URL, Map, Set, console, fetch,
        state:{selected:'a', ai:{enabled:true}, aiLoading:new Set()},
        $:id => id === 'lawComparisonBody' ? body : null,
        esc:value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c])),
        ensureAIAnalysis(){},
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../assets/js/law-comparison.js'), 'utf8'), context);
    return {context, body, run:code => vm.runInContext(code, context)};
}

test('comparison is collapsed and draft/attachment events have no comparison panel', () => {
    const h = harness();
    const markup = h.run('renderLawComparisonSection({id:"a", source_key:"insurance_law", title:"保險法"})');
    assert.match(markup, /修正前後對照/);
    assert.doesNotMatch(markup, /class="block law-comparison" open/);
    assert.equal(h.run('renderLawComparisonSection({id:"a", source_key:"insurance_law", title:"保險法修正草案"})'), '');
    assert.equal(h.run('renderLawComparisonSection({id:"a", source_key:"insurance_law", title:"修正條文.pdf"})'), '');
});

test('source and changed text cannot inject markup or links', () => {
    const h = harness();
    assert.equal(h.run('lawSourceLink("javascript:alert(1)", "原文")'), '');
    assert.equal(h.run('lawSourceLink("https://law.fsc.gov.tw.evil.example/", "原文")'), '');
    const markup = h.run('comparisonText([{text:"<script>alert(1)</script>", changed:true}], "text", "after")');
    assert.match(markup, /<ins>&lt;script&gt;/);
    assert.doesNotMatch(markup, /<script>/);
});

test('pending comparison requests are shared and responses cannot overwrite another event', async () => {
    let resolve, calls=0;
    const pending = new Promise(done => resolve=done);
    const h = harness(() => { calls++; return pending; });
    const first = h.run('loadLawComparison({id:"a"})');
    await h.run('loadLawComparison({id:"a"})');
    assert.equal(calls, 1);
    h.run('state.selected="b"');
    h.body.innerHTML='other event';
    resolve({ok:true, json:async () => ({ok:true, comparisons:[]})});
    await first;
    assert.equal(h.body.innerHTML, 'other event');
    assert.equal(h.run('lawComparisonState.get("a").data.length'), 0);
});

test('network failures preserve retry and a retry can succeed', async () => {
    let calls=0;
    const h = harness(async () => {
        calls++;
        if(calls === 1) throw new Error('offline');
        return {ok:true, json:async () => ({ok:true, comparisons:[]})};
    });
    await h.run('loadLawComparison({id:"a"})');
    assert.match(h.body.innerHTML, /重新讀取/);
    await h.run('loadLawComparison({id:"a"}, true)');
    assert.equal(calls, 2);
    assert.equal(h.run('lawComparisonState.get("a").error'), '');
});
