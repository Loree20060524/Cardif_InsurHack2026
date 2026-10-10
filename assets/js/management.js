/* User-selected sources for management summaries. */

function managementEvents(){
    return [...state.events].sort((a, b) => {
        const dateValue = event => new Date(event.published_at || event.detected_at || 0).getTime() || 0;
        return dateValue(b) - dateValue(a);
    });
}

function filteredManagementEvents(){
    const query = state.managementQuery.trim().toLowerCase();
    return managementEvents().filter(event => {
        if(state.managementType !== '全部' && sourceType(event) !== state.managementType) return false;
        const text = [event.title, event.source, event.description, event.analysis?.summary].join(' ').toLowerCase();
        return !query || text.includes(query);
    });
}

function selectedManagementEvents(){
    const byId = new Map(state.events.map(event => [event.id, event]));
    return [...state.managementSelection].map(id => byId.get(id)).filter(Boolean);
}

function updateManagementSelection(){
    const count = selectedManagementEvents().length;
    const matching = filteredManagementEvents();
    const visible = pageWindow('management', matching).items;
    const loading = state.managementReportLoading || state.history.loading;
    $('managementSelectionCount').textContent = `已選 ${count} 筆資訊 · 符合條件 ${matching.length} 筆`;
    $('managementSelectionHint').textContent = state.managementReportLoading
        ? `正在彙整已選擇的 ${count} 筆資訊，資料較多時需較長時間。`
        : state.history.loading ? '正在載入更早資料，已保留您的跨頁選取。'
        : count ? '摘要將使用所有勾選資訊；翻頁、搜尋或切換類型會保留已選項目。' : '可跨頁勾選資訊，再產生摘要。';
    $('reportBtn').disabled = loading || !count;
    $('reportBtn').textContent = state.managementReportLoading ? '產生中…' : '產生管理摘要';
    $('selectManagementVisible').disabled = loading || !visible.length || visible.every(event => state.managementSelection.has(event.id));
    $('clearManagementSelection').disabled = loading || !count;
    $('managementSearch').disabled = loading;
    $('managementTypeFilter').disabled = loading;
}

function renderManagementSelection(){
    const availableIds = new Set(state.events.map(event => event.id));
    state.managementSelection = new Set([...state.managementSelection].filter(id => availableIds.has(id)));
    const matching = filteredManagementEvents();
    const visible = pageWindow('management', matching).items;
    renderPagination('management', matching, renderManagementSelection);
    $('priorityList').innerHTML = visible.length ? visible.map(event => {
        const analysis = event.analysis || {};
        const selected = state.managementSelection.has(event.id);
        const meta = [formatEventDate(event), sourceType(event), event.source];
        if(['高', '中', '低'].includes(analysis.risk_level)) meta.push(`風險：${analysis.risk_level}`);
        if(['重大', '重要', '一般'].includes(analysis.importance)) meta.push(`重要性：${analysis.importance}`);
        return `<label class="management-selection-item ${selected ? 'selected' : ''}">
            <input type="checkbox" data-management-event="${esc(event.id)}" ${selected ? 'checked' : ''} ${state.managementReportLoading || state.history.loading ? 'disabled' : ''}>
            <span class="management-selection-copy"><strong>${esc(event.title)}</strong><small>${meta.map(esc).join(' · ')}</small></span>
        </label>`;
    }).join('') : '<div class="empty">沒有符合搜尋條件的資訊。</div>';
    $('priorityList').querySelectorAll('[data-management-event]').forEach(input => {
        input.onchange = () => {
            if(input.checked) state.managementSelection.add(input.dataset.managementEvent);
            else state.managementSelection.delete(input.dataset.managementEvent);
            input.closest('label').classList.toggle('selected', input.checked);
            updateManagementSelection();
        };
    });
    updateManagementSelection();
}

function renderManagement(){
    $('managementSearch').value = state.managementQuery;
    $('managementTypeFilter').value = state.managementType;
    $('managementSearch').oninput = event => {
        state.managementQuery = event.target.value;
        state.pagination.management.page = 1;
        renderManagementSelection();
    };
    $('managementTypeFilter').onchange = event => {
        state.managementType = event.target.value;
        state.pagination.management.page = 1;
        renderManagementSelection();
    };
    $('selectManagementVisible').onclick = () => {
        pageWindow('management', filteredManagementEvents()).items.forEach(event => state.managementSelection.add(event.id));
        renderManagementSelection();
    };
    $('clearManagementSelection').onclick = () => {
        state.managementSelection.clear();
        renderManagementSelection();
    };
    renderManagementSelection();
    renderTopics();
}

