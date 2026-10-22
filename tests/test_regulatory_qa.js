const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function boot(fetch){
    const elements = Object.fromEntries(['qaForm','qaQuestion','qaType','qaDateFrom','qaDateTo','qaSubmit','qaStatus','qaResult',
        'qaInputLabel','qaNewQuestion','qaExamples','qaScopeNote','qaConversation'].map(id=>[id,{
        value:'',textContent:'',innerHTML:'',disabled:false,hidden:false,attributes:{},
        addEventListener(){},focus(){},setAttribute(name,value){this.attributes[name]=value;},
        querySelectorAll(){return [];},
    }]));
    elements.qaType.value='全部';
    const context=vm.createContext({document:{getElementById:id=>elements[id]},fetch,URL});
    for(const file of ['core.js','regulatory-qa.js']) vm.runInContext(fs.readFileSync(path.join(__dirname,'..','assets','js',file),'utf8'),context);
    vm.runInContext("state.view='qa';",context);
    return {elements,context,run:code=>vm.runInContext(code,context)};
}

function answer(status='answered'){
    const citation={source_id:'S1',quote:'測試原文指出應保存投資決策與覆核紀錄。'};
    return {mode:'auto',status,question:'投資內控',filters:{type:'全部',date_from:'',date_to:''},
        claims:status==='clarify' ? [] : [{text:'測試原文指出應保存投資決策與覆核紀錄。',kind:'fact',citations:[citation]},
            {text:'本問題涉及投資決策，可先核對覆核紀錄。',kind:'inference',citations:[citation]}],
        sources:status==='clarify' ? [] : [{source_id:'S1',document_id:'law:sample',type:'法規',title:'測試用投資管理規範',
            source:'官方法規原文',date:'2026-10-02',date_label:'修正／公布日期',url:'https://www.fsc.gov.tw/example?a=1&b=2'}],
        conversation:{summary:'整理使用者的問題與已知條件',follow_up_questions:status==='clarify' ? ['廠商將如何使用資料？'] : [],next_steps:[],turn:1,max_turns:6},
        missing_information:[],scope:{documents:20,retrieved_documents:status==='clarify'?0:1,passages:status==='clarify'?0:1},timing:{total_seconds:1.5}};
}

test('one answer view escapes model text, binds quotations to real documents and rejects unsafe links',()=>{
    const app=boot();
    const fixture=answer();
    fixture.claims[1].text='<img src=x onerror=alert(1)>';
    fixture.conversation.summary='<script>alert(1)</script>';
    app.context.fixture=fixture;
    app.run('renderQAAnswer(fixture)');
    const html=app.elements.qaResult.innerHTML;
    assert.doesNotMatch(html,/<img|<script>/);
    assert.match(html,/&lt;img/);
    assert.match(html,/測試原文指出應保存投資決策與覆核紀錄/);
    assert.match(html,/對應回答/);
    assert.match(html,/rel="noopener noreferrer"/);
    assert.equal(app.run("qaOfficialLink({url:'javascript:alert(1)'})"),'');
    assert.equal(app.run("qaOfficialLink({url:'https://user:password@example.com'})"),'');
});

test('every input uses the unified API with filters and history and duplicate submits are blocked',async()=>{
    let requests=0,body,resolve;
    const pending=new Promise(done=>{resolve=done;});
    const app=boot(async(_url,options)=>{requests++;body=JSON.parse(options.body);return pending;});
    app.elements.qaQuestion.value='投資內控';
    app.elements.qaDateFrom.value='2026-10-01';
    const operation=app.run('submitRegulatoryQuestion({preventDefault(){}})');
    await app.run('submitRegulatoryQuestion({preventDefault(){}})');
    assert.equal(requests,1);
    assert.equal(app.elements.qaNewQuestion.disabled,true);
    assert.equal(app.elements.qaSubmit.disabled,true);
    assert.deepEqual(body,{question:'投資內控',filters:{type:'全部',date_from:'2026-10-01',date_to:''},mode:'auto',history:[]});
    resolve({ok:true,json:async()=>({ok:true,answer:answer()})});
    await operation;
    assert.equal(app.elements.qaSubmit.disabled,false);
    assert.equal(app.elements.qaResult.attributes['aria-busy'],'false');
    assert.equal(app.elements.qaQuestion.value,'');
    assert.equal(app.run('qaHistory.length'),1);
    assert.equal(app.elements.qaSubmit.textContent,'繼續詢問');
    assert.match(app.elements.qaConversation.innerHTML,/投資內控/);
});

