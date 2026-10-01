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

    for (const file of ['assets/js/core.js', 'assets/js/dashboard.js']) {
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