function renderTopics(){
    const topics = [
        ['招攬／公平待客', ['招攬', '公平待客', '適合度', '業務員']],
        ['資安／個資', ['資安', '個資', '資訊安全', '個人資料']],
        ['內控／法遵', ['內部控制', '法遵', '法令遵循', '稽核']],
        ['商品／精算', ['商品', '精算', '準備金', '費率']],
        ['資本／清償能力', ['清償能力', '資本適足', '風險資本', 'TIS', 'ICS']],
        ['投資管理', ['投資', '有價證券', '資產配置', '投資限額']],
    ];
    const counts = topics.map(([name, keywords]) => [name, state.events.filter(event => {
        const analysis = event.analysis || {};
        const text = [event.title, event.description, analysis.summary, ...(analysis.regulatory_points || []), ...(analysis.attention_items || [])].join(' ').toLowerCase();
        return keywords.some(keyword => text.includes(keyword.toLowerCase()));
    }).length]).sort((a, b) => b[1] - a[1]);
    const max = Math.max(1, ...counts.map(item => item[1]));
    $('trendList').innerHTML = counts.map(([name, count]) => `<div class="trend-row">
        <span>${esc(name)}</span><div class="track"><div class="fill" style="width:${Math.round(count / max * 100)}%"></div></div><b>${count}</b>
    </div>`).join('');
}

function managementSourceLink(event){
    try{
        const url = new URL(event.url);
        if(['http:', 'https:'].includes(url.protocol)) return `<a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">${esc(event.title)}</a>`;
    }catch(_){ /* A source without a valid URL still has a readable title. */ }
    return esc(event.title);
}

function renderManagementReport(report, sources){
    const events = Array.isArray(report.priority_events) ? report.priority_events : [];
    const actions = Array.isArray(report.priority_actions) ? report.priority_actions : [];
    const trends = Array.isArray(report.trend_observations) ? report.trend_observations : [];
    $('reportBox').innerHTML = `
        <div class="management-report-title">${esc(report.headline || '管理摘要')}</div>
        <p class="management-report-scope">本次摘要使用生成時勾選的 ${sources.length} 筆資訊。</p>
        <div class="management-overview">
            <div class="management-stat"><span>整體風險程度</span><b>${esc(report.risk_outlook || '待確認')}</b></div>
            <div class="management-stat"><span>納入資訊</span><b>${sources.length} 筆</b></div>
            <div class="management-stat"><span>監理趨勢觀察</span><b>${trends.length} 項</b></div>
        </div>
        <div class="management-section"><h3>管理重點</h3><div class="management-summary-text">${esc(report.summary || '目前尚無足夠資訊產生管理摘要。')}</div></div>
        <details class="management-section management-report-sources" open>
            <summary>本次納入資訊（${sources.length} 筆）</summary>
            <ol>${sources.map(event => `<li>${managementSourceLink(event)}<small>${esc(formatEventDate(event))} · ${esc(event.source || '')}</small></li>`).join('')}</ol>
        </details>
        ${events.length ? `<div class="management-section"><h3>AI 建議優先關注</h3>${events.map((item, index) => `
            <div class="management-event"><div class="management-event-number">${String(index + 1).padStart(2, '0')}</div>
            <div><b>${esc(item.title)}</b><p>${esc(item.reason || '請確認事件對公司的實際影響。')}</p></div></div>`).join('')}</div>` : ''}
        ${trends.length ? `<div class="management-section"><h3>監理趨勢觀察</h3>${trends.map(item => `<div class="trend-observation">${esc(item)}</div>`).join('')}</div>` : ''}
        ${actions.length ? `<div class="management-section"><h3>建議管理方向</h3><ul class="management-actions">${actions.map(item => `<li>${esc(item)}</li>`).join('')}</ul></div>` : ''}
        <div class="management-note"><b>系統說明：</b>${esc(report.management_note || '本摘要供管理階層初步參考，最終適用性仍需由相關單位確認。')}</div>`;
}

async function generateManagementReport(){
    if(state.managementReportLoading) return;
    const selected = selectedManagementEvents();
    if(!selected.length){ updateManagementSelection(); return; }
    const selectedIds = selected.map(event => event.id);
    const box = $('reportBox');
    state.managementReportLoading = true;
    renderManagementSelection();
    box.classList.remove('hidden');
    box.setAttribute('aria-busy', 'true');
    box.innerHTML = `<div class="management-report-title">管理摘要產生中…</div>
        <div class="management-summary-text">AI 正在彙整您勾選的 ${selected.length} 筆資訊，整理重點、可能影響與監理趨勢。</div>`;
    box.focus({preventScroll:true});
    box.scrollIntoView({block:'start'});
    try{
        const response = await fetch('/api/management-summary', {
            method:'POST', headers:{'Content-Type':'application/json'}, cache:'no-store',
            body:JSON.stringify({event_ids:selectedIds}),
        });
        const data = await response.json();
        if(!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
        const report = data.summary || {};
        const sources = Array.isArray(report.source_events) ? report.source_events : [];
        const returnedIds = new Set(sources.map(event => event.id));
        if(returnedIds.size !== selectedIds.length || selectedIds.some(id => !returnedIds.has(id))) throw new Error('摘要使用的資訊與所選項目不一致，請重新選取後產生。');
        renderManagementReport(report, sources);
    }catch(error){
        console.error(error);
        box.innerHTML = `<div class="management-report-title">管理摘要暫時無法產生</div>
            <div class="management-summary-text">${esc(error.message)}<br>已保留您的選取項目，可再次產生摘要。</div>`;
    }finally{
        state.managementReportLoading = false;
        box.setAttribute('aria-busy', 'false');
        renderManagementSelection();
        box.scrollIntoView({block:'start'});
    }
}