test('failed requests preserve the draft and conversation; invalid dates stop before the API',async()=>{
    let requests=0;
    const app=boot(async()=>{requests++;return {ok:false,json:async()=>({ok:false,error:'模型尚未啟動'})};});
    app.elements.qaQuestion.value='投資內控';
    await app.run('submitRegulatoryQuestion({preventDefault(){}})');
    assert.equal(app.elements.qaQuestion.value,'投資內控');
    assert.equal(app.run('qaHistory.length'),0);
    assert.equal(app.elements.qaSubmit.disabled,false);
    assert.equal(app.elements.qaStatus.textContent,'模型尚未啟動');
    app.elements.qaDateFrom.value='2026-10-02';
    app.elements.qaDateTo.value='2026-10-01';
    await app.run('submitRegulatoryQuestion({preventDefault(){}})');
    assert.equal(requests,1);
    assert.match(app.elements.qaStatus.textContent,/開始日期/);
});

test('necessary clarification and followup use the same entry; a new question clears prior context',async()=>{
    const bodies=[];
    const app=boot(async(_url,options)=>{
        bodies.push(JSON.parse(options.body));
        return {ok:true,json:async()=>({ok:true,answer:answer(bodies.length===1?'clarify':'answered')})};
    });
    app.elements.qaQuestion.value='我想把客戶名單交給廠商';
    await app.run('submitRegulatoryQuestion({preventDefault(){}})');
    assert.equal(bodies[0].mode,'auto');
    assert.match(app.elements.qaResult.innerHTML,/請補充以下資訊/);
    assert.equal(app.elements.qaSubmit.textContent,'補充並繼續');
    assert.equal(app.elements.qaExamples.hidden,true);
    app.elements.qaQuestion.value='只用於既有保戶服務';
    await app.run('submitRegulatoryQuestion({preventDefault(){}})');
    assert.deepEqual(bodies[1].history,[{question:'我想把客戶名單交給廠商',follow_up_questions:['廠商將如何使用資料？']}]);
    assert.match(app.elements.qaConversation.innerHTML,/只用於既有保戶服務/);
    assert.equal(app.elements.qaSubmit.textContent,'繼續詢問');
    app.elements.qaType.value='法規';
    app.run('resetQAConversation()');
    assert.equal(app.run('qaHistory.length'),0);
    assert.equal(app.elements.qaConversation.hidden,true);
    assert.equal(app.elements.qaExamples.hidden,false);
    assert.equal(app.elements.qaType.value,'法規');
    assert.doesNotMatch(app.elements.qaResult.innerHTML,/客戶名單/);
});

test('reset is blocked during a request and failed followups retain prior facts',async()=>{
    let resolve;
    const pending=new Promise(done=>{resolve=done;});
    const app=boot(async()=>pending);
    app.run("qaHistory=[{question:'先前的問題',follow_up_questions:['用途為何？']}];qaNeedsClarification=true;");
    app.elements.qaQuestion.value='這次的補充';
    const operation=app.run('submitRegulatoryQuestion({preventDefault(){}})');
    app.run('resetQAConversation()');
    assert.equal(app.run('qaHistory.length'),1);
    assert.equal(app.elements.qaQuestion.value,'這次的補充');
    resolve({ok:false,json:async()=>({ok:false,error:'模型暫時無法使用'})});
    await operation;
    assert.equal(app.elements.qaQuestion.value,'這次的補充');
    assert.equal(app.run('qaHistory.length'),1);
    assert.equal(app.elements.qaSubmit.textContent,'補充並繼續');
    assert.equal(app.elements.qaNewQuestion.disabled,false);
});

