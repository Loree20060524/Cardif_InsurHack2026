/* Shared pagination and on-demand official history for both source lists. */

function pageWindow(view, events){
    const paging = state.pagination[view];
    const pages = Math.max(1, Math.ceil(events.length / paging.size));
    paging.page = Math.max(1, Math.min(paging.page, pages));
    const start = (paging.page - 1) * paging.size;
    return {items:events.slice(start, start + paging.size), start, pages};
}

function archiveSources(view){
    const byType = {'公告':'fsc_announcement', '裁罰':'fsc_penalty', '監理新聞':'reg_news'};
    return Object.entries(byType).filter(([name, key]) => {
        if(view === 'management' && state.managementType !== '全部' && state.managementType !== name) return false;
        if(view === 'intel' && state.filters.types.size && !state.filters.types.has(name)) return false;
        return state.history.sources[key]?.has_more !== false;
    }).map(([, key]) => key);
}

function renderPagination(view, events, onPageChange){
    const element = $(view === 'intel' ? 'eventPagination' : 'managementPagination');
    const title = view === 'intel' ? '監理資訊清單' : '摘要資訊';
    const paging = state.pagination[view];
    const {start, items, pages} = pageWindow(view, events);
    const busy = state.history.loading;
    const disabled = busy ? 'disabled' : '';
    const historyKeys = archiveSources(view);
    element.innerHTML = `
        <div class="pagination-summary">
            <span aria-live="polite">${events.length ? `第 ${start + 1}–${start + items.length} 筆，共 ${events.length} 筆` : '目前沒有符合條件的資料'}</span>
            <label>每頁 <select data-page-size aria-label="${title}每頁筆數" ${disabled}>
                ${[25, 50, 100].map(size => `<option value="${size}" ${size === paging.size ? 'selected' : ''}>${size} 筆</option>`).join('')}
            </select></label>
        </div>
        <div class="pagination-actions">
            <div class="pagination-navigation">
                <button type="button" data-page-prev ${busy || paging.page === 1 ? 'disabled' : ''}>上一頁</button>
                <label>第 <select data-page-jump aria-label="${title}頁碼" ${disabled}>
                    ${Array.from({length:pages}, (_, index) => `<option value="${index + 1}" ${index + 1 === paging.page ? 'selected' : ''}>${index + 1}</option>`).join('')}
                </select> / ${pages} 頁</label>
                <button type="button" data-page-next ${busy || paging.page === pages ? 'disabled' : ''}>下一頁</button>
            </div>
            ${historyKeys.length ? `<button type="button" class="pagination-history" data-load-history ${busy || state.managementReportLoading ? 'disabled' : ''}>${state.history.loading ? '載入中…' : '載入更早資料'}</button>` : ''}
        </div>`;
    const changePage = page => {
        paging.page = page;
        onPageChange();
        $(view === 'intel' ? 'eventList' : 'priorityList').scrollTop = 0;
    };
    element.querySelector('[data-page-prev]').onclick = () => changePage(paging.page - 1);
    element.querySelector('[data-page-next]').onclick = () => changePage(paging.page + 1);
    element.querySelector('[data-page-jump]').onchange = event => changePage(Number(event.target.value));
    element.querySelector('[data-page-size]').onchange = event => {
        paging.size = Number(event.target.value);
        changePage(Math.floor(start / paging.size) + 1);
    };
    const historyButton = element.querySelector('[data-load-history]');
    if(historyButton) historyButton.onclick = () => loadOlderEvents(view);
}

async function loadOlderEvents(view){
    if(state.history.loading || state.managementReportLoading) return;
    const sources = archiveSources(view);
    if(!sources.length) return;
    const knownIds = new Set(state.events.map(event => event.id));
    state.history.loading = true;
    renderList();
    renderManagementSelection();
    try{
        const response = await fetch('/api/events/history', {
            method:'POST', headers:{'Content-Type':'application/json'}, cache:'no-store',
            body:JSON.stringify({source_keys:sources}),
        });
        const data = await response.json();
        if(!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
        const previous = new Map(state.events.map(event => [event.id, event]));
        state.events = data.events.map(event => {
            const old = previous.get(event.id);
            return old?.analysis?.analysis_mode === 'AI 深度分析'
                ? {...event, analysis:old.analysis, title:old.title, url:old.url, description:old.description}
                : event;
        });
        state.history.sources = data.history?.sources || {};
        state.sources = data.sources || state.sources;
        state.lastSync = data.last_sync;
        state.stale = !!data.stale;
        const matching = view === 'management' ? filteredManagementEvents() : ledgerEvents();
        const firstNew = matching.findIndex(event => !knownIds.has(event.id));
        if(firstNew >= 0){
            state.pagination[view].page = Math.floor(firstNew / state.pagination[view].size) + 1;
            if(view === 'intel') state.selected = matching[firstNew].id;
        }
        const added = state.events.filter(event => !knownIds.has(event.id)).length;
        const errors = data.history_result?.errors || [];
        if(errors.length){
            toast(`${added ? `已新增 ${added} 筆；` : ''}部分來源暫時無法載入，可再試一次。`);
            console.error('歷史資料讀取：', errors.join('；'));
        }else{
            toast(added ? `已新增 ${added} 筆官方資料。` : '本批資料已在清單中，可繼續載入更早資料。');
        }
    }catch(error){
        console.error(error);
        toast(error.message || '歷史資料暫時無法載入，請再試一次。');
    }finally{
        state.history.loading = false;
        renderList();
        if(view === 'intel') renderDetail();
        renderManagementSelection();
        renderTopics();
        renderSources();
    }
}
