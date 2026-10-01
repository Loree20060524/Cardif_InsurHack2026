const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

test('management topic change uses dated source text, not generated advice', () => {
    const trendList = {innerHTML: ''};
    const context = vm.createContext({
        document: {getElementById: id => id === 'trendList' ? trendList : null},
        URLSearchParams,
    });
    const root = path.resolve(__dirname, '..');
    for (const file of ['assets/js/core.js', 'assets/js/management.js']) {
        vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), context);
    }
    context.fixtures = [
        {title: '保險業資安規範', description: '', published_at: '2026-09-30'},
        {title: '保險業監理公告', description: '', published_at: '2026-09-20',
            analysis: {summary: '資安'}},
        {title: '資安通報要求', description: '', published_at: '2026-08-20'},
        {title: '資安舊聞', description: '', published_at: '2026-05-01'},
    ];
    vm.runInContext('state.events = fixtures; renderTopics();', context);
    assert.match(trendList.innerHTML, /近 30 日與前 30 日比較/);
    assert.match(trendList.innerHTML, /資安／個資[\s\S]*?1\s*\/\s*1/);
});
