// Throwaway UI prototype on the existing intelligence route (?variant=A|B|C|D).
(() => {
    const variants = {
        A: '清單工作台',
        B: '管理簡報',
        C: '風險監控台',
        D: '監理紀錄簿',
    };
    const parameters = new URLSearchParams(location.search);
    const initial = parameters.get('variant');
    if (!variants[initial]) return;

    const sheet = document.createElement('link');
    sheet.rel = 'stylesheet';
    sheet.href = 'prototypes/ui-directions-preview.css';
    document.head.appendChild(sheet);

    const intro = document.createElement('section');
    intro.className = 'preview-intro';
    intro.setAttribute('aria-label', '監理情報概覽');
    intro.innerHTML = `
        <div class="preview-intro-copy">
            <span class="preview-eyebrow">REGULATORY INTELLIGENCE / 監理情報</span>
            <h2>掌握最新監理動向</h2>
            <p>從官方發布資訊辨識企業影響，快速找到需要關注的法規與部門。</p>
        </div>
        <div class="preview-metrics" aria-label="即時資料概況">
            <div class="preview-metric"><strong data-preview-count>—</strong><span>監理訊號</span></div>
            <div class="preview-metric"><strong data-preview-high>—</strong><span>高風險事項</span></div>
            <div class="preview-metric"><strong data-preview-sources>—</strong><span>監測來源</span></div>
        </div>
    `;
    const intel = document.getElementById('intelView');
    intel.insertBefore(intro, intel.firstChild);

    const topNav = document.createElement('div');
    topNav.className = 'preview-top-nav';
    topNav.innerHTML = '<button type="button" class="active" data-preview-view="intel">監理情報</button><button type="button" data-preview-view="management">管理摘要</button>';
    document.querySelector('.topbar').insertBefore(topNav, document.querySelector('.top-actions'));
    topNav.addEventListener('click', event => {
        const button = event.target.closest('[data-preview-view]');
        if (!button) return;
        showView(button.dataset.previewView);
        topNav.querySelectorAll('button').forEach(item => {
            item.classList.toggle('active', item === button);
        });
    });

    const dHeader = document.createElement('header');
    dHeader.className = 'd-header';
    dHeader.innerHTML = `
        <div class="d-brand"><strong>法遵雷達</strong><span>保險監理情報</span></div>
        <nav aria-label="預覽導覽"><button type="button" class="active" data-d-view="intel">監理情報</button><button type="button" data-d-view="management">管理摘要</button></nav>
        <div class="d-header-actions"><span class="d-connect"><i></i> 官方來源資料</span><button type="button" data-d-sources>來源狀態</button><button type="button" class="d-refresh" data-d-refresh>同步資料 ↗</button></div>
    `;
    document.querySelector('.main').insertBefore(dHeader, document.querySelector('.topbar'));

    const dView = document.createElement('div');
    dView.className = 'd-view';
    dView.innerHTML = `
        <div class="d-heading"><div><span class="d-overline">保險監理資訊</span><h2>監理資訊</h2><p>彙整主管機關公告與法規更新，選取項目查看重點及可能影響。</p></div><div class="d-statusline" data-d-status></div></div>
        <div class="d-workspace">
            <aside class="d-filters" aria-label="資訊類型篩選"><div class="d-side-title">資訊類別</div><div class="d-source-list" data-d-sources-list></div><p class="d-side-note">資料來源為主管機關公開資訊；分析內容供初步參考。</p></aside>
            <section class="d-ledger" aria-label="監理事件紀錄"><div class="d-ledger-title"><div><h3>最新公告與法規</h3></div><small data-d-result></small></div><div class="d-search"><span aria-hidden="true">⌕</span><input type="search" placeholder="搜尋公告、法規或關鍵字" aria-label="搜尋監理事件"><div class="d-filter-host"></div></div><div class="d-table-head"><span>發布日期</span><span>類型</span><span>公告與法規</span></div><div class="d-table-body" data-d-table></div></section>
            <section class="d-dossier" aria-label="選取事件的分析" data-d-detail></section>
        </div>
    `;
    intel.appendChild(dView);
    const dSourceList = dView.querySelector('[data-d-sources-list]');
    const dTable = dView.querySelector('[data-d-table]');
    const dDetail = dView.querySelector('[data-d-detail]');
    const dSearch = dView.querySelector('.d-search input');
    const originalFilterHost = document.querySelector('.toolbar');
    const advancedFilter = document.getElementById('advancedFilter');
    const dFilterHost = dView.querySelector('.d-filter-host');
    const dAnalysisFailures = new Set();
    let dDisplayedEventId = null;
    let dSource = '全部';
    dHeader.addEventListener('click', event => {
        const viewButton = event.target.closest('[data-d-view]');
        if (viewButton) {
            showView(viewButton.dataset.dView);
            dHeader.querySelectorAll('[data-d-view]').forEach(button => button.classList.toggle('active', button === viewButton));
        }
        if (event.target.closest('[data-d-sources]')) document.getElementById('sourcesBtn').click();
        if (event.target.closest('[data-d-refresh]')) document.getElementById('refreshBtn').click();
    });
    dSourceList.addEventListener('click', event => {
        const button = event.target.closest('[data-d-source]');
        if (!button) return;
        dSource = button.dataset.dSource;
        renderD();
    });
    dTable.addEventListener('click', event => {
        const button = event.target.closest('[data-d-id]');
        if (!button) return;
        state.selected = button.dataset.dId;
        dAnalysisFailures.delete(state.selected);
        renderList();
        renderDetail();
        renderD();
    });
    dDetail.addEventListener('click', event => {
        const button = event.target.closest('[data-d-analyze]');
        if (!button || !state.ai?.enabled) return;
        const selected = (state.events || []).find(item => item.id === button.dataset.dAnalyze);
        if (!selected || state.aiLoading.has(selected.id)) return;
        state.aiRequested.delete(selected.id);
        state.aiFailed.delete(selected.id);
        dAnalysisFailures.delete(selected.id);
        ensureAIAnalysis(selected, true);
        renderD();
    });
    dSearch.addEventListener('input', renderD);

    function renderD() {
        const events = state.events || [];
        const types = ['全部', '法規', '公告', '裁罰', '監理新聞', '監理資訊'];
        const counts = new Map(types.map(type => [type, 0]));
        events.forEach(event => {
            const type = sourceType(event);
            counts.set(type, (counts.get(type) || 0) + 1);
        });
        counts.set('全部', events.length);
        dSourceList.innerHTML = types.filter(type => counts.get(type)).map(type => `
            <button type="button" data-d-source="${esc(type)}" class="${type === dSource ? 'active' : ''}"><span>${esc(type)}</span><em>${counts.get(type)}</em></button>
        `).join('');

        const query = dSearch.value.trim().toLocaleLowerCase();
        const shown = filteredEvents().filter(event => {
            if (dSource !== '全部' && sourceType(event) !== dSource) return false;
            if (!query) return true;
            return [event.title, event.source, event.description, event.analysis?.summary]
                .join(' ').toLocaleLowerCase().includes(query);
        });
        shown.sort((a, b) => new Date(b.published_at || b.detected_at || 0) - new Date(a.published_at || a.detected_at || 0));
        dView.querySelector('[data-d-result]').textContent = `共 ${shown.length} 筆`;
        const lastUpdated = state.lastSync ? formatDate(state.lastSync) : '日期未提供';
        dView.querySelector('[data-d-status]').innerHTML = `
            <span>共 ${events.length} 筆資料</span>
            <span>更新日期 ${esc(lastUpdated)}</span>
        `;

        dTable.innerHTML = shown.length ? shown.map(event => {
            return `
                <button type="button" class="d-row ${event.id === state.selected ? 'active' : ''}" data-d-id="${esc(event.id)}">
                    <time>${esc(formatEventDate(event))}</time>
                    <span class="d-type">${esc(sourceType(event))}</span>
                    <span class="d-row-main"><strong>${esc(event.title)}</strong><small>${esc(event.source || '')}</small></span>
                </button>
            `;
        }).join('') : '<div class="d-empty">目前沒有符合條件的監理事件。</div>';

        const event = shown.find(item => item.id === state.selected) || shown[0];
        if (!event) {
            dDetail.innerHTML = '<div class="d-empty">選擇一筆事件以查看分析。</div>';
            return;
        }
        const analysis = event.analysis || {};
        const points = (analysis.regulatory_points || []).slice(0, 3);
        const actions = (analysis.actions || []).slice(0, 3);
        const departments = (analysis.departments || []).slice(0, 5);
        const processes = (analysis.impact_processes || []).slice(0, 3);
        const attention = (analysis.attention_items || []).slice(0, 3);
        const summary = analysis.summary || event.description || '尚無分析摘要。';
        const aiComplete = analysis.analysis_mode === 'AI 深度分析';
        const aiLoading = state.aiLoading.has(event.id);
        const aiFailed = dAnalysisFailures.has(event.id);
        const aiStatus = aiLoading
            ? 'AI 深度分析中'
            : aiComplete
                ? 'AI 深度分析完成'
                : aiFailed
                    ? 'AI 分析未完成'
                    : state.ai?.enabled
                        ? '尚待 AI 深度分析'
                        : '目前為規則備援';
        const riskLevel = analysis.risk_level === '待確認' && !aiComplete
            ? aiFailed
                ? '分析失敗，待重試'
                : state.ai?.enabled
                    ? '待 AI 分析'
                    : '待人工確認'
            : analysis.risk_level || '待評估';
        let sourceUrl = '';
        try {
            const parsedUrl = new URL(String(event.url || ''));
            if (parsedUrl.protocol === 'https:' || parsedUrl.protocol === 'http:') sourceUrl = parsedUrl.href;
        } catch (_) {}
        dDisplayedEventId = event.id;
        dDetail.innerHTML = `
            <div class="d-dossier-top"><span>內容摘要</span><span>${esc(sourceType(event))}</span></div>
            <div class="d-dossier-body">
                <div class="d-case-number">${esc(formatEventDate(event))} · ${esc(event.source || '')}</div>
                <h3>${esc(event.title)}</h3>
                ${sourceUrl ? `<a class="d-source-link" href="${esc(sourceUrl)}" target="_blank" rel="noopener noreferrer">開啟主管機關原文 ↗</a>` : ''}
                <div class="d-ai-control"><span class="d-ai-state ${aiLoading ? 'loading' : aiComplete ? 'complete' : aiFailed ? 'failed' : ''}">${esc(aiStatus)}</span>${state.ai?.enabled && !aiComplete ? `<button type="button" data-d-analyze="${esc(event.id)}" ${aiLoading ? 'disabled' : ''}>${aiLoading ? '分析中…' : aiFailed ? '重試 AI 分析' : '進行 AI 深度分析'}</button>` : ''}</div>
                <div class="d-facts">
                    <div><span>風險程度</span><strong class="${analysis.risk_level === '高' ? 'd-fact-high' : ''}">${esc(riskLevel)}</strong></div>
                    <div><span>重要性</span><strong>${esc(analysis.importance || '未評估')}</strong></div>
                    <div><span>主責單位</span><strong>${esc(analysis.responsible_department || '待確認')}</strong></div>
                </div>
                <section class="d-brief"><h4>摘要</h4><p>${esc(summary)}</p></section>
                <section class="d-case-section"><h4>監理要點</h4>${points.length ? `<ol>${points.map(point => `<li>${esc(point)}</li>`).join('')}</ol>` : '<p class="d-section-empty">尚未整理重點，請先參閱主管機關原文。</p>'}</section>
                <section class="d-case-section"><h4>應注意事項</h4>${attention.length ? `<ul>${attention.map(item => `<li>${esc(item)}</li>`).join('')}</ul>` : `<p class="d-section-empty">${aiComplete ? '目前沒有額外注意事項。' : '完成 AI 分析後會補充；目前請以原文為準。'}</p>`}</section>
                ${departments.length ? `<section class="d-case-section"><h4>受影響單位</h4><p class="d-departments">${departments.map(item => esc(item.department || item)).join('　/　')}</p></section>` : ''}
                ${processes.length ? `<section class="d-case-section"><h4>可能受影響流程</h4><ul>${processes.map(item => `<li>${esc(item.process || item)}</li>`).join('')}</ul></section>` : ''}
                ${actions.length ? `<section class="d-case-section d-next"><h4>建議處置</h4><ol>${actions.map(item => `<li>${esc(item)}</li>`).join('')}</ol></section>` : ''}
                <p class="d-provenance">${esc(analysis.analysis_mode || '初步分析')} · 請由公司專業人員確認適用性與法律效果。</p>
            </div>
        `;
    }

    const switcher = document.createElement('div');
    switcher.className = 'preview-switcher';
    switcher.setAttribute('role', 'group');
    switcher.setAttribute('aria-label', '介面原型方案切換');
    switcher.innerHTML = `
        <span class="preview-switcher-note">UI 預覽</span>
        <button type="button" data-preview-step="-1" aria-label="上一個方案">←</button>
        <strong data-preview-label></strong>
        <button type="button" data-preview-step="1" aria-label="下一個方案">→</button>
        <a href="/" aria-label="回到目前介面">目前介面 ↗</a>
    `;
    document.body.appendChild(switcher);

    const keys = Object.keys(variants);
    let active = initial;
    document.addEventListener('regintel:ai-analysis-state', event => {
        const { eventId, status } = event.detail || {};
        if (status === 'failed') dAnalysisFailures.add(eventId);
        else if (status === 'loading' || status === 'complete') dAnalysisFailures.delete(eventId);
        if (active === 'D' && eventId === dDisplayedEventId) renderD();
    });
    function setVariant(next) {
        active = next;
        document.body.dataset.uiPreview = next;
        if (next === 'D') dFilterHost.appendChild(advancedFilter);
        else originalFilterHost.appendChild(advancedFilter);
        switcher.querySelector('[data-preview-label]').textContent = `${next} · ${variants[next]}`;
        parameters.set('variant', next);
        history.replaceState(null, '', `${location.pathname}?${parameters}${location.hash}`);
        if (next === 'D') renderD();
    }
    function cycle(step) {
        setVariant(keys[(keys.indexOf(active) + step + keys.length) % keys.length]);
    }
    switcher.addEventListener('click', event => {
        const button = event.target.closest('[data-preview-step]');
        if (button) cycle(Number(button.dataset.previewStep));
    });
    document.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
        if (event.target.closest('input, textarea, select, [contenteditable]')) return;
        cycle(event.key === 'ArrowRight' ? 1 : -1);
    });
    setVariant(initial);

    function updateMetrics() {
        const events = state.events || [];
        intro.querySelector('[data-preview-count]').textContent = events.length || '—';
        intro.querySelector('[data-preview-high]').textContent = events.filter(event => event.analysis?.risk_level === '高').length;
        intro.querySelector('[data-preview-sources]').textContent = new Set(events.map(event => event.source_key).filter(Boolean)).size || '—';
    }
    new MutationObserver(() => {
        updateMetrics();
        if (active === 'D') renderD();
    }).observe(document.getElementById('eventList'), { childList: true });
    updateMetrics();
})();
