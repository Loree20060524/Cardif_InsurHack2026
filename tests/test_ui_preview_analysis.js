const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');


class FakeElement {
    constructor(tagName = 'div') {
        this.tagName = tagName;
        this.children = [];
        this.dataset = {};
        this.listeners = {};
        this.attributes = {};
        this.className = '';
        this.textContent = '';
        this.innerHTML = '';
        this.value = '';
        this.descendants = new Map();
    }

    addEventListener(type, listener) {
        this.listeners[type] = listener;
    }

    appendChild(child) {
        this.children.push(child);
        return child;
    }

    insertBefore(child) {
        this.children.push(child);
        return child;
    }

    setAttribute(name, value) {
        this.attributes[name] = value;
    }

    querySelector(selector) {
        if (!this.descendants.has(selector)) {
            this.descendants.set(selector, new FakeElement());
        }
        return this.descendants.get(selector);
    }

    querySelectorAll() {
        return [];
    }
}


class FakeCustomEvent {
    constructor(type, options = {}) {
        this.type = type;
        this.detail = options.detail;
    }
}


function bootPreview() {
    const created = [];
    const documentListeners = new Map();
    const documentElements = new Map();
    const selectors = new Map();
    const document = {
        head: new FakeElement('head'),
        body: new FakeElement('body'),
        createElement(tagName) {
            const element = new FakeElement(tagName);
            created.push(element);
            return element;
        },
        getElementById(id) {
            if (!documentElements.has(id)) {
                documentElements.set(id, new FakeElement());
            }
            return documentElements.get(id);
        },
        querySelector(selector) {
            if (!selectors.has(selector)) {
                selectors.set(selector, new FakeElement());
            }
            return selectors.get(selector);
        },
        addEventListener(type, listener) {
            documentListeners.set(type, listener);
        },
        dispatchEvent(event) {
            documentListeners.get(event.type)?.(event);
        },
    };
    const event = {
        id: 'event-1',
        source_key: 'insurance_law',
        source: '保險局主管法規',
        title: '保險法規更新',
        url: 'https://example.org/law',
        analysis: {
            analysis_mode: '規則備援',
            risk_level: '待確認',
            summary: '規則備援摘要',
            regulatory_points: ['目前要點'],
            attention_items: ['檢查生效日期'],
            departments: ['法遵'],
            impact_processes: ['法規審查'],
            actions: ['比對修正內容'],
        },
    };
    const state = {
        events: [event],
        selected: event.id,
        query: '',
        filters: { types: new Set(), departments: new Set() },
        sources: {},
        lastSync: '2026-09-25T00:00:00Z',
        ai: { enabled: true, mode: '按需 AI 深度分析' },
        aiLoading: new Set(),
        aiRequested: new Set(),
        aiFailed: new Set(),
    };
    const context = vm.createContext({
        URL,
        URLSearchParams,
        CustomEvent: FakeCustomEvent,
        document,
        history: { replaceState() {} },
        location: { search: '?variant=D', pathname: '/', hash: '' },
        MutationObserver: class {
            observe() {}
        },
        state,
        esc: value => String(value ?? ''),
        sourceType: () => '法規',
        formatDate: value => String(value),
        formatEventDate: () => '2026/09/25',
        filteredEvents: () => state.events,
        $: () => new FakeElement(),
        renderList() {},
        renderAdvancedFilters() {},
        renderDetail() {},
        renderManagement() {},
        showView() {},
        toast() {},
        console: { error() {} },
        fetch: async () => ({
            ok: true,
            json: async () => ({
                ai_used: true,
                analysis: {
                    analysis_mode: 'AI 深度分析',
                    risk_level: '中',
                    summary: 'AI 完成後的新摘要',
                    regulatory_points: ['AI 整理的法規重點'],
                    attention_items: ['AI 整理的注意事項'],
                    departments: ['法遵'],
                    impact_processes: ['法規審查'],
                    actions: ['完成修正評估'],
                },
            }),
        }),
    });
    const root = path.resolve(__dirname, '..');

    for (const file of ['prototypes/ui-directions-preview.js', 'assets/js/ai-analysis.js']) {
        vm.runInContext(
            fs.readFileSync(path.join(root, file), 'utf8'),
            context,
            { filename: file },
        );
    }

    const dView = created.find(element => element.className === 'd-view');
    return {
        context,
        dDetail: dView.querySelector('[data-d-detail]'),
        event,
    };
}


test('D preview shows attention items already returned by analysis', () => {
    const { dDetail } = bootPreview();

    assert.match(dDetail.innerHTML, /應注意事項/);
    assert.match(dDetail.innerHTML, /檢查生效日期/);
});


test('D preview refreshes its selected dossier when AI analysis completes', async () => {
    const { context, dDetail, event } = bootPreview();

    await vm.runInContext('ensureAIAnalysis(state.events[0])', context);

    assert.equal(event.analysis.analysis_mode, 'AI 深度分析');
    assert.match(dDetail.innerHTML, /AI 完成後的新摘要/);
    assert.match(dDetail.innerHTML, /AI 整理的注意事項/);
});


