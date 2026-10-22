const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');


function renderEventList(event) {
    const eventList = { innerHTML: '' };
    const eventDetail = { innerHTML: '' };
    const sourceTypeList = {
        innerHTML: '',
        querySelectorAll: () => [],
    };
    const elements = {
        eventList,
        eventDetail,
        sourceTypeList,
        eventPagination: { innerHTML: '', querySelector: () => ({}) },
        ledgerResultCount: { textContent: '' },
        ledgerStatus: { textContent: '' },
    };
    const context = vm.createContext({
        document: {
            getElementById: id => elements[id],
            querySelectorAll: () => [],
        },
        URLSearchParams,
        formatDate: value => String(value),
    });
    const root = path.resolve(__dirname, '..');

    for (const file of ['assets/js/core.js', 'assets/js/pagination.js', 'assets/js/dashboard.js']) {
        vm.runInContext(
            fs.readFileSync(path.join(root, file), 'utf8'),
            context,
            { filename: file },
        );
    }

    context.eventFixture = event;
    vm.runInContext(
        'state.events = [eventFixture]; state.selected = eventFixture.id; renderList();',
        context,
    );

    return eventList.innerHTML;
}


function filteredEventIds(events, types, departments) {
    const context = vm.createContext({
        document: {
            getElementById: () => null,
        },
        URLSearchParams,
    });
    const root = path.resolve(__dirname, '..');

    vm.runInContext(
        fs.readFileSync(path.join(root, 'assets/js/core.js'), 'utf8'),
        context,
        { filename: 'assets/js/core.js' },
    );

    context.eventFixtures = events;
    context.typeFixtures = types;
    context.departmentFixtures = departments;

    return vm.runInContext(
        `state.events = eventFixtures;
         state.filters.types = new Set(typeFixtures);
         state.filters.departments = new Set(departmentFixtures);
         filteredEvents().map(event => event.id);`,
        context,
    );
}


test('latest regulatory signal does not show an internal pending workflow', () => {
    const html = renderEventList({
        id: 'event-1',
        source_key: 'reg_news',
        source: '金融監理新聞',
        title: '保險業監理制度更新',
        published_at: '2026-09-08T00:00:00+08:00',
        workflow_status: '待確認',
    });

    assert.doesNotMatch(html, /待確認/);
    assert.match(html, /金融監理新聞/);
});


test('advanced search combines multi-select types and responsible departments', () => {
    const events = [
        {
            id: 'law-compliance',
            source_key: 'law_db',
            title: '法規更新',
            analysis: { responsible_department: '法令遵循部' },
        },
        {
            id: 'penalty-risk',
            source_key: 'fsc_penalty',
            title: '裁罰事件',
            analysis: { responsible_department: '風險管理部' },
        },
        {
            id: 'news-finance',
            source_key: 'reg_news',
            title: '監理新聞',
            analysis: { responsible_department: '財務部' },
        },
        {
            id: 'law-finance',
            source_key: 'insurance_law',
            title: '財務法規',
            analysis: { responsible_department: '財務部' },
        },
    ];

    const ids = filteredEventIds(
        events,
        ['法規', '裁罰'],
        ['法令遵循', '風險管理'],
    );

    assert.deepEqual([...ids], ['law-compliance', 'penalty-risk']);
});

function bootFilters(){
    const elements=new Map();
    const inputs=[
        {dataset:{advancedFilterGroup:'types'},value:'公告',checked:false},
        {dataset:{advancedFilterGroup:'types'},value:'法規',checked:false},
        {dataset:{advancedFilterGroup:'riskLevels'},value:'中',checked:false},
    ];
    const document={
        getElementById(id){
            if(!elements.has(id)) elements.set(id,{
                innerHTML:'',textContent:'',value:'',hidden:false,
                classList:{toggle(){}},setAttribute(){},
                querySelectorAll(){return [];},querySelector(){return {};},
            });
            return elements.get(id);
        },
        querySelectorAll:selector=>selector==='[data-advanced-filter-group]' ? inputs : [],
    };
    const context=vm.createContext({document,URLSearchParams,renderDetail(){}});
    for(const file of ['core.js','pagination.js','dashboard.js']){
        vm.runInContext(fs.readFileSync(path.join(__dirname,'..','assets','js',file),'utf8'),context);
    }
    vm.runInContext(`state.events=[
        {id:'announcement',source_key:'fsc_announcement',title:'保險更新公告',analysis:{risk_level:'中',responsible_department:'法令遵循'}},
        {id:'law',source_key:'law_db',title:'保險法規',analysis:{risk_level:'中',responsible_department:'法令遵循'}},
        {id:'news',source_key:'reg_news',title:'保險新聞',analysis:{risk_level:'高',responsible_department:'財務'}},
    ];`,context);
    return {context,elements,inputs,run:code=>vm.runInContext(code,context)};
}

