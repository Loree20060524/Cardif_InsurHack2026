/* Single-question answers with server-checked passage quotations. */
let qaPending = false;

function qaOfficialLink(source){
    try{
        const url = new URL(source.url);
        if(!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return '';
        return `<a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">查看官方來源 ↗</a>`;
    }catch(_){ return ''; }
}

function renderQAAnswer(answer){
    const sources = new Map(answer.sources.map(source => [source.source_id, source]));
    const claims = answer.claims.map(item => `
        <article class="qa-claim">
            <span class="qa-kind ${item.kind === 'inference' ? 'is-inference' : ''}">${item.kind === 'inference' ? 'AI 推論' : '官方原文重點'}</span>
            <p>${esc(item.text)}</p>
            <details class="qa-evidence"><summary>查看原文依據（${item.citations.length}）</summary>
                ${item.citations.map(citation => {
                    const source = sources.get(citation.source_id);
                    if(!source) return '';
                    return `<div class="qa-source"><strong>${esc(source.title)}</strong>
                        <small>${esc(source.source)} · ${esc(source.date_label)}：${esc(source.date || '未提供')}</small>
                        <blockquote>${esc(citation.quote)}</blockquote>
                        ${source.version_note ? `<p class="qa-version-note">${esc(source.version_note)}</p>` : ''}
                        ${qaOfficialLink(source)}</div>`;
                }).join('')}
            </details>
        </article>`).join('');
    const missing = answer.missing_information.length ? `
        <aside class="qa-limitations"><strong>資料缺口與範圍提醒</strong>
            <ul>${answer.missing_information.map(value => `<li>${esc(value)}</li>`).join('')}</ul>
        </aside>` : '';
    const scope = answer.scope;
    const proposalNote = answer.sources.some(source => source.version_note?.startsWith('預告／草案'))
        ? '<p class="qa-version-note">本次搜尋資料包含預告／草案，不能視為已生效規範。</p>' : '';
    const references = answer.status !== 'answered' && answer.sources.length ? `
        <details class="qa-evidence"><summary>查看搜尋到的官方段落（${answer.sources.length}）</summary>
            ${answer.sources.map(source => `<div class="qa-source"><strong>${esc(source.title)}</strong>
                <small>${esc(source.date_label)}：${esc(source.date || '未提供')}</small>
                <blockquote>${esc(source.text)}</blockquote>${qaOfficialLink(source)}</div>`).join('')}
        </details>` : '';
    $('qaResult').innerHTML = `
        <div class="qa-result-heading"><h3>${answer.status === 'answered' ? '回答與依據' : '目前資料不足'}</h3>
            <small>耗時 ${Number(answer.timing.total_seconds).toFixed(1)} 秒</small></div>
        <p class="qa-asked">${esc(answer.question)}</p>
        <p class="qa-answer-scope">搜尋 ${scope.documents} 份已收錄資料，找到 ${scope.retrieved_documents} 份資料的 ${scope.passages} 個相關段落。
            ${esc(answer.filters.type)} · ${esc(answer.filters.date_from || '不限起日')} 至 ${esc(answer.filters.date_to || '不限迄日')}</p>
        ${proposalNote}${claims}${missing}${references}
        <p class="qa-footnote">引用摘錄已檢查是否出現在所列原文中；結論與引用的關係仍需核對。搜尋結果不代表完整法規或所有案件。</p>`;
}

async function submitRegulatoryQuestion(event){
    event.preventDefault();
    if(qaPending) return;
    const question = $('qaQuestion').value.trim();
    const filters = {type:$('qaType').value, date_from:$('qaDateFrom').value, date_to:$('qaDateTo').value};
    if(question.length < 2 || question.length > 500){
        $('qaStatus').textContent = '請輸入 2 至 500 字的監理問題。';
        $('qaQuestion').focus();
        return;
    }
    if(filters.date_from && filters.date_to && filters.date_from > filters.date_to){
        $('qaStatus').textContent = '開始日期不能晚於結束日期。';
        return;
    }
    qaPending = true;
    const controls = ['qaQuestion', 'qaType', 'qaDateFrom', 'qaDateTo', 'qaSubmit'];
    controls.forEach(id => {$(id).disabled = true;});
    $('qaSubmit').textContent = '回答中…';
    $('qaStatus').textContent = '正在搜尋官方資料並整理回答，首次查詢可能需要較長時間。';
    $('qaResult').setAttribute('aria-busy', 'true');
    try{
        const response = await fetch('/api/regulatory-qa', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({question, filters}),
        });
        const payload = await response.json();
        if(!response.ok || !payload.ok) throw new Error(payload.error || '監理問答暫時無法完成，請稍後再試。');
        renderQAAnswer(payload.answer);
        $('qaStatus').textContent = payload.answer.status === 'answered' ? '回答完成，可展開原文依據核對。' : '未取得足夠依據，請查看資料缺口。';
        if(state.view === 'qa') $('qaResult').focus({preventScroll:true});
    }catch(error){
        $('qaStatus').textContent = error.message;
    }finally{
        qaPending = false;
        controls.forEach(id => {$(id).disabled = false;});
        $('qaSubmit').textContent = '送出問題';
        $('qaResult').setAttribute('aria-busy', 'false');
    }
}

$('qaForm').addEventListener('submit', submitRegulatoryQuestion);
