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


test('D preview offers a working retry when AI returns rule fallback', async () => {
    const { context, dDetail, event } = bootPreview();

    context.fetch = async () => ({
        ok: true,
        json: async () => ({
            ai_used: false,
            message: 'model unavailable',
            analysis: event.analysis,
        }),
    });
    await vm.runInContext('ensureAIAnalysis(state.events[0])', context);

    assert.match(dDetail.innerHTML, /重試 AI 分析/);
    assert.equal(vm.runInContext('state.aiRequested.has("event-1")', context), false);

    context.fetch = async () => ({
        ok: true,
        json: async () => ({
            ai_used: true,
            analysis: {
                ...event.analysis,
                analysis_mode: 'AI 深度分析',
                summary: '重試後完成的 AI 摘要',
            },
        }),
    });
    const analyzeButton = { dataset: { dAnalyze: event.id } };
    dDetail.listeners.click({
        target: {
            closest: selector => selector === '[data-d-analyze]' ? analyzeButton : null,
        },
    });
    await new Promise(resolve => setImmediate(resolve));

    assert.match(dDetail.innerHTML, /重試後完成的 AI 摘要/);
    assert.doesNotMatch(dDetail.innerHTML, /重試 AI 分析/);
});
