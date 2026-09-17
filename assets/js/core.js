const $ =
    id =>
        document.getElementById(
            id
        );


const state = {

    events:[],

    sources:{},

    selected:null,

    query:'',

    filter:'all',

    view:'intel',

    stale:false,

    lastSync:null,

    ai:{
        enabled:false,
        mode:'',
        model:'',
        provider:'',
    },

    aiLoading:
        new Set(),

    aiRequested:
        new Set(),
};


/* =====================================================
   HTML Escape
===================================================== */

const esc =
    value =>

        String(
            value ?? ''
        )
        .replace(

            /[&<>'"]/g,

            char => ({

                '&':'&amp;',

                '<':'&lt;',

                '>':'&gt;',

                "'":'&#39;',

                '"':'&quot;',

            }[char])
        );


/* =====================================================
   部門名稱
===================================================== */

const departmentNameMap = {

    Compliance:
        '法令遵循部',

    Legal:
        '法務部',

    Risk:
        '風險管理部',

    Audit:
        '內部稽核部',

    Sales:
        '業務通路管理部',

    Operations:
        '保單行政／營運管理部',

    IT:
        '資訊科技部',

    'Information Technology':
        '資訊科技部',

    'Information Security':
        '資訊安全部',

    'Cyber Security':
        '資訊安全部',

    Product:
        '商品發展部',

    'Product Development':
        '商品發展部',

    Marketing:
        '行銷企劃部',

    Training:
        '人力資源部',

    'Human Resources':
        '人力資源部',

    HR:
        '人力資源部',

    Claims:
        '理賠部',

    Claim:
        '理賠部',

    'Customer Service':
        '客戶服務部',

    'Customer Services':
        '客戶服務部',

    Actuarial:
        '精算部',

    Finance:
        '財務部',

    Accounting:
        '財務部',

    Investment:
        '投資管理部',

    Investments:
        '投資管理部',

    'Data Governance':
        '個資／資料治理單位',

    Privacy:
        '個資／資料治理單位',

    Outsourcing:
        '採購／委外管理單位',

    Procurement:
        '採購／委外管理單位',
};


function departmentLabel(
    name
){

    if(!name){

        return '待確認';
    }


    const value =
        String(
            name
        ).trim();


    return (

        departmentNameMap[
            value
        ]

        ||

        value
    );
}


/* =====================================================
   Source Types
===================================================== */

function sourceType(
    event
){

    const key =
        event?.source_key
        ||
        '';


    if(
        key
        ===
        'fsc_penalty'
    ){

        return '裁罰';
    }


    if(
        [
            'law_db',
            'insurance_law'
        ]
        .includes(
            key
        )
    ){

        return '法規';
    }


    if(
        key
        ===
        'fsc_announcement'
    ){

        return '公告';
    }


    if(
        key
        ===
        'reg_news'
    ){

        return '監理新聞';
    }


    return '監理資訊';
}


function sourceTone(
    event
){

    const type =
        sourceType(
            event
        );


    if(
        type
        ===
        '裁罰'
    ){

        return 'red';
    }


    if(
        type
        ===
        '法規'
    ){

        return 'green';
    }


    if(
        type
        ===
        '公告'
    ){

        return 'blue';
    }


    return 'gray';
}


function workflowStatus(
    event
){

    return (
        event.workflow_status
        ||
        '待確認'
    );
}


/* =====================================================
   Dates
===================================================== */

function formatDate(
    value
){

    if(!value){

        return '日期未提供';
    }


    const date =
        new Date(
            value
        );


    if(
        Number.isNaN(
            date.getTime()
        )
    ){

        return value;
    }


    return new Intl.DateTimeFormat(

        'zh-TW',

        {

            year:'numeric',

            month:'2-digit',

            day:'2-digit',
        }

    ).format(
        date
    );
}


function formatDateTime(
    value
){

    if(!value){

        return '—';
    }


    const date =
        new Date(
            value
        );


    if(
        Number.isNaN(
            date.getTime()
        )
    ){

        return value;
    }


    return new Intl.DateTimeFormat(

        'zh-TW',

        {

            month:'2-digit',

            day:'2-digit',

            hour:'2-digit',

            minute:'2-digit',
        }

    ).format(
        date
    );
}


/* =====================================================
   Filters
===================================================== */

function filteredEvents(){

    const query =

        state.query
        .trim()
        .toLowerCase();


    return state.events.filter(

        event => {


            const type =
                sourceType(
                    event
                );


            const filterOk =

                state.filter
                ===
                'all'

                ||

                (
                    state.filter
                    ===
                    'penalty'

                    &&

                    type
                    ===
                    '裁罰'
                )

                ||

                (
                    state.filter
                    ===
                    'law'

                    &&

                    type
                    ===
                    '法規'
                )

                ||

                (
                    state.filter
                    ===
                    'announcement'

                    &&

                    type
                    ===
                    '公告'
                )

                ||

                (
                    state.filter
                    ===
                    'news'

                    &&

                    type
                    ===
                    '監理新聞'
                );


            if(!filterOk){

                return false;
            }


            if(!query){

                return true;
            }


            const analysis =
                event.analysis
                ||
                {};


            const departmentText = (

                analysis.departments
                ||
                []

            )
            .flatMap(

                item => [

                    departmentLabel(
                        item.department
                    ),

                    item.reason
                ]
            );


            const processText = (

                analysis.impact_processes
                ||
                []

            )
            .flatMap(

                item => [

                    item.process,

                    item.department,

                    item.impact,
                ]
            );


            const text = [

                event.title,

                event.source,

                event.source_detail,

                event.description,

                event.category,

                analysis.summary,

                analysis.event_nature,

                analysis.responsible_department,

                ...(
                    analysis.regulatory_points
                    ||
                    []
                ),

                ...(
                    analysis.attention_items
                    ||
                    []
                ),

                ...(
                    analysis.actions
                    ||
                    []
                ),

                ...departmentText,

                ...processText,

            ]
            .join(
                ' '
            )
            .toLowerCase();


            return text.includes(
                query
            );
        }
    );
}


/* =====================================================
   Source Groups
===================================================== */

function sourceGroups(){

    const groups = {};


    Object.entries(
        state.sources
    )
    .forEach(

        (
            [
                key,
                source
            ]
        ) => {


            const name =

                source.group_label

                ||

                source.label

                ||

                key;


            (
                groups[
                    name
                ]
                ??=
                []
            )
            .push(
                [
                    key,
                    source
                ]
            );
        }
    );


    return groups;
}


function sourceHealthyGroupCount(){

    return Object.values(
        sourceGroups()
    )
    .filter(

        items =>

            items.some(

                (
                    [
                        ,
                        source
                    ]
                ) =>
                    source.ok
            )
    )
    .length;
}
