const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function boot(fetch){
    const elements = new Map();
    const element = id=>{
        if(!elements.has(id)) elements.set(id,{value:'',innerHTML:'',textContent:'',hidden:false,disabled:false,attributes:{},
            addEventListener(){},querySelectorAll(){return [];},focus(){},setAttribute(key,value){this.attributes[key]=value;}});
        return elements.get(id);
    };
    const context = vm.createContext({$:element,fetch,esc:value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'..','assets/js/enterprise-knowledge.js'),'utf8'),context);
    element('ekQuestion').value = 'VPN連不上怎麼辦？';
    element('ekCategory').value = 'IT 支援';
    return {element,context,run:code=>vm.runInContext(code,context)};
}

function searchResult(){
    return {question:'VPN連不上怎麼辦？',category:'IT 支援',documents:1,sources:[{id:'vpn-faq',source_id:'K1',category:'IT 支援',title:'VPN連線FAQ',section:'初步排查',text:'先確認一般網路可用，再確認公司核准的VPN客戶端。',number:'DEMO-IT-002',version:'1.0',updated:'2026-10-20',url:'/api/enterprise-knowledge/document?id=vpn-faq#section-1',download_url:'/api/enterprise-knowledge/document?id=vpn-faq&download=1'}]};
}

test('document matches appear before AI finishes and remain usable when AI is unavailable',async()=>{
    let answerResolve, answerStarted;
    const started = new Promise(resolve=>{answerStarted=resolve;});
    const pending = new Promise(resolve=>{answerResolve=resolve;});
    const requests=[];
    const app=boot(async(url,options)=>{
        requests.push({url,body:JSON.parse(options.body)});
        if(url.endsWith('/search')) return {ok:true,json:async()=>({ok:true,result:searchResult()})};
        answerStarted();
        return pending;
    });
    const operation=app.run('submitEnterpriseQuestion({preventDefault(){}})');
    await started;
    assert.equal(app.element('ekMatches').hidden,false);
    assert.match(app.element('ekMatches').innerHTML,/VPN連線FAQ/);
    assert.match(app.element('ekMatches').innerHTML,/下載完整文件/);
    assert.equal(app.element('ekSubmit').disabled,true);
    await app.run('submitEnterpriseQuestion({preventDefault(){}})');
    assert.equal(requests.length,2);
    assert.equal(requests[0].body.category,'IT 支援');
    assert.ok(requests.every(request=>request.url.startsWith('/api/enterprise-knowledge/')));
    answerResolve({ok:false,json:async()=>({ok:false,error:'模型無法使用'})});
    await operation;
    assert.equal(app.element('ekSubmit').disabled,false);
    assert.match(app.element('ekMatches').innerHTML,/VPN連線FAQ/);
    assert.match(app.element('ekResult').innerHTML,/你仍可查閱與下載/);
    assert.equal(app.element('ekQuestion').value,'VPN連不上怎麼辦？');
});

test('no related document stops before AI generation',async()=>{
    const calls=[];
    const app=boot(async(url)=>{calls.push(url);return {ok:true,json:async()=>({ok:true,result:{...searchResult(),sources:[],documents:0}})};});
    await app.run('submitEnterpriseQuestion({preventDefault(){}})');
    assert.deepEqual(calls,['/api/enterprise-knowledge/search']);
    assert.equal(app.element('ekMatches').hidden,true);
    assert.match(app.element('ekStatus').textContent,/尚未呼叫 AI/);
});

test('AI prose and quotations are escaped and citations resolve to company documents',()=>{
    const app=boot();
    app.context.result={...searchResult(),status:'answered',points:[{text:'<script>bad</script>',citations:[{source_id:'K1',quote:'先確認一般網路可用，再確認公司核准的VPN客戶端。'}]}],steps:[],follow_up_questions:['是哪個系統？']};
    app.run('renderEnterpriseAnswer(result)');
    assert.ok(!app.element('ekResult').innerHTML.includes('<script>'));
    assert.match(app.element('ekResult').innerHTML,/&lt;script&gt;/);
    assert.match(app.element('ekResult').innerHTML,/查看依據 K1/);
    assert.match(app.element('ekResult').innerHTML,/還需要釐清/);
    assert.equal(app.run("enterpriseLink('javascript:alert(1)')"),'#');
    assert.equal(app.run("enterpriseLink('https://external.example/file')"),'#');
});

test('category changes filter the file library without replacing the question',()=>{
    const app=boot();
    app.context.catalog={documents:[{id:'vpn',title:'VPN FAQ',category:'IT 支援',number:'IT1',version:'1.0',url:'/api/enterprise-knowledge/document?id=vpn',download_url:'/api/enterprise-knowledge/document?id=vpn&download=1'}, {id:'data',title:'資料提供表單',category:'表單',number:'F1',version:'1.0',url:'/api/enterprise-knowledge/document?id=data',download_url:'/api/enterprise-knowledge/document?id=data&download=1'}]};
    app.run('enterpriseState.catalog=catalog;renderEnterpriseLibrary();');
    assert.match(app.element('ekLibraryList').innerHTML,/VPN FAQ/);
    assert.ok(!app.element('ekLibraryList').innerHTML.includes('資料提供表單'));
    assert.equal(app.element('ekQuestion').value,'VPN連不上怎麼辦？');
});
