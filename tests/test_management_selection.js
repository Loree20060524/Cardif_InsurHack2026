const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function boot(returnedIds = ['event-9', 'event-2']) {
    const elements = new Map();
    const requests = [];
    const views = [];
    const messages = [];
    const document = {getElementById(id) {
        if(!elements.has(id)) elements.set(id, {
            innerHTML:'', textContent:'', value:'', disabled:false,
            classList:{remove(){},toggle(){}},
            setAttribute(){}, focus(){}, scrollIntoView(){},
            querySelectorAll(){return [];}, querySelector(){return {};},
        });
        return elements.get(id);
    }};
    const context = vm.createContext({
        document, URLSearchParams, URL, console:{error(){}},
        showView:view => views.push(view),
        toast:message => messages.push(message),
        fetch:async (url, options) => {
            requests.push({url, ...options});
            return {ok:true, json:async () => ({ok:true, summary:{
                headline:'選取摘要', summary:'只彙整所選資訊。',
                source_events:returnedIds.map(id => ({id, title:id, source:'官方來源'})),
            }})};
        },
    });
    for(const file of ['assets/js/core.js', 'assets/js/pagination.js', 'assets/js/management.js']) {
        vm.runInContext(fs.readFileSync(path.resolve(__dirname, '..', file), 'utf8'), context, {filename:file});
    }
    vm.runInContext(`state.events = Array.from({length:10}, (_, i) => ({
        id:'event-'+i, title:'資訊 '+i, source_key:'reg_news',
        published_at:'2026-10-02T00:00:00+08:00'
    }));`, context);
    return {context, elements, requests, views, messages};
}

test('summary request uses exactly the manually selected events, including one outside the old shortlist', async () => {
    const app = boot();
    vm.runInContext("state.managementSelection = new Set(['event-9', 'event-2']);", app.context);
    await vm.runInContext('generateManagementReport()', app.context);
    assert.equal(app.requests[0].method, 'POST');
    assert.deepEqual(JSON.parse(app.requests[0].body), {event_ids:['event-9', 'event-2']});
    assert.match(app.elements.get('reportBox').innerHTML, /本次納入資訊（2 筆）/);
    assert.match(app.elements.get('reportBox').innerHTML, /event-9/);
});

test('search preserves hidden selections and an empty selection disables generation', async () => {
    const app = boot();
    vm.runInContext("state.managementSelection.add('event-9'); state.managementQuery = '資訊 2'; renderManagementSelection();", app.context);
    assert.match(app.elements.get('managementSelectionCount').textContent, /已選 1 筆資訊 · 符合條件 1 筆/);
    assert.deepEqual([...vm.runInContext('selectedManagementEvents().map(event => event.id)', app.context)], ['event-9']);
    vm.runInContext('state.managementSelection.clear(); renderManagementSelection();', app.context);
    assert.equal(app.elements.get('reportBtn').disabled, true);
    await vm.runInContext('generateManagementReport()', app.context);
    assert.equal(app.requests.length, 0);
});

test('a report with a different source selection is rejected and the selection survives for retry', async () => {
    const app = boot(['event-1']);
    vm.runInContext("state.managementSelection.add('event-9');", app.context);
    await vm.runInContext('generateManagementReport()', app.context);
    assert.match(app.elements.get('reportBox').innerHTML, /資訊與所選項目不一致/);
    assert.equal(vm.runInContext("state.managementSelection.has('event-9')", app.context), true);
    assert.equal(app.elements.get('reportBtn').disabled, false);
});

test('adding a detail event preserves existing selections and reveals its page without generating a report', () => {
    const app = boot();
    vm.runInContext(`state.managementSelection.add('event-2');
        state.managementQuery = 'unmatched';
        state.managementType = '法規';
        state.pagination.management.size = 3;
        addToManagementSummary(state.events[9]);
        addToManagementSummary(state.events[9]);`, app.context);

    assert.deepEqual([...vm.runInContext('state.managementSelection', app.context)], ['event-2', 'event-9']);
    assert.equal(vm.runInContext('state.managementQuery', app.context), '');
    assert.equal(vm.runInContext('state.managementType', app.context), '全部');
    assert.equal(vm.runInContext('state.pagination.management.page', app.context), 4);
    assert.deepEqual(app.views, ['management', 'management']);
    assert.equal(app.requests.length, 0);
    assert.match(app.messages.at(-1), /已選 2 筆/);
});

test('adding a detail event cannot alter the selection during a report or history request', () => {
    for(const busy of ['state.managementReportLoading', 'state.history.loading']){
        const app = boot();
        vm.runInContext(`state.managementSelection.add('event-2');
            ${busy} = true;
            addToManagementSummary(state.events[9]);`, app.context);
        assert.deepEqual([...vm.runInContext('state.managementSelection', app.context)], ['event-2']);
        assert.equal(app.views.length, 0);
        assert.equal(app.requests.length, 0);
        assert.match(app.messages[0], /請稍候/);
    }
});

test('an event no longer in the loaded sources is not added to the management report', () => {
    const app = boot();
    vm.runInContext("addToManagementSummary({id:'removed-event'});", app.context);
    assert.equal(vm.runInContext('state.managementSelection.size', app.context), 0);
    assert.equal(app.views.length, 0);
    assert.equal(app.requests.length, 0);
    assert.match(app.messages[0], /已不在目前清單/);
});
