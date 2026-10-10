/* Official text comparisons stay separate from AI interpretation. */
const lawComparisonState = new Map();

function canCompareLaw(event){
    const title = event?.title || '';
    return !/草案|預告|\.(?:pdf|odt|docx?)$/i.test(title)
        && (['insurance_law', 'law_db'].includes(event?.source_key)
            || /修正|增訂|刪除|訂定/.test(title));
}

function lawComparisonEntry(event){
    if(!lawComparisonState.has(event.id)){
        lawComparisonState.set(event.id, {open:false, loading:false, data:null, error:'', articles:new Set()});
    }
    return lawComparisonState.get(event.id);
}

function lawSourceLink(url, label){
    try{
        const target = new URL(url);
        if(target.protocol !== 'https:' || target.hostname !== 'law.fsc.gov.tw' || target.username || target.password) return '';
        return `<a class="source-link" href="${esc(target.href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
    }catch{return '';}
}

function comparisonText(segments, text, side){
    if(!text) return '<span class="law-comparison-absent">此版本無此條次</span>';
    if(!Array.isArray(segments) || !segments.length) return esc(text);
    return segments.map(part => part.changed
        ? `<${side === 'before' ? 'del' : 'ins'}>${esc(part.text)}</${side === 'before' ? 'del' : 'ins'}>`
        : esc(part.text)).join('');
}

function renderLawComparisonBody(event, entry){
    if(entry.loading) return '<p class="law-comparison-note" role="status">正在讀取官方版本並比對條文…</p>';
    if(entry.error) return `<p class="law-comparison-note" role="status">${esc(entry.error)}</p><button type="button" class="ghost" data-law-comparison-retry>重新讀取</button>`;
    if(!entry.data) return '<p class="law-comparison-note">展開後讀取可取得的官方前後版本。</p>';
    if(!entry.data.length) return '<p class="law-comparison-note">目前未找到可配對的法規版本，請查閱公告所附官方文件。</p>';
    const labels = {added:'新增', deleted:'刪除', modified:'修正'};
    const ready = entry.data.filter(item => item.status === 'ready' && item.changes.length);
    const analyzed = event.analysis?.law_comparison_signatures || [];
    const needsAnalysis = ready.some(item => !analyzed.includes(item.signature));
    return entry.data.map(item => {
        const before = item.before_version, after = item.after_version;
        const changes = item.changes || [];
        return `<section class="law-comparison-law">
            <h4>${esc(item.name)}</h4>
            ${after ? `<div class="law-comparison-versions">
                <span>前版：${esc(before?.date || '尚未取得')} ${before ? lawSourceLink(before.url, '原文') : ''}</span>
                <span>後版：${esc(after.date)} ${lawSourceLink(after.url, '原文')}</span>
            </div>` : ''}
            <p class="law-comparison-note">${esc(item.note || '')}</p>
            ${item.fetch_note ? `<p class="law-comparison-note">${esc(item.fetch_note)}</p>` : ''}
            ${item.status === 'ready' ? `<p class="law-comparison-scope">${esc(item.scope_note)}</p>
                <p class="law-comparison-counts">新增 ${Number(item.counts.added) || 0} 條 · 修正 ${Number(item.counts.modified) || 0} 條 · 刪除 ${Number(item.counts.deleted) || 0} 條</p>
                ${changes.length ? changes.map(change => {
                    const key = `${item.law_key}:${change.article}`;
                    return `<details class="law-article-change" data-law-article="${esc(key)}" ${entry.articles.has(key) ? 'open' : ''}>
                        <summary>${esc(change.article)}<span class="law-change-kind">${esc(labels[change.kind] || '差異')}</span></summary>
                        <div class="law-comparison-columns">
                            <div><h5>修正前</h5><p>${comparisonText(change.before_segments, change.before, 'before')}</p></div>
                            <div><h5>修正後</h5><p>${comparisonText(change.after_segments, change.after, 'after')}</p></div>
                        </div>
                    </details>`;
                }).join('') : '<p class="law-comparison-note">兩個版本未發現條文文字差異；附件、格式表及生效安排仍請查閱官方文件。</p>'}` : ''}
            ${(item.attachments || []).filter(link => /對照|說明/.test(link.title)).map(link => `<div class="law-comparison-attachment">${lawSourceLink(link.url, link.title)}</div>`).join('')}
            ${item.can_fetch && (item.status !== 'ready' || item.fetch_note) ? '<button type="button" class="ghost" data-law-comparison-retry>重新讀取官方版本</button>' : ''}
        </section>`;
    }).join('') + (ready.length ? `<div class="law-comparison-analysis">
        <p class="law-comparison-note">${needsAnalysis ? '可將已取得的條文差異納入 AI 分析。' : '目前 AI 分析已使用這組對照的差異節錄。'}部門影響與因應建議屬初步推論。</p>
        ${state.ai.enabled && needsAnalysis ? `<button type="button" class="ghost" data-law-comparison-analyze ${state.aiLoading.has(event.id) ? 'disabled' : ''}>依條文差異重新分析</button>` : ''}
    </div>` : '');
}

function renderLawComparisonSection(event){
    if(!canCompareLaw(event)) return '';
    const entry = lawComparisonEntry(event);
    return `<details id="lawComparison" class="block law-comparison" ${entry.open ? 'open' : ''}>
        <summary>修正前後對照</summary>
        <div id="lawComparisonBody">${renderLawComparisonBody(event, entry)}</div>
    </details>`;
}

function bindLawComparisonBody(event){
    const container = $('lawComparisonBody');
    if(!container) return;
    const entry = lawComparisonEntry(event);
    container.querySelectorAll('[data-law-comparison-retry]').forEach(button => button.addEventListener('click', () => loadLawComparison(event, true)));
    container.querySelector('[data-law-comparison-analyze]')?.addEventListener('click', () => {
        ensureAIAnalysis(event, true);
        updateLawComparisonBody(event);
    });
    container.querySelectorAll('[data-law-article]').forEach(article => article.addEventListener('toggle', () => {
        const key = article.dataset.lawArticle;
        if(article.open) entry.articles.add(key); else entry.articles.delete(key);
    }));
}

function updateLawComparisonBody(event){
    if(state.selected !== event.id || !$('lawComparisonBody')) return;
    $('lawComparisonBody').innerHTML = renderLawComparisonBody(event, lawComparisonEntry(event));
    bindLawComparisonBody(event);
}

async function loadLawComparison(event, retry=false){
    const entry = lawComparisonEntry(event);
    if(entry.loading || (!retry && entry.data !== null)) return;
    entry.loading = true;
    entry.error = '';
    updateLawComparisonBody(event);
    try{
        const response = await fetch(`/api/law-comparison?id=${encodeURIComponent(event.id)}`, {cache:'no-store'});
        const result = await response.json();
        if(!response.ok || !result.ok || !Array.isArray(result.comparisons)) throw new Error('comparison unavailable');
        entry.data = result.comparisons;
    }catch{
        entry.error = '官方版本暫時無法讀取，請稍後重試。';
    }finally{
        entry.loading = false;
        updateLawComparisonBody(event);
    }
}

function bindLawComparison(event){
    const section = $('lawComparison');
    if(!section) return;
    const entry = lawComparisonEntry(event);
    section.addEventListener('toggle', () => {
        entry.open = section.open;
        if(section.open) loadLawComparison(event);
    });
    bindLawComparisonBody(event);
    if(entry.open) loadLawComparison(event);
}
