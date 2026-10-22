/* =====================================================
   Load Events
===================================================== */

async function loadEvents(
    force=false
){

    const button =
        $('refreshBtn');


    button.disabled =
        true;


    button.textContent =

        force

        ?

        '更新中…'

        :

        '讀取中…';


    try{

        const response =
            await fetch(

                `/api/events${
                    force
                    ?
                    '?refresh=1'
                    :
                    ''
                }`,

                {
                    cache:'no-store'
                }
            );


        if(
            !response.ok
        ){

            throw new Error(
                `HTTP ${response.status}`
            );
        }


        const data =
            await response.json();

        state.history.sources = data.history?.sources || {};

        const retryAfter = Number(data.manual_retry_after_seconds);
        state.manualRefreshRetryAt = data.manual_refresh_limited && Number.isFinite(retryAfter) && retryAfter > 0
            ? Date.now() + retryAfter * 1000 : null;


        state.events =
            data.events
            ||
            [];


        state.sources =
            data.sources
            ||
            {};


        state.lastSync =
            data.last_sync;


        state.stale =
            !!data.stale;


        state.ai =
            data.ai
            ||
            {

                enabled:false,

                mode:'',

                model:'',

                provider:'',
            };


        const exists =
            state.events.some(

                event =>
                    event.id
                    ===
                    state.selected
            );


        if(
            !exists
            &&
            state.events.length
        ){

            state.selected =
                state.events[0].id;
        }


        renderList();

        renderAdvancedFilters();

        renderTicker();

        renderDetail();

        renderManagement();

        renderSources();

        if(
            state.stale
        ){

            $('connectionNotice').className =
                'notice';


            $('connectionNotice')
            .classList
            .remove(
                'hidden'
            );


            $('connectionNotice').innerHTML =

                (
                    '<strong>'
                    +
                    '部分官方來源目前無法更新。'
                    +
                    '</strong> '
                    +
                    '系統已保留先前成功取得的資料。'
                );
        }

        else{

            $('connectionNotice')
            .classList
            .add(
                'hidden'
            );
        }


        if(
            data.manual_refresh_limited
            &&
            force
        ){

            toast(

                manualRefreshWaitText()
            );

        }

        else if(force){

            toast(
                '最新監理資訊已更新。'
            );
        }

    }

    catch(error){

        console.error(
            '監理資訊載入失敗（/api/events）：',
            error
        );


        $('connectionNotice').className =
            'notice error';


        $('connectionNotice')
        .classList
        .remove(
            'hidden'
        );


        $('connectionNotice').innerHTML = `
            <strong>目前無法取得資料，請稍後重試。</strong>
            ${state.events.length ? '<span>目前保留上次取得的資料。</span>' : ''}
            <button type="button" class="btn" id="retryLoadEvents">重新載入</button>`;
        const retry = $('retryLoadEvents');
        retry.onclick = async () => {
            retry.disabled = true;
            await loadEvents();
        };
        if(!state.events.length){
            $('eventList').innerHTML = '<div class="d-empty">目前無法取得監理資訊。</div>';
            $('eventDetail').innerHTML = '<div class="d-empty">目前無法取得監理資訊，請使用「重新載入」再試一次。</div>';
            $('ledgerStatus').textContent = '資料載入失敗';
            $('ledgerResultCount').textContent = '尚未取得資料';
        }

    }

    finally{

        button.disabled =
            false;


        button.textContent =
            '更新最新資訊';
    }
}


/* =====================================================
   View Switch
===================================================== */

function showView(
    view
){

    state.view =
        view;

    $('qaView').classList.toggle('hidden', view !== 'qa');

    $('intelView')
    .classList
    .toggle(

        'hidden',

        view
        !==
        'intel'
    );


    $('managementView')
    .classList
    .toggle(

        'hidden',

        view
        !==
        'management'
    );


    $('viewTitle').textContent = view === 'qa' ? '監理問答助手' :

        view
        ===
        'management'

        ?

        '管理摘要'

        :

        '監理情報中心';


    document
    .querySelectorAll(
        '.nav button'
    )
    .forEach(

        button => {

            button
            .classList
            .toggle(

                'active',

                button.dataset.view
                ===
                view
            );

            if(button.dataset.view === view) button.setAttribute('aria-current', 'page');
            else button.removeAttribute('aria-current');
        }
    );


    if(
        view
        ===
        'management'
    ){

        renderManagement();
    }
    else if(view === 'intel'){
        renderList();
    }
}


