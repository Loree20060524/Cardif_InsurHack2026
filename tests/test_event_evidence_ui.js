const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness(){
    const elements = new Map();
    const context = vm.createContext({URL, Map, Set, console,
        state:{events:[], selected:'e', ai:{enabled:true}, aiLoading:new Set(), aiFailed:new Set(), aiRequested:new Set()},
        $:id=>{if(!elements.has(id)) elements.set(id,{innerHTML:''}); return elements.get(id);},
        esc:value=>String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c])),
        sourceType:()=> '監理新聞', sourceTone:()=>'', formatEventDate:()=> '2026/01/01', departmentLabel:value=>value,
        renderImpactChain:()=>'', renderProcesses:()=>'', renderLawComparisonSection:()=>'', bindLawComparison(){},
        addToManagementSummary(){}, ensureAIAnalysis(){}, toast(){}, navigator:{}, renderManagement(){},
        renderAdvancedFilters(){}, renderList(){},
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/js/detail-view.js'),'utf8'),context);
    return {context,elements,run:code=>vm.runInContext(code,context)};
}

function report(){
    return {analysis_mode:'AI 深度分析', risk_level:'中', importance:'重要', responsible_department:'法令遵循',
        rating_reason:'涉及內部控制改善。', summary:'依原文整理的摘要。',
        verification_notice:'部分結論未獲原文充分支持，已省略。',
        support_review:{version:'event-support-v1',requested:2,supported:1,withheld:1,unverified:1,
            sources:[{source_id:'S1',title:'官方公告',url:'https://example.com/notice'}],
            checks:[{id:'summary',status:'supported',text:'保留的摘要。',citations:[{source_id:'S1',quote:'原文所述的完整依據。'}]},
                    {id:'actions:0',status:'unverified',reason:'暫時無法完成核對。',text:'不該顯示的未核對內容。'}]}};
}

test('source evidence is collapsed, with counts and no unsupported text or legal assurance',()=>{
    const h=harness(); h.context.sample=report();
    const markup=h.run('renderEventEvidence(sample)');
    assert.match(markup,/<details class="block detail-review">/);
    assert.doesNotMatch(markup,/<details[^>]*\bopen\b|不該顯示|法律正確|已通過/);
    assert.match(markup,/核對 2 項，保留 1 項，省略 1 項/);
    assert.match(markup,/原文所述的完整依據/);
    assert.match(markup,/仍可能誤判或漏判/);
    assert.match(markup,/未完成核對/);
});

test('quotes and source titles are escaped and unsafe source URLs have no links',()=>{
    const h=harness(), sample=report();
    sample.support_review.sources[0]={source_id:'S1',title:'<img onerror=alert(1)>',url:'javascript:alert(1)'};
    sample.support_review.checks[0].citations[0].quote='<script>source</script>';
    h.context.sample=sample;
    const markup=h.run('renderEventEvidence(sample)');
    assert.match(markup,/&lt;script&gt;/);
    assert.match(markup,/&lt;img/);
    assert.doesNotMatch(markup,/<script>|<img|javascript:|<a href/);
});

test('detail distinguishes incomplete review and shows the rating basis and notice',()=>{
    const h=harness(); h.context.sample=report();
    h.run('state.events=[{id:"e",title:"監理公告",url:"https://example.com",analysis:sample}]; renderDetail(false)');
    const markup=h.elements.get('eventDetail').innerHTML;
    assert.match(markup,/id="aiAnalysisStatus"[^>]*>\s*依據核對未完成/);
    assert.match(markup,/分級依據：涉及內部控制改善/);
    assert.match(markup,/建議關注部門/);
    assert.match(markup,/可能受影響部門（初步判讀）/);
    assert.match(markup,/role="status">部分結論/);
    assert.match(markup,/目前沒有可保留的注意事項/);
});

test('legacy AI results get a visible request to recheck sources',()=>{
    const h=harness();
    assert.match(h.run('renderEventEvidence({analysis_mode:"AI 深度分析"})'),/尚未做來源支持核對/);
    assert.equal(h.run('renderEventEvidence({analysis_mode:"規則備援"})'),'');
});

test('an incomplete forced review preserves the previously reviewed result and allows retry',async()=>{
    const h=harness(), sample=report(); sample.support_review.unverified=0;
    h.context.sample=sample;
    h.run('state.events=[{id:"e",analysis:sample}]');
    h.context.fetch=async()=>({ok:true,json:async()=>({ai_used:true,analysis:report()})});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/js/ai-analysis.js'),'utf8'),h.context);
    await h.run('ensureAIAnalysis(state.events[0],true)');
    assert.equal(h.run('state.events[0].analysis.support_review.unverified'),0);
    assert.equal(h.run('state.aiFailed.has("e")'),true);
    assert.equal(h.run('state.aiLoading.has("e")'),false);
});

test('an old unreviewed result triggers a new request and incomplete review is not treated as complete',async()=>{
    const h=harness();
    h.run('state.events=[{id:"e",analysis:{analysis_mode:"AI 深度分析",summary:"舊摘要"}}]');
    let calls=0;
    h.context.fetch=async()=>{calls++;return {ok:true,json:async()=>({ai_used:true,analysis:report()})};};
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/js/ai-analysis.js'),'utf8'),h.context);
    await h.run('ensureAIAnalysis(state.events[0])');
    await h.run('ensureAIAnalysis(state.events[0])');
    assert.equal(calls,1);
    assert.equal(h.run('state.aiFailed.has("e")'),true);
    assert.equal(h.run('state.events[0].analysis.support_review.unverified'),1);
});
