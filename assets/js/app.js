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


        renderMetrics();

        renderList();

        renderDetail();

        renderManagement();

        renderSources();

        updateSystemStatus();


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

                `更新頻率保護中，約 ${
                    data.manual_retry_after_seconds
                    ||
                    0
                } 秒後可再次強制更新。`
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
            error
        );


        $('connectionNotice').className =
            'notice error';


        $('connectionNotice')
        .classList
        .remove(
            'hidden'
        );


        $('connectionNotice').innerHTML =

            (
                '<strong>'
                +
                '無法連到本機資料服務。'
                +
                '</strong> '
                +
                '請確認 server.py 是否仍在執行。'
            );


        $('systemStatus').textContent =
            '資料服務未連線';


        $('aiStatus').textContent =
            'AI 狀態無法取得';
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


    $('viewTitle').textContent =

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
        }
    );


    if(
        view
        ===
        'management'
    ){

        renderManagement();
    }
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

$('search').oninput =
    event => {


        state.query =
            event.target.value;


        renderList();
    };


document
.querySelectorAll(
    '.chip'
)
.forEach(

    chip =>

        chip.onclick =
            () => {


                state.filter =
                    chip.dataset.filter;


                document
                .querySelectorAll(
                    '.chip'
                )
                .forEach(

                    item =>

                        item
                        .classList
                        .toggle(

                            'active',

                            item
                            ===
                            chip
                        )
                );


                renderList();
            }
);


document
.querySelectorAll(
    '.nav button'
)
.forEach(

    button =>

        button.onclick =
            () =>
                showView(
                    button.dataset.view
                )
);


$('refreshBtn').onclick =
    () => {


        state.aiRequested.clear();


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
    };


$('closeSources').onclick =
    () =>

        $('sourcesModal')
        .classList
        .add(
            'hidden'
        );


$('sourcesModal').onclick =
    event => {


        if(
            event.target
            ===
            $('sourcesModal')
        ){

            $('sourcesModal')
            .classList
            .add(
                'hidden'
            );
        }
    };


$('reportBtn').onclick =
    generateManagementReport;


/* =====================================================
   Initialize
===================================================== */

loadEvents(
    false
);