test('sidebar and advanced type checkboxes apply one shared selection immediately, including multiple types',()=>{
    const app=bootFilters();
    app.run("setIntelSourceType('公告');setAdvancedFilterOpen(true);");
    assert.deepEqual([...app.run('ledgerEvents().map(event=>event.id)')],['announcement']);
    assert.match(app.elements.get('typeFilterOptions').innerHTML,/value="公告"\s+checked/);
    const law=app.inputs.find(input=>input.value==='法規');
    law.checked=true;
    law.onchange();
    assert.deepEqual([...app.run('ledgerEvents().map(event=>event.id)')],['announcement','law']);
    assert.equal(app.run('state.advancedFilterOpen'),true);
    assert.match(app.elements.get('sourceTypeList').innerHTML,/d-source-option active"\s+data-source-type="公告"/);
    assert.match(app.elements.get('sourceTypeList').innerHTML,/d-source-option active"\s+data-source-type="法規"/);
    const announcement=app.inputs.find(input=>input.value==='公告');
    announcement.checked=false;
    announcement.onchange();
    assert.deepEqual([...app.run('ledgerEvents().map(event=>event.id)')],['law']);
    assert.match(app.elements.get('intelActiveFilters').innerHTML,/類型：法規/);
    assert.doesNotMatch(app.elements.get('intelActiveFilters').innerHTML,/類型：公告/);
    assert.deepEqual([...app.run("archiveSources('intel')")],[]);
});

test('choosing a sidebar type replaces only types and keeps keyword, risk and department filters',()=>{
    const app=bootFilters();
    app.run("state.query='保險';state.filters.riskLevels.add('中');state.filters.departments.add('法令遵循');setIntelSourceType('公告');setIntelSourceType('法規');");
    assert.deepEqual([...app.run('state.filters.types')],['法規']);
    assert.deepEqual([...app.run('state.filterDraft.types')],['法規']);
    assert.deepEqual([...app.run('ledgerEvents().map(event=>event.id)')],['law']);
    assert.match(app.elements.get('intelActiveFilters').innerHTML,/關鍵字：保險/);
    assert.match(app.elements.get('intelActiveFilters').innerHTML,/風險：中/);
    assert.match(app.elements.get('intelActiveFilters').innerHTML,/部門：法令遵循/);
    app.run("setIntelSourceType('全部');");
    assert.deepEqual([...app.run('ledgerEvents().map(event=>event.id)')],['announcement','law']);
    assert.deepEqual([...app.run("archiveSources('intel')")],['fsc_announcement','fsc_penalty','reg_news']);
});

test('risk checkboxes apply without closing the panel; clearing all also resets search and type selection',()=>{
    const app=bootFilters();
    app.run("setIntelSourceType('法規');setAdvancedFilterOpen(true);");
    const risk=app.inputs.find(input=>input.value==='中');
    risk.checked=true;
    risk.onchange();
    assert.deepEqual([...app.run('state.filters.riskLevels')],['中']);
    app.run("state.query='不存在的字';renderList();clearAdvancedFilterDraft();");
    assert.equal(app.run('advancedFilterCount()'),0);
    assert.equal(app.run('state.query'),'');
    assert.equal(app.run('state.advancedFilterOpen'),true);
    assert.equal(app.elements.get('search').value,'');
    assert.equal(app.elements.get('intelActiveFilters').hidden,true);
    assert.deepEqual([...app.run('ledgerEvents().map(event=>event.id)')],['announcement','law','news']);
    assert.doesNotMatch(app.elements.get('typeFilterOptions').innerHTML,/\schecked/);
});

test('individual active-filter chips remove one condition and escape search text',()=>{
    const app=bootFilters();
    app.run("setIntelSourceType('法規');state.filters.riskLevels.add('中');renderList();");
    const removeType={dataset:{filterGroup:'types',filterValue:'法規'}};
    app.elements.get('intelActiveFilters').querySelectorAll=()=>[removeType];
    app.run('renderActiveIntelFilters()');
    removeType.onclick();
    assert.equal(app.run('state.filters.types.size'),0);
    assert.deepEqual([...app.run('state.filters.riskLevels')],['中']);
    app.run(`state.query='<img src=x onerror="alert(1)">';renderActiveIntelFilters();`);
    assert.doesNotMatch(app.elements.get('intelActiveFilters').innerHTML,/<img/);
    assert.match(app.elements.get('intelActiveFilters').innerHTML,/&lt;img/);
});

test('AI completion reapplies risk filters and replaces a detail that no longer matches',async()=>{
    const app=bootFilters();
    app.context.console={error(){}};
    app.context.renderManagement=()=>{};
    app.context.fetch=async()=>({ok:true,json:async()=>({ai_used:true,analysis:{
        analysis_mode:'AI 深度分析',risk_level:'高',importance:'重要',responsible_department:'資訊科技',
        support_review:{version:'test',unverified:0},
    }})});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/js/ai-analysis.js'),'utf8'),app.context);
    app.run('state.ai.enabled=true;state.selected="announcement";state.filters.riskLevels.add("中");renderList();');
    assert.match(app.elements.get('eventList').innerHTML,/data-id="announcement"/);
    await app.run('ensureAIAnalysis(state.events[0])');
    assert.doesNotMatch(app.elements.get('eventList').innerHTML,/data-id="announcement"/);
    assert.match(app.elements.get('eventList').innerHTML,/data-id="law"/);
    assert.equal(app.elements.get('ledgerResultCount').textContent,'共 1 筆');
    assert.equal(app.run('state.selected'),'law');
    assert.match(app.elements.get('departmentFilterOptions').innerHTML,/資訊科技/);
});
