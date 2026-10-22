/* Theme 4: natural-language company knowledge, files and IT support. */
const enterpriseState = {catalog:null, loading:false, pending:false, lastSearch:null};

async function initializeEnterpriseKnowledge(){
    if(enterpriseState.catalog || enterpriseState.loading) return;
    enterpriseState.loading = true;
    try{
        const response = await fetch('/api/enterprise-knowledge', {cache:'no-store'});
        const payload = await response.json();
        if(!response.ok || !payload.ok) throw new Error(payload.error || '無法載入企業知識庫。');
        enterpriseState.catalog = payload.catalog;
        renderEnterpriseWorkspace();
    }catch(error){
        $('enterpriseKnowledge').innerHTML = `<div class="qa-limitations"><strong>知識庫尚未載入</strong><p>${esc(error.message)}</p><button type="button" id="ekReload">重新載入</button></div>`;
        $('ekReload').addEventListener('click', initializeEnterpriseKnowledge);
    }finally{ enterpriseState.loading = false; }
}

function enterpriseLink(url){
    return typeof url === 'string' && url.startsWith('/api/enterprise-knowledge/document?id=') ? esc(url) : '#';
}

function renderEnterpriseWorkspace(){
    const catalog = enterpriseState.catalog;
    $('enterpriseKnowledge').innerHTML = `
        <header class="ek-heading"><span>企業專屬知識 · 自建示範</span><h3>企業知識與 IT 支援助手</h3><p>描述你要做的事或遇到的問題，找到相關文件、作業方式與可參考的解法。</p></header>
        <div class="ek-layout"><div>
            <form id="ekForm" class="ek-card"><label class="ek-label" for="ekQuestion">想找什麼，或卡在哪裡？</label>
                <textarea id="ekQuestion" rows="3" required minlength="2" maxlength="500" placeholder="例如：要把客戶資料交給合作廠商，應查哪份 SOP 和表單？或是 VPN 連不上，先怎麼排查？" aria-describedby="ekScope"></textarea>
                <div class="ek-submit"><label for="ekCategory">知識類型<select id="ekCategory"><option>全部</option>${catalog.categories.map(kind=>`<option>${esc(kind)}</option>`).join('')}</select></label><button type="submit" id="ekSubmit">查詢知識並回答</button></div>
                <p id="ekScope">搜尋目前收錄的示範企業文件。請勿輸入客戶個資、密碼或驗證碼。</p><p id="ekStatus" role="status" aria-live="polite"></p>
                <div class="ek-examples" aria-label="範例問題"><span>試著問</span>${catalog.examples.map((question,index)=>`<button type="button" data-ek-example="${index}">${esc(question)}</button>`).join('')}</div>
            </form>
            <section class="ek-card" id="ekResult" aria-label="企業知識回答" tabindex="-1"><h3>從問題找到文件與作法</h3><p class="ek-muted">可詢問 SOP、表單、專業術語、新人常見問題，以及登入、密碼、網路與 VPN 問題。回答會附文件依據。</p></section>
            <section class="ek-card" id="ekMatches" aria-label="找到的相關文件" hidden></section>
        </div><aside class="ek-card ek-library" aria-label="示範知識庫"><div class="ek-library-title"><h3>示範知識庫</h3><span>${catalog.documents.length} 份文件</span></div><p>${esc(catalog.note)}</p><div id="ekLibraryList"></div></aside></div>`;
    $('ekForm').addEventListener('submit', submitEnterpriseQuestion);
    $('ekCategory').addEventListener('change', renderEnterpriseLibrary);
    $('ekForm').querySelectorAll('[data-ek-example]').forEach(button=>button.addEventListener('click', ()=>{
        if(enterpriseState.pending) return;
        $('ekQuestion').value = catalog.examples[Number(button.dataset.ekExample)];
        $('ekQuestion').focus();
    }));
    renderEnterpriseLibrary();
}

function renderEnterpriseLibrary(){
    const category = $('ekCategory').value || '全部';
    const documents = enterpriseState.catalog.documents.filter(item=>category === '全部' || item.category === category);
    $('ekLibraryList').innerHTML = documents.map(item=>`<article class="ek-file"><span>${esc(item.category)} · 示範</span><a href="${enterpriseLink(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)} ↗</a><small>${esc(item.number)} · v${esc(item.version)}</small><a class="ek-download" href="${enterpriseLink(item.download_url)}">下載文件 .txt</a></article>`).join('');
}

function renderEnterpriseMatches(result){
    const sources = result.sources || [];
    $('ekMatches').hidden = !sources.length;
    $('ekMatches').innerHTML = `<h3>找到的相關文件</h3><p class="ek-muted">${Number(result.documents)} 份文件 · ${sources.length} 個段落 · ${esc(result.category)}</p>
        ${sources.map(source=>`<article class="ek-match"><div><span>${esc(source.source_id)} · ${esc(source.category)} · 示範</span><a href="${enterpriseLink(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.title)} ↗</a></div><strong>${esc(source.section)}</strong><blockquote>${esc(source.text)}</blockquote><small>${esc(source.number)} · v${esc(source.version)} · ${esc(source.updated)}</small><a class="ek-download" href="${enterpriseLink(source.download_url)}">下載完整文件 .txt</a></article>`).join('')}`;
}

