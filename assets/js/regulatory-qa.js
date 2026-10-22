/* One regulatory assistant for questions, workplace situations and follow-up details. */
let qaPending = false;
let qaHistory = [];
let qaNeedsClarification = false;
const QA_MAX_TURNS = 6;

function updateQAUI(){
    const exhausted = qaHistory.length >= QA_MAX_TURNS;
    $('qaInputLabel').textContent = qaNeedsClarification ? '補充資訊' : (qaHistory.length ? '接續提問' : '問題或工作情境');
    $('qaNewQuestion').disabled = qaPending;
    if($('qaExamples')){
        $('qaExamples').hidden = Boolean(qaHistory.length);
        $('qaExamples').querySelectorAll('button').forEach(button => {button.disabled = qaPending;});
    }
    $('qaScopeNote').textContent = '依已收錄的官方資料回答。同一問題可繼續補充，最多六次；請勿輸入客戶個資。';
    $('qaQuestion').placeholder = qaHistory.length
        ? '可回答追問或接續補充；不同主題請按「開始新問題」。'
        : '例如：把保戶名單交給委外客服提醒繳費，需要注意哪些規定？';
    $('qaQuestion').disabled = qaPending || exhausted;
    $('qaSubmit').disabled = qaPending || exhausted;
    $('qaSubmit').textContent = qaPending ? '處理中…' : (qaNeedsClarification ? '補充並繼續' : (qaHistory.length ? '繼續詢問' : '送出問題'));
    $('qaResult').querySelectorAll('[data-qa-reply]').forEach(button => {button.disabled = qaPending || exhausted;});
    if(exhausted) $('qaStatus').textContent = '本次已達六次輸入，請按「開始新問題」繼續。';
    renderQAConversation();
}

function renderQAConversation(){
    const element = $('qaConversation');
    if(!element) return;
    element.hidden = !qaHistory.length;
    element.innerHTML = qaHistory.map((turn, index) => `
        <div class="qa-turn"><strong>你的${index ? '補充' : '提問'}</strong><p>${esc(turn.question)}</p></div>
        ${turn.follow_up_questions.length ? `<div class="qa-turn is-assistant"><strong>需要釐清</strong><ul>${turn.follow_up_questions.map(text => `<li>${esc(text)}</li>`).join('')}</ul></div>` : ''}
    `).join('');
    element.scrollTop = element.scrollHeight;
}

function resetQAConversation(){
    if(qaPending) return;
    qaHistory = [];
    qaNeedsClarification = false;
    $('qaQuestion').value = '';
    $('qaStatus').textContent = '';
    $('qaResult').innerHTML = '<div class="qa-empty"><strong>開始新問題</strong><p>輸入問題或說明工作內容，即可查詢相關法規。</p></div>';
    updateQAUI();
    $('qaQuestion').focus();
}

