const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function boot(){
    const elements=new Map();
    const diagnostics=[];
    let available=false;
    const element=id=>{
        if(!elements.has(id)) elements.set(id,{innerHTML:'',textContent:'',disabled:false,
            classList:{add(){},remove(){}}});
        return elements.get(id);
    };
    const context=vm.createContext({document:{getElementById:element},
        console:{error:(...args)=>diagnostics.push(args)},toast(){},
        fetch:async()=>({ok:available,status:available?200:503,
            json:async()=>({events:[{id:'new'}],sources:{},ai:{enabled:false}})}),
        renderList(){element('eventList').innerHTML='取得的資料';},
        renderDetail(){element('eventDetail').innerHTML='取得的詳情';},
        renderAdvancedFilters(){},renderTicker(){},renderManagement(){},renderSources(){},
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/js/core.js'),'utf8'),context);
    const app=fs.readFileSync(path.join(__dirname,'../assets/js/app.js'),'utf8');
    vm.runInContext(app.slice(0,app.indexOf('function showView(')),context);
    element('eventDetail').innerHTML='正在取得監理資訊…';
    return {elements,element,diagnostics,run:code=>vm.runInContext(code,context),
        set available(value){available=value;}};
}

test('initial API failure replaces loading messages and exposes a working retry',async()=>{
    const app=boot();
    await app.run('loadEvents()');
    assert.doesNotMatch(app.element('eventDetail').innerHTML,/正在取得|載入中/);
    assert.match(app.element('eventDetail').innerHTML,/無法取得/);
    assert.match(app.element('connectionNotice').innerHTML,/重新載入/);
    assert.equal(app.element('refreshBtn').disabled,false);
    assert.match(app.diagnostics[0][0],/api\/events/);
    app.available=true;
    await app.element('retryLoadEvents').onclick();
    assert.equal(app.element('eventList').innerHTML,'取得的資料');
    assert.equal(app.element('eventDetail').innerHTML,'取得的詳情');
    assert.equal(app.run('state.events[0].id'),'new');
});

test('a failed refresh preserves previously displayed public data and detail',async()=>{
    const app=boot();
    app.run('state.events=[{id:"previous"}];state.selected="previous";');
    app.element('eventList').innerHTML='先前的清單';
    app.element('eventDetail').innerHTML='先前的詳情';
    await app.run('loadEvents(true)');
    assert.equal(app.element('eventList').innerHTML,'先前的清單');
    assert.equal(app.element('eventDetail').innerHTML,'先前的詳情');
    assert.equal(app.run('state.selected'),'previous');
    assert.match(app.element('connectionNotice').innerHTML,/保留上次/);
    assert.equal(app.element('refreshBtn').disabled,false);
});