function enterpriseEvidence(item, sources){
    return (item.citations || []).map(citation=>{
        const source = sources.get(citation.source_id);
        if(!source) return '';
        return `<details class="ek-citation"><summary>查看依據 ${esc(citation.source_id)} · ${esc(source.title)}</summary><blockquote>${esc(citation.quote)}</blockquote><a href="${enterpriseLink(source.url)}" target="_blank" rel="noopener noreferrer">開啟文件原文 ↗</a></details>`;
    }).join('');
}

function renderEnterpriseAnswer(result){
    const sources = new Map((result.sources || []).map(item=>[item.source_id,item]));
    const points = result.points || [], steps = result.steps || [], followups = result.follow_up_questions || [];
    $('ekResult').innerHTML = `<div class="ek-answer-heading"><h3>${result.status === 'answered' ? '回答與作業方向' : '先從相關文件確認'}</h3><span>${result.status === 'answered' ? 'AI 整理 · 依示範文件' : '文件搜尋結果'}</span></div><p class="ek-asked">${esc(result.question)}</p>
        ${result.message ? `<p class="ek-message">${esc(result.message)}</p>` : ''}
        ${points.map(item=>`<article class="ek-point"><p>${esc(item.text)}</p>${enterpriseEvidence(item,sources)}</article>`).join('')}
        ${steps.length ? `<h4>可以先怎麼做</h4><ol class="ek-actions">${steps.map(item=>`<li><p>${esc(item.text)}</p>${enterpriseEvidence(item,sources)}</li>`).join('')}</ol>` : ''}
        ${followups.length ? `<div class="ek-followups"><strong>還需要釐清</strong><ul>${followups.map(text=>`<li>${esc(text)}</li>`).join('')}</ul><p>可將這些條件補進問題後再查詢。</p></div>` : ''}
        ${result.status === 'documents_only' && result.sources?.length ? '<button type="button" id="ekRetryAnswer">重新整理回答</button>' : ''}
        <p class="ek-muted">文件為自建示範；AI 引用已檢查逐字出處，內容與實際作業仍須核對。</p>`;
    $('ekRetryAnswer')?.addEventListener('click', ()=>askEnterpriseAI(enterpriseState.lastSearch));
}

function setEnterprisePending(pending){
    enterpriseState.pending = pending;
    for(const id of ['ekQuestion','ekCategory','ekSubmit']) $(id).disabled = pending;
    $('ekForm').querySelectorAll('[data-ek-example]').forEach(button=>{button.disabled=pending;});
    if($('ekRetryAnswer')) $('ekRetryAnswer').disabled = pending;
    $('ekSubmit').textContent = pending ? '查詢中…' : '查詢知識並回答';
    $('ekResult').setAttribute('aria-busy', String(pending));
}

async function askEnterpriseAI(searchResult){
    if(!searchResult || enterpriseState.pending) return;
    setEnterprisePending(true);
    $('ekStatus').textContent = '已找到相關文件，AI 正在整理回答；可先開啟下方文件。';
    try{
        const response = await fetch('/api/enterprise-knowledge/answer', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:searchResult.question,category:searchResult.category})});
        const payload = await response.json();
        if(!response.ok || !payload.ok) throw new Error(payload.error || 'AI 整理暫時無法完成。');
        renderEnterpriseAnswer(payload.result);
        $('ekStatus').textContent = payload.result.status === 'answered' ? '回答完成，可核對引用並開啟相關文件。' : '相關文件已找到；AI 狀態請見回答區。';
    }catch(error){
        renderEnterpriseAnswer({...searchResult,status:'documents_only',message:`${error.message} 你仍可查閱與下載已找到的文件。`});
        $('ekStatus').textContent = 'AI 整理未完成，文件搜尋結果已保留。';
    }finally{ setEnterprisePending(false); }
}

async function submitEnterpriseQuestion(event){
    event.preventDefault();
    if(enterpriseState.pending) return;
    const question = $('ekQuestion').value.trim(), category = $('ekCategory').value;
    if(question.length < 2 || question.length > 500){ $('ekStatus').textContent='請輸入 2 至 500 字的問題。'; return; }
    setEnterprisePending(true);
    $('ekStatus').textContent = '正在搜尋示範企業知識與文件…';
    $('ekResult').innerHTML = '<p class="ek-muted">正在找相關文件…</p>';
    $('ekMatches').hidden = true;
    enterpriseState.lastSearch = null;
    let result;
    try{
        const response = await fetch('/api/enterprise-knowledge/search', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,category})});
        const payload = await response.json();
        if(!response.ok || !payload.ok) throw new Error(payload.error || '企業知識搜尋暫時無法完成。');
        result = payload.result;
        enterpriseState.lastSearch = result;
        renderEnterpriseMatches(result);
        if(!result.sources.length){
            renderEnterpriseAnswer({...result,status:'not_found',message:'目前示範文件沒有足夠依據。可補充工作名稱、系統或錯誤訊息，或改查其他類型。'});
            $('ekStatus').textContent = '找不到相關文件，尚未呼叫 AI。';
        }else{
            $('ekResult').innerHTML = `<h3>已找到 ${Number(result.documents)} 份相關文件</h3><p class="ek-muted">AI 正在依文件整理回答，文件原文可先查閱。</p>`;
        }
    }catch(error){ $('ekStatus').textContent = error.message; $('ekResult').innerHTML = '<p class="ek-muted">搜尋未完成，可保留問題再試。</p>'; }
    finally{ setEnterprisePending(false); }
    if(result?.sources.length) await askEnterpriseAI(result);
}