/* =====================================================
   Sidebar
===================================================== */

function setSidebarExpanded(
    expanded
){

    const sidebar =
        $('sidebar');


    const toggle =
        $('sidebarToggle');


    sidebar
    .classList
    .toggle(

        'expanded',

        expanded
    );


    toggle.setAttribute(

        'aria-expanded',

        String(
            expanded
        )
    );


    toggle.setAttribute(

        'aria-label',

        expanded

        ?

        '收合主選單'

        :

        '展開主選單'
    );
}


/* =====================================================
   Toast
===================================================== */

function toast(
    message
){

    const element =
        $('toast');


    element.textContent =
        message;


    element
    .classList
    .remove(
        'hidden'
    );


    clearTimeout(
        element.timer
    );


    element.timer =
        setTimeout(

            () =>

                element
                .classList
                .add(
                    'hidden'
                ),

            2600
        );
}


/* =====================================================
   User Events
===================================================== */

$('sidebarToggle').onclick =
    () =>
        setSidebarExpanded(

            !$('sidebar')
            .classList
            .contains(
                'expanded'
            )
        );


document.addEventListener(

    'keydown',

    event => {

        if(
            event.key
            ===
            'Escape'
        ){

            if(!$('sourcesModal').classList.contains('hidden')){
                closeSourcesModal();
                return;
            }

            setSidebarExpanded(
                false
            );


            if(
                state.advancedFilterOpen
            ){

                setAdvancedFilterOpen(
                    false
                );
            }
        }
    }
);


$('search').oninput =
    event => {


        state.query =
            event.target.value;

        state.pagination.intel.page = 1;


        renderList();
    };


$('advancedFilterButton').onclick =
    () =>
        setAdvancedFilterOpen(
            !state.advancedFilterOpen
        );


$('clearAdvancedFilters').onclick =
    clearAdvancedFilterDraft;


$('applyAdvancedFilters').onclick =
    applyAdvancedFilterDraft;


document.addEventListener(

    'click',

    event => {

        if(
            state.advancedFilterOpen
            &&
            !$('advancedFilter')
            .contains(
                event.target
            )
        ){

            setAdvancedFilterOpen(
                false
            );
        }
    }
);


document
.querySelectorAll(
    '.nav button'
)
.forEach(

    button =>

        button.onclick =
            () => {

                showView(
                    button.dataset.view
                );


                if(
                    window
                    .matchMedia(
                        '(max-width:700px)'
                    )
                    .matches
                ){

                    setSidebarExpanded(
                        false
                    );
                }
            }
);


$('refreshBtn').onclick =
    () => {


        state.aiRequested.clear();

        state.aiFailed.clear();


        loadEvents(
            true
        );
    };


$('sourcesBtn').onclick =
    () => {


        $('sourcesModal')
        .classList
        .remove(
            'hidden'
        );


        renderSources();
        document.querySelector('.shell').inert = true;
        $('closeSources').focus();
    };


function closeSourcesModal(){
    $('sourcesModal').classList.add('hidden');
    document.querySelector('.shell').inert = false;
    $('sourcesBtn').focus();
}

$('closeSources').onclick = closeSourcesModal;


$('sourcesModal').onclick =
    event => {


        if(
            event.target
            ===
            $('sourcesModal')
        ){

            closeSourcesModal();
        }
    };

$('sourcesModal').addEventListener('keydown', event => {
    if(event.key !== 'Tab') return;
    const controls = Array.from($('sourcesModal').querySelectorAll('button, summary, a[href]'))
        .filter(element => element.getClientRects().length && !element.disabled)
        .filter(element => !element.closest('details:not([open])') || element.matches('summary'));
    const first = controls[0];
    const last = controls[controls.length - 1];
    if(event.shiftKey && document.activeElement === first){
        event.preventDefault();
        last?.focus();
    }else if(!event.shiftKey && document.activeElement === last){
        event.preventDefault();
        first?.focus();
    }
});


$('reportBtn').onclick =
    generateManagementReport;


/* =====================================================
   Initialize
===================================================== */

setSidebarExpanded(
    false
);


loadEvents(
    false
);