test('completed AI analysis can be explicitly rerun after prompt changes', async () => {
    const { context, event } = bootPreview();
    let requestCount = 0;
    event.analysis.analysis_mode = 'AI 深度分析';
    event.analysis.support_review = {version:'event-support-v1', unverified:0};
    context.fetch = async () => {
        requestCount += 1;
        return {
            ok: true,
            json: async () => ({
                ai_used: true,
                analysis: {
                    ...event.analysis,
                    summary: '重新分析後摘要',
                },
            }),
        };
    };

    await vm.runInContext('ensureAIAnalysis(state.events[0])', context);
    assert.equal(requestCount, 0, 'completed analysis should be reused by default');

    await vm.runInContext('ensureAIAnalysis(state.events[0], true)', context);
    assert.equal(requestCount, 1, 'explicit rerun should bypass the completed result');
    assert.equal(event.analysis.summary, '重新分析後摘要');
});

test('explicit rerun after a successful request reaches the server and bypasses its cache', async () => {
    const { context, event } = bootPreview();
    const requests = [];
    context.fetch = async url => {
        requests.push(url);
        return {ok:true, json:async () => ({ai_used:true, analysis:{...event.analysis, analysis_mode:'AI 深度分析'}})};
    };
    await vm.runInContext('ensureAIAnalysis(state.events[0])', context);
    await vm.runInContext('ensureAIAnalysis(state.events[0])', context);
    await vm.runInContext('ensureAIAnalysis(state.events[0], true)', context);
    assert.deepEqual(requests, ['/api/analyze?id=event-1', '/api/analyze?id=event-1&force=1']);
});

test('a force request cannot start a second analysis while the first is pending', async () => {
    const { context } = bootPreview();
    let finish;
    let requests = 0;
    context.fetch = () => {
        requests += 1;
        return new Promise(resolve => {finish = resolve;});
    };
    const first = vm.runInContext('ensureAIAnalysis(state.events[0])', context);
    await vm.runInContext('ensureAIAnalysis(state.events[0], true)', context);
    assert.equal(requests, 1);
    finish({ok:true, json:async () => ({ai_used:true, analysis:{analysis_mode:'AI 深度分析'}})});
    await first;
});

test('a failed forced generation keeps the completed result and marks retry as failed', async () => {
    const { context, event } = bootPreview();
    event.analysis = {...event.analysis, analysis_mode:'AI 深度分析', summary:'先前完成的摘要'};
    context.fetch = async () => ({ok:true, json:async () => ({ai_used:false,
        analysis:{analysis_mode:'規則備援', summary:'模型失敗後的備援內容'}})});
    await vm.runInContext('ensureAIAnalysis(state.events[0], true)', context);
    assert.equal(event.analysis.summary, '先前完成的摘要');
    assert.equal(event.analysis.analysis_mode, 'AI 深度分析');
    assert.equal(vm.runInContext('state.aiFailed.has(state.events[0].id)', context), true);
    assert.equal(vm.runInContext('state.aiRequested.has(state.events[0].id)', context), false);
    assert.equal(vm.runInContext('state.aiLoading.has(state.events[0].id)', context), false);
});


test('D preview offers a working retry when AI returns rule fallback', async () => {
    const { context, dDetail, event } = bootPreview();
    let requestCount = 0;

    context.fetch = async () => {
        requestCount += 1;
        return {
            ok: true,
            json: async () => ({
                ai_used: false,
                message: 'model unavailable',
                analysis: event.analysis,
            }),
        };
    };
    await vm.runInContext('ensureAIAnalysis(state.events[0])', context);

    assert.match(dDetail.innerHTML, /重試 AI 分析/);
    assert.equal(vm.runInContext('state.aiRequested.has("event-1")', context), false);
    await vm.runInContext('ensureAIAnalysis(state.events[0])', context);
    assert.equal(requestCount, 1, 'failed analysis should not retry on a later render');

    context.fetch = async () => {
        requestCount += 1;
        return {
            ok: true,
            json: async () => ({
                ai_used: true,
                analysis: {
                    ...event.analysis,
                    analysis_mode: 'AI 深度分析',
                    summary: '重試後完成的 AI 摘要',
                },
            }),
        };
    };
    const analyzeButton = { dataset: { dAnalyze: event.id } };
    dDetail.listeners.click({
        target: {
            closest: selector => selector === '[data-d-analyze]' ? analyzeButton : null,
        },
    });
    await new Promise(resolve => setImmediate(resolve));

    assert.equal(requestCount, 2);
    assert.match(dDetail.innerHTML, /重試後完成的 AI 摘要/);
    assert.doesNotMatch(dDetail.innerHTML, /重試 AI 分析/);
});
