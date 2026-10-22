const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function boot(returnedIds = ['event-9', 'event-2'], options = {}) {
    const elements = new Map();
    const requests = [];
    const views = [];
    const messages = [];
    const timers = new Map();
    let timerId = 0;
    let scrolls = 0;
    const document = {getElementById(id) {
        if(!elements.has(id)) elements.set(id, {
            innerHTML:'', textContent:'', value:'', disabled:false, hidden:false, attributes:{},
            classList:{remove(){},toggle(){}},
            setAttribute(name,value){this.attributes[name]=value;}, focus(){}, scrollIntoView(){scrolls++;},
            querySelectorAll(){return [];}, querySelector(){return {};},
        });
        return elements.get(id);
    }};
    const context = vm.createContext({
        document, URLSearchParams, URL, console:{error(){}},
        setTimeout:callback => {const id=++timerId;timers.set(id,callback);return id;},
        clearTimeout:id => timers.delete(id),
        showView:view => {views.push(view);if(view === 'management') vm.runInContext('renderManagement()',context);},
        toast:message => messages.push(message),
        fetch:async (url, requestOptions) => {
            requests.push({url, ...requestOptions});
            if(options.fetch) return options.fetch(url, requestOptions, requests.length);
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
    return {context, elements, requests, views, messages, timers, get scrolls(){return scrolls;},
        run:code=>vm.runInContext(code,context),
        async tick(){
            const callbacks=[...timers.values()];
            timers.clear();
            callbacks.forEach(callback=>callback());
            await new Promise(resolve=>setImmediate(resolve));
        },
    };
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

test('history loading blocks detail additions while report generation still allows selection changes', () => {
    const app = boot();
    app.run("state.managementSelection.add('event-2');state.history.loading=true;addToManagementSummary(state.events[9]);");
    assert.deepEqual([...app.run('state.managementSelection')], ['event-2']);
    assert.equal(app.views.length, 0);
    assert.match(app.messages[0], /請稍候/);
    app.run('state.history.loading=false;state.managementReportLoading=true;addToManagementSummary(state.events[9]);');
    assert.deepEqual([...app.run('state.managementSelection')], ['event-2','event-9']);
    assert.equal(app.elements.get('managementSearch').disabled,false);
    assert.equal(app.requests.length,0);
});

test('an event no longer in the loaded sources is not added to the management report', () => {
    const app = boot();
    vm.runInContext("addToManagementSummary({id:'removed-event'});", app.context);
    assert.equal(vm.runInContext('state.managementSelection.size', app.context), 0);
    assert.equal(app.views.length, 0);
    assert.equal(app.requests.length, 0);
    assert.match(app.messages[0], /已不在目前清單/);
});

function response(ids, headline='最新摘要'){
    return {ok:true,json:async()=>({ok:true,summary:{headline,summary:'依選取資料彙整。',
        source_events:ids.map(id=>({id,title:id,source:'官方來源'})),
    }})};
}

test('only the first report requires a click; later rapid changes produce one request for the latest selection',async()=>{
    const app=boot([], {fetch:(_url,options)=>response(JSON.parse(options.body).event_ids)});
    app.run("state.managementSelection=new Set(['event-1']);renderManagementSelection();");
    await app.tick();
    assert.equal(app.requests.length,0);
    await app.run('generateManagementReport()');
    const initialScrolls=app.scrolls;
    app.run("state.managementSelection.add('event-2');renderManagementSelection();");
    app.run("state.managementSelection.add('event-3');renderManagementSelection();");
    app.run("state.managementSelection.delete('event-1');renderManagementSelection();");
    assert.equal(app.requests.length,1);
    assert.equal(app.timers.size,1);
    await app.tick();
    assert.equal(app.requests.length,2);
    assert.deepEqual(JSON.parse(app.requests[1].body).event_ids,['event-2','event-3']);
    assert.equal(app.scrolls,initialScrolls,'Automatic updates keep the reading position');
    assert.equal(app.elements.get('reportBox').attributes['data-selection-match'],'true');
    assert.equal(app.elements.get('reportBox').attributes['aria-busy'],'false');
    assert.match(app.elements.get('reportBox').innerHTML,/event-3/);
    assert.doesNotMatch(app.elements.get('reportBox').innerHTML,/event-1/);
});

test('search, paging and reordering selected IDs do not reset or trigger an automatic update',async()=>{
    const app=boot(['event-1','event-2']);
    app.run("state.managementSelection=new Set(['event-1','event-2']);");
    await app.run('generateManagementReport()');
    app.run("state.managementSelection=new Set(['event-2','event-1']);state.managementQuery='資訊 9';state.pagination.management.page=2;renderManagement();");
    assert.equal(app.timers.size,0);
    assert.equal(app.requests.length,1);
    app.run("state.managementSelection.add('event-3');renderManagementSelection();");
    const timer=[...app.timers.keys()][0];
    app.run('renderManagement();renderManagementSelection();');
    assert.equal([...app.timers.keys()][0],timer);
});

test('in-flight generation allows editing, queues only the latest selection and never displays an obsolete reply',async()=>{
    const resolvers=[];
    const app=boot([], {fetch:()=>new Promise(resolve=>resolvers.push(resolve))});
    app.run("state.managementSelection=new Set(['event-1']);");
    const first=app.run('generateManagementReport()');
    assert.equal(app.elements.get('managementSearch').disabled,false);
    assert.equal(app.elements.get('managementTypeFilter').disabled,false);
    assert.doesNotMatch(app.elements.get('priorityList').innerHTML,/data-management-event="event-1"[^>]*disabled/);
    assert.doesNotMatch(app.elements.get('managementPagination').innerHTML,/data-page-size[^>]*disabled/);
    app.run("state.managementSelection=new Set(['event-2']);renderManagementSelection();");
    app.run("state.managementSelection=new Set(['event-3']);renderManagementSelection();");
    await app.tick();
    assert.equal(app.requests.length,1,'Keep only one model request in flight');
    resolvers[0](response(['event-1'],'過時的摘要'));
    await first;
    assert.equal(app.requests.length,2);
    assert.deepEqual(JSON.parse(app.requests[1].body).event_ids,['event-3']);
    assert.doesNotMatch(app.elements.get('reportBox').innerHTML,/過時的摘要/);
    resolvers[1](response(['event-3'],'目前選取的摘要'));
    await new Promise(resolve=>setImmediate(resolve));
    assert.match(app.elements.get('reportBox').innerHTML,/目前選取的摘要/);
    assert.equal(app.elements.get('reportBox').attributes['data-selection-match'],'true');
});

test('a failed automatic update preserves the old report with a visible notice and can be retried without a loop',async()=>{
    const app=boot([], {fetch:(_url,options,count)=>count===2
        ? {ok:false,json:async()=>({ok:false,error:'模型暫時無法使用'})}
        : response(JSON.parse(options.body).event_ids)});
    app.run("state.managementSelection=new Set(['event-1']);");
    await app.run('generateManagementReport()');
    app.run("state.managementSelection=new Set(['event-2']);renderManagementSelection();");
    assert.match(app.elements.get('managementReportStatus').textContent,/上一次結果/);
    await app.tick();
    assert.match(app.elements.get('reportBox').innerHTML,/event-1/);
    assert.match(app.elements.get('managementReportStatus').textContent,/模型暫時無法使用/);
    assert.equal(app.elements.get('managementReportStatus').hidden,false);
    assert.equal(app.elements.get('reportBtn').textContent,'重試更新');
    assert.equal(app.timers.size,0);
    app.run('renderManagementSelection()');
    await app.tick();
    assert.equal(app.requests.length,2);
    await app.run('generateManagementReport()');
    assert.match(app.elements.get('reportBox').innerHTML,/event-2/);
    assert.equal(app.elements.get('managementReportStatus').hidden,true);
});

test('clearing all selections ignores an in-flight result and selecting again resumes automatic updates',async()=>{
    let resolve;
    const app=boot([], {fetch:(_url,options,count)=>count===1
        ? new Promise(done=>{resolve=done;}) : response(JSON.parse(options.body).event_ids)});
    app.run("state.managementSelection=new Set(['event-1']);");
    const first=app.run('generateManagementReport()');
    app.run('state.managementSelection.clear();renderManagementSelection();');
    resolve(response(['event-1'],'不應顯示的舊回覆'));
    await first;
    await app.tick();
    assert.equal(app.requests.length,1);
    assert.match(app.elements.get('reportBox').innerHTML,/尚未選取資訊/);
    assert.doesNotMatch(app.elements.get('reportBox').innerHTML,/不應顯示的舊回覆/);
    assert.equal(app.elements.get('reportBtn').disabled,true);
    app.run("state.managementSelection.add('event-2');renderManagementSelection();");
    await app.tick();
    assert.equal(app.requests.length,2);
    assert.match(app.elements.get('reportBox').innerHTML,/event-2/);
});

test('returning to the completed selection reuses its report without another request',async()=>{
    const app=boot(['event-1']);
    app.run("state.managementSelection=new Set(['event-1']);");
    await app.run('generateManagementReport()');
    app.run("state.managementSelection=new Set(['event-2']);renderManagementSelection();");
    app.run("state.managementSelection=new Set(['event-1']);renderManagementSelection();");
    await app.tick();
    assert.equal(app.requests.length,1);
    assert.equal(app.elements.get('managementReportStatus').hidden,true);
    assert.equal(app.elements.get('reportBox').attributes['data-selection-match'],'true');
});

test('management source review renders warnings and checked quotes safely while keeping details collapsed',()=>{
    const app=boot();
    app.context.reviewReport={headline:'測試摘要',summary:'保留的內容',verification_notice:'部分結論未獲原文充分支持，已省略。',
        support_review:{requested:2,supported:1,withheld:1,sources:[{source_id:'S1',title:'測試來源',url:'https://example.com/source'}],
            checks:[{id:'summary',status:'supported',text:'<img src=x>',citations:[{source_id:'S1',quote:'官方原文包含 <script> 測試文字。'}]},
                {id:'action',status:'insufficient',text:'不應顯示的結論',citations:[]}]}};
    app.run('renderManagementReport(reviewReport,[])');
    const html=app.elements.get('reportBox').innerHTML;
    assert.match(html,/management-review-warning/);
    assert.match(html,/依據核對：保留 1 項，省略 1 項/);
    assert.match(html,/href="https:\/\/example.com\/source"/);
    assert.match(html,/&lt;script&gt;/);
    assert.doesNotMatch(html,/<img|<script>|不應顯示的結論/);
    assert.match(html,/<details class="management-section management-review-details">/);
});

test('an unavailable source review preserves the prior report during automatic updates',async()=>{
    const app=boot([], {fetch:(_url,options,count)=>{
        const ids=JSON.parse(options.body).event_ids;
        return count===2 ? {ok:true,json:async()=>({ok:true,summary:{support_review:{unverified:2,supported:0},
            source_events:ids.map(id=>({id,title:id}))}})} : response(ids);
    }});
    app.run("state.managementSelection=new Set(['event-1']);");
    await app.run('generateManagementReport()');
    app.run("state.managementSelection=new Set(['event-2']);renderManagementSelection();");
    await app.tick();
    assert.match(app.elements.get('reportBox').innerHTML,/event-1/);
    assert.match(app.elements.get('managementReportStatus').textContent,/依據核對未完成/);
    assert.equal(app.elements.get('reportBtn').textContent,'重試更新');
});