test('law and news evidence stay separate and uncited sources never appear as recommended laws',()=>{
    const app=boot();
    const fixture=answer();
    fixture.sources.push({...fixture.sources[0],source_id:'S2',document_id:'news:sample',type:'監理新聞',title:'測試用監理新聞'});
    fixture.sources.push({...fixture.sources[0],source_id:'S3',document_id:'law:uncited',title:'未引用的文件'});
    fixture.claims.push({kind:'fact',text:'測試用新聞摘錄。',citations:[{source_id:'S2',quote:'測試用新聞摘錄。'}]});
    fixture.conversation.next_steps=[{text:'核對尚未確認的投資覆核安排',citations:fixture.claims[0].citations}];
    app.context.fixture=fixture;
    app.run('renderQAAnswer(fixture)');
    const html=app.elements.qaResult.innerHTML;
    assert.match(html,/法規依據/);
    assert.match(html,/其他官方資料/);
    assert.match(html,/待確認事項/);
    assert.ok(html.indexOf('測試用監理新聞')>html.indexOf('其他官方資料'));
    assert.doesNotMatch(html,/未引用的文件|示範作業指引/);
});

test('answer comes before pending items and laws; details keep original questions out of the summary',()=>{
    const app=boot();
    const fixture=answer();
    fixture.question='這是完整的原問題';
    fixture.conversation.next_steps=[{text:'請核對覆核安排。',citations:fixture.claims[0].citations}];
    fixture.missing_information=['尚未提供投資標的。','尚未提供投資標的。'];
    app.context.fixture=fixture;
    app.run('renderQAAnswer(fixture)');
    const html=app.elements.qaResult.innerHTML;
    const sections=['qa-answer-panel','qa-pending-panel','qa-regulations','qa-query-details'];
    sections.forEach((name,index)=>{if(index) assert.ok(html.indexOf(name)>html.indexOf(sections[index-1]));});
    const summary=html.slice(0,html.indexOf('qa-pending-panel'));
    assert.match(summary,/本問題涉及投資決策/);
    assert.doesNotMatch(summary,/這是完整的原問題|整理使用者的問題|查詢耗時/);
    assert.equal((html.match(/本問題涉及投資決策/g)||[]).length,1);
    assert.equal((html.match(/尚未提供投資標的。/g)||[]).length,1);
    assert.match(html,/<h5>建議做法<\/h5>/);
    assert.match(html,/<h5>尚缺資料<\/h5>/);
    assert.match(html,/<details class="qa-query-details"><summary>查詢詳情<\/summary>[\s\S]*這是完整的原問題[\s\S]*查詢耗時 1\.5 秒/);
});

test('law cards retain exact quotes, group passages by document and link to the answer without repeating it',()=>{
    const app=boot();
    const fixture=answer();
    const quote='原文：甲 < 乙，且不包含「例外」。';
    fixture.claims[0].citations[0].quote=quote;
    fixture.sources.push({...fixture.sources[0],source_id:'S2'});
    fixture.claims[1].citations.push({source_id:'S2',quote:'同一法規的另一個段落。'});
    app.context.fixture=fixture;
    app.run('renderQAAnswer(fixture)');
    const html=app.elements.qaResult.innerHTML;
    assert.equal((html.match(/class="qa-regulation"/g)||[]).length,1);
    assert.match(html,/<details class="qa-regulation-evidence"><summary>引用原文與版本<\/summary>/);
    assert.match(html,/<blockquote>原文：甲 &lt; 乙，且不包含「例外」。<\/blockquote>/);
    assert.match(html,/同一法規的另一個段落。/);
    assert.match(html,/href="#qaResult-source-1"/);
    assert.match(html,/id="qaResult-source-1"/);
    assert.match(html,/href="#qaResult-point-1"/);
    assert.match(html,/id="qaResult-point-1"/);
    assert.doesNotMatch(html,/<details[^>]*\bopen(?:[\s=>])/);
});

