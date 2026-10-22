const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

async function loadFixture(payload, { force = false, offline = false } = {}) {
    const classes = new Set(['hidden']);
    const elements = {
        refreshBtn: {},
        connectionNotice: {
            innerHTML: '', className: '',
            classList: { add: name => classes.add(name), remove: name => classes.delete(name) },
        },
    };
    const messages = [];
    const context = vm.createContext({
        $: id => elements[id] || (elements[id] = {innerHTML:'',textContent:'',disabled:false}),
        state: { history: {}, events: [], sources: {}, selected: null },
        fetch: async () => {
            if (offline) throw new Error('offline');
            return { ok: true, json: async () => payload };
        },
        renderList() {}, renderAdvancedFilters() {}, renderTicker() {},
        renderDetail() {}, renderManagement() {}, renderSources() {},
        toast: message => messages.push(message), console: { error() {} },
    });
    const source = fs.readFileSync(path.join(__dirname, '../assets/js/app.js'), 'utf8');
    vm.runInContext(source.slice(0, source.indexOf('function showView(')), context);
    await vm.runInContext(`loadEvents(${force})`, context);
    return { notice: elements.connectionNotice, hidden: classes.has('hidden'), messages };
}

test('healthy saved data does not display a source update failure warning', async () => {
    const result = await loadFixture({ events: [{ id: 'public' }], deployment_snapshot: true, stale: false });
    assert.equal(result.hidden, true);
    assert.doesNotMatch(result.notice.innerHTML, /無法更新/);
});

test('actual source failures remain visible and do not claim a successful full refresh', async () => {
    const result = await loadFixture({ events: [{ id: 'public' }], stale: true }, { force: true });
    assert.equal(result.hidden, false);
    assert.match(result.notice.innerHTML, /部分官方來源目前無法更新/);
    assert.match(result.messages[0], /部分來源更新失敗/);
    assert.doesNotMatch(result.messages[0], /最新監理資訊已更新/);
});

test('hosted data failures do not ask the user to start a local Python server', async () => {
    const result = await loadFixture({}, { offline: true });
    assert.equal(result.hidden, false);
    assert.match(result.notice.innerHTML, /目前無法取得資料/);
    assert.match(result.notice.innerHTML, /重新載入/);
    assert.doesNotMatch(result.notice.innerHTML, /server\.py|本機/);
});