function qaOfficialLink(source){
    try{
        const url = new URL(source.url);
        if(!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return '';
        return `<a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">查看官方來源 ↗</a>`;
    }catch(_){ return ''; }
}

function qaEvidence(citations, sources){
    return `<details class="qa-evidence"><summary>引用原文（${citations.length}）</summary>
        ${citations.map(citation => {
            const source = sources.get(citation.source_id);
            if(!source) return '';
            return `<div class="qa-source"><strong>${esc(source.title)}</strong>
                <small>${esc(source.type || '官方資料')} · ${esc(source.source)} · ${esc(source.date_label)}：${esc(source.date || '未提供')}</small>
                <blockquote>${esc(citation.quote)}</blockquote>
                ${source.version_note ? `<p class="qa-version-note">${esc(source.version_note)}</p>` : ''}
                ${qaOfficialLink(source)}</div>`;
        }).join('')}</details>`;
}

function qaAnswerDocuments(answer, conversation){
    const sources = new Map(answer.sources.map(source => [source.source_id, source]));
    const documents = new Map();
    for(const claim of [...answer.claims, ...(conversation?.next_steps || [])]){
        for(const citation of claim.citations){
            const source = sources.get(citation.source_id);
            if(!source) continue;
            const key = source.document_id || source.title;
            if(!documents.has(key)) documents.set(key, {source, quotes:new Set(), sourceIds:new Set(), number:documents.size + 1});
            const item = documents.get(key);
            item.quotes.add(citation.quote);
            item.sourceIds.add(citation.source_id);
        }
    }
    return {sources, documents:[...documents.values()]};
}

function qaPointDocuments(point, documents){
    return documents.filter(item => point.citations.some(citation => item.sourceIds.has(citation.source_id)));
}

function renderQARegulations(documents, points, prefix){
    const fullLaw = item => item.source.document_id?.startsWith('law:') && item.source.type === '法規';
    const render = (title, items) => items.length ? `<section class="qa-regulations"><h4>${title}</h4>${items.map(item=>{
        const {source,quotes,number} = item;
        const related = points.flatMap((point,index) => qaPointDocuments(point,[item]).length ? [index + 1] : []);
        const draft = source.version_note?.startsWith('預告／草案');
        return `<article class="qa-regulation" id="${prefix}-source-${number}">
            <div class="qa-regulation-heading"><span class="qa-source-number">${number}</span><strong>${esc(source.title)}</strong><span class="qa-kind ${draft ? 'is-draft' : ''}">${draft ? '預告／草案' : esc(source.type || '官方資料')}</span></div>
            ${related.length ? `<p class="qa-related-points">對應回答：${related.map(index=>`<a href="#${prefix}-point-${index}">第 ${index} 點</a>`).join('、')}</p>` : ''}
            <details class="qa-regulation-evidence"><summary>引用原文與版本</summary>
                ${[...quotes].map(quote=>`<blockquote>${esc(quote)}</blockquote>`).join('')}
                <small>${esc(source.source || '官方來源')} · ${esc(source.date_label || '日期')}：${esc(source.date || '未提供')}</small>
                ${source.version_note ? `<p class="qa-version-note">${esc(source.version_note)}</p>` : ''}${qaOfficialLink(source)}
            </details></article>`;
    }).join('')}</section>` : '';
    return render('法規依據',documents.filter(fullLaw)) + render('其他官方資料',documents.filter(item=>!fullLaw(item)));
}

function qaUniqueText(items){
    return [...new Set(items.filter(text => typeof text === 'string' && text.trim()).map(text=>text.trim()))];
}

function renderQAAnswer(answer, targetId = 'qaResult'){
    const conversation = answer.conversation || answer.scenario;
    const prefix = targetId.replace(/[^a-zA-Z0-9_-]/g,'-');
    const {sources,documents} = qaAnswerDocuments(answer,conversation);
    const inferences = answer.claims.filter(item=>item.kind === 'inference');
    const points = inferences.length ? inferences : answer.claims.filter(item=>item.kind === 'fact');
    const followups = conversation?.follow_up_questions || [];
    const steps = conversation?.next_steps || [];
    const missing = qaUniqueText(answer.missing_information);
    const isNotice = text => /^(部分結論|部分回答的來源|部分推論或建議的來源|部分境外內容|部分內容未通過|已省略與已知境內|請核對法規完整條文)/.test(text);
    const gaps = missing.filter(text=>!isNotice(text));
    const notes = missing.filter(isNotice);
    if(answer.sources.some(source=>source.version_note?.startsWith('預告／草案'))) notes.push('查到的資料包含預告或草案，請確認是否已生效。');
    if(documents.length && !documents.some(item=>item.source.document_id?.startsWith('law:') && item.source.type === '法規')) notes.push('目前未引用完整法規原文，請核對正式條文及適用條件。');
    const review = answer.support_review;
    const summary = `<section class="qa-answer-panel">
        <div class="qa-result-heading"><h3>${followups.length ? '請補充以下資訊' : (points.length ? (inferences.length ? '回答' : '原文摘錄') : '資料不足')}</h3>${points.length ? `<span class="qa-kind ${inferences.length ? 'is-inference' : ''}">${inferences.length ? 'AI 推論' : '官方原文'}</span>` : ''}</div>
        ${followups.length ? `<ol class="qa-answer-list">${followups.map(text=>`<li>${esc(text)}</li>`).join('')}</ol>` : (points.length ? `<ol class="qa-answer-list">${points.map((point,index)=>`<li id="${prefix}-point-${index+1}"><p>${esc(point.text)}</p><span class="qa-point-sources">${qaPointDocuments(point,documents).map(item=>`<a href="#${prefix}-source-${item.number}" aria-label="查看${esc(item.source.title)}的依據">依據 ${item.number}</a>`).join('')}</span></li>`).join('')}</ol>` : '<p class="qa-answer-empty">目前沒有足夠的官方原文可回答這個問題。</p>')}
        ${review?.supported ? '<p class="qa-review-note">推論與建議另經模型核對原文。</p>' : ''}
    </section>`;
    const pending = steps.length || gaps.length ? `<section class="qa-pending-panel"><h4>待確認事項</h4>
        ${steps.length ? `<h5>建議做法</h5><ol class="qa-action-list">${steps.map(item=>`<li><p>${esc(item.text)}</p>${qaEvidence(item.citations,sources)}</li>`).join('')}</ol>` : ''}
        ${gaps.length ? `<h5>${steps.length ? '尚缺資料' : '需要補充或核對'}</h5><ul class="qa-gap-list">${gaps.map(text=>`<li>${esc(text)}</li>`).join('')}</ul>` : ''}
    </section>` : '';
    const notices = notes.length ? `<aside class="qa-answer-notes" aria-label="回答備註"><strong>備註</strong><ul>${qaUniqueText(notes).map(text=>`<li>${esc(text)}</li>`).join('')}</ul></aside>` : '';
    const scope = answer.scope;
    const scopeText = answer.status === 'clarify'
        ? `第 ${Number(conversation.turn)}／${Number(conversation.max_turns)} 次輸入 · 等待補充，尚未查詢法規。`
        : `搜尋 ${scope.documents} 份已收錄資料，找到 ${scope.retrieved_documents} 份資料的 ${scope.passages} 個相關段落。
            ${esc(answer.filters.type)} · ${esc(answer.filters.date_from || '不限起日')} 至 ${esc(answer.filters.date_to || '不限迄日')}`;
    const references = answer.status !== 'answered' && answer.sources.length ? `
        <details class="qa-unanswered-sources"><summary>查到的資料（${answer.sources.length}）</summary>
            ${answer.sources.map(source => `<div class="qa-source"><strong>${esc(source.title)}</strong>
                <small>${esc(source.date_label)}：${esc(source.date || '未提供')}</small>
                <blockquote>${esc(source.text)}</blockquote>${qaOfficialLink(source)}</div>`).join('')}
        </details>` : '';
    $(targetId).innerHTML = `
        ${summary}${notices}${pending}${renderQARegulations(documents,points,prefix)}${references}
        <details class="qa-query-details"><summary>查詢詳情</summary>
            <h4>你的問題</h4><p>${esc(answer.question)}</p>
            ${conversation?.summary && conversation.summary !== answer.question ? `<h4>問題摘要</h4><p>${esc(conversation.summary)}</p>` : ''}
            <p>${scopeText}</p><p>查詢耗時 ${Number(answer.timing.total_seconds).toFixed(1)} 秒</p>
            ${review?.requested ? `<h4>依據核對</h4><p>核對 ${Number(review.requested)} 項，保留 ${Number(review.supported)} 項，省略 ${Number(review.withheld)} 項。採模型判讀、條件及金額檢查，仍需確認法規適用性。</p>` : ''}
        </details>
        <div class="qa-answer-footer"><p>法規是否適用，仍須依實際情況及正式條文確認。</p><button type="button" data-qa-reply>${followups.length ? '補充資訊' : '繼續詢問'}</button></div>`;
}

async function submitRegulatoryQuestion(event){
    event.preventDefault();
    if(qaPending) return;
    if(qaHistory.length >= QA_MAX_TURNS){ updateQAUI(); return; }
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
    updateQAUI();
    $('qaStatus').textContent = '查詢中，請稍候。';
    $('qaResult').setAttribute('aria-busy', 'true');
    try{
        const body = {question, filters, mode:'auto', history:qaHistory};
        const response = await fetch('/api/regulatory-qa', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify(body),
        });
        const payload = await response.json();
        if(!response.ok || !payload.ok) throw new Error(payload.error || '監理問答暫時無法完成，請稍後再試。');
        renderQAAnswer(payload.answer);
        const conversation = payload.answer.conversation || payload.answer.scenario;
        qaHistory.push({question, follow_up_questions:conversation?.follow_up_questions || []});
        qaNeedsClarification = payload.answer.status === 'clarify';
        $('qaQuestion').value = '';
        $('qaStatus').textContent = payload.answer.status === 'clarify' ? '請補充下列資訊後再送出。' : (payload.answer.status === 'answered' ? '回答已更新，可點開引用原文查看依據。' : '目前資料不足，請查看待確認事項。');
        if(state.view === 'qa'){
            $('qaResult').focus({preventScroll:true});
            $('qaResult').scrollIntoView?.({block:'start'});
        }
    }catch(error){
        $('qaStatus').textContent = error.message;
    }finally{
        qaPending = false;
        controls.forEach(id => {$(id).disabled = false;});
        updateQAUI();
        $('qaResult').setAttribute('aria-busy', 'false');
    }
}

$('qaForm').addEventListener('submit', submitRegulatoryQuestion);
$('qaNewQuestion').addEventListener('click', resetQAConversation);
$('qaResult').addEventListener('click', event => {
    if(!event.target.closest('[data-qa-reply]') || qaPending || qaHistory.length >= QA_MAX_TURNS) return;
    $('qaQuestion').focus();
});
$('qaExamples')?.addEventListener('click', event => {
    const button = event.target.closest('button[data-example]');
    if(!button || qaPending) return;
    resetQAConversation();
    $('qaQuestion').value = button.dataset.example;
    $('qaQuestion').focus();
});
updateQAUI();