test('draft status and citation warnings remain visible while long quotations are collapsed',()=>{
    const app=boot();
    const fixture=answer();
    fixture.sources[0].version_note='預告／草案，尚未正式發布。';
    fixture.missing_information=['部分推論或建議的來源未通過檢查，已省略。'];
    app.context.fixture=fixture;
    app.run('renderQAAnswer(fixture)');
    const html=app.elements.qaResult.innerHTML;
    const notes=html.match(/<aside class="qa-answer-notes"[\s\S]*?<\/aside>/)[0];
    assert.match(notes,/部分推論或建議的來源未通過檢查/);
    assert.match(notes,/預告或草案，請確認是否已生效/);
    const lawHeading=html.slice(html.indexOf('qa-regulation-heading'),html.indexOf('qa-regulation-evidence'));
    assert.match(lawHeading,/預告／草案/);
    assert.doesNotMatch(notes,/<details/);
});

test('facts remain literal when no inference exists and insufficient results still explain what is missing',()=>{
    const app=boot();
    const fixture=answer();
    fixture.claims=fixture.claims.filter(item=>item.kind==='fact');
    app.context.fixture=fixture;
    app.run('renderQAAnswer(fixture)');
    assert.match(app.elements.qaResult.innerHTML,/<h3>原文摘錄<\/h3>/);
    assert.match(app.elements.qaResult.innerHTML,/測試原文指出應保存投資決策與覆核紀錄。/);
    assert.doesNotMatch(app.elements.qaResult.innerHTML,/AI 推論/);
    fixture.status='insufficient';
    fixture.claims=[];
    fixture.missing_information=['請補充委外作業內容。'];
    app.run('renderQAAnswer(fixture)');
    assert.match(app.elements.qaResult.innerHTML,/<h3>資料不足<\/h3>/);
    assert.match(app.elements.qaResult.innerHTML,/請補充委外作業內容/);
    assert.match(app.elements.qaResult.innerHTML,/<details class="qa-unanswered-sources">/);
    assert.doesNotMatch(app.elements.qaResult.innerHTML,/class="qa-regulations"/);
});

test('source-support notices stay visible and model review is never presented as legal approval',()=>{
    const app=boot();
    const fixture=answer();
    fixture.support_review={requested:3,supported:1,withheld:2,unverified:1};
    fixture.missing_information=['部分結論的依據核對未完成，已省略未確認的推論與建議；原文仍可查看。'];
    app.context.fixture=fixture;
    app.run('renderQAAnswer(fixture)');
    const html=app.elements.qaResult.innerHTML;
    assert.match(html,/推論與建議另經模型核對原文/);
    const notes=html.match(/<aside class="qa-answer-notes"[\s\S]*?<\/aside>/)[0];
    assert.match(notes,/核對未完成/);
    assert.match(html,/核對 3 項，保留 1 項，省略 2 項/);
    assert.doesNotMatch(html,/保證正確|已通過法律審查/);
});

test('conversation limits block another API request and reset restores input',async()=>{
    let calls=0;
    const app=boot(async()=>{calls++;});
    app.run("qaHistory=Array.from({length:6},()=>({question:'已有的問題',follow_up_questions:[]}));updateQAUI();");
    assert.equal(app.elements.qaSubmit.disabled,true);
    app.elements.qaQuestion.value='再詢問一次';
    await app.run('submitRegulatoryQuestion({preventDefault(){}})');
    assert.equal(calls,0);
    app.run('resetQAConversation()');
    assert.equal(app.elements.qaSubmit.disabled,false);
    assert.equal(app.elements.qaQuestion.disabled,false);
});

test('published pages expose one assistant form and one new-question action without mode selectors',()=>{
    for(const file of ['index.html','public/index.html']){
        const html=fs.readFileSync(path.join(__dirname,'..',file),'utf8');
        assert.match(html,/監理問答助手/);
        assert.equal((html.match(/id="qaForm"/g)||[]).length,1);
        assert.match(html,/id="qaNewQuestion"/);
        assert.doesNotMatch(html,/id="qaModeQuestion"|id="qaModeScenario"|id="enterpriseKnowledge"/);
    }
});
