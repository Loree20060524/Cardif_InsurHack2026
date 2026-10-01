const $ =
    id =>
        document.getElementById(
            id
        );


const state = {

    events:[],

    sources:{},

    selected:null,

    sourceTypeFilter:'全部',

    query:'',

    filters:{
        types:new Set(),
        departments:new Set(),
    },

    filterDraft:{
        types:new Set(),
        departments:new Set(),
    },

    advancedFilterOpen:false,

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

    aiFailed:
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
        '法令遵循',

    '法令遵循部':
        '法令遵循',

    Legal:
        '法務',

    '法務部':
        '法務',

    Risk:
        '風險管理',

    '風險管理部':
        '風險管理',

    Audit:
        '內部稽核',

    '內部稽核部':
        '內部稽核',

    Sales:
        '業務通路／行銷',

    Marketing:
        '業務通路／行銷',

    '業務通路管理部':
        '業務通路／行銷',

    '行銷企劃部':
        '業務通路／行銷',

    Operations:
        '核保／新契約／保單營運',

    Underwriting:
        '核保／新契約／保單營運',

    'New Business':
        '核保／新契約／保單營運',

    'Policy Administration':
        '核保／新契約／保單營運',

    '保單行政／營運管理部':
        '核保／新契約／保單營運',

    IT:
        '資訊科技',

    'Information Technology':
        '資訊科技',

    '資訊科技部':
        '資訊科技',

    'Information Security':
        '資訊安全／個資治理',

    'Cyber Security':
        '資訊安全／個資治理',

    'Data Governance':
        '資訊安全／個資治理',

    Privacy:
        '資訊安全／個資治理',

    '資訊安全部':
        '資訊安全／個資治理',

    '個資／資料治理單位':
        '資訊安全／個資治理',

    Product:
        '商品／精算',

    'Product Development':
        '商品／精算',

    Actuarial:
        '商品／精算',

    '商品發展部':
        '商品／精算',

    '精算部':
        '商品／精算',

    Training:
        '人力資源',

    'Human Resources':
        '人力資源',

    HR:
        '人力資源',

    '人力資源部':
        '人力資源',

    Claims:
        '理賠',

    Claim:
        '理賠',

    '理賠部':
        '理賠',

    'Customer Service':
        '客戶服務／申訴',

    'Customer Services':
        '客戶服務／申訴',

    '客戶服務部':
        '客戶服務／申訴',

    Finance:
        '財務／會計',

    Accounting:
        '財務／會計',

    '財務部':
        '財務／會計',

    Investment:
        '投資／資產負債管理',

    Investments:
        '投資／資產負債管理',

    '投資管理部':
        '投資／資產負債管理',

    Outsourcing:
        '風險管理',

    Procurement:
        '風險管理',

    '採購／委外管理單位':
        '風險管理',
};


const RESPONSIBLE_DEPARTMENT_OPTIONS = [
    '法令遵循',
    '法務',
    '風險管理',
    '內部稽核',
    '商品／精算',
    '業務通路／行銷',
    '核保／新契約／保單營運',
    '客戶服務／申訴',
    '理賠',
    '財務／會計',
    '投資／資產負債管理',
    '資訊科技',
    '資訊安全／個資治理',
    '人力資源',
];


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


function formatEventDate(
    event
){

    if(
        event?.published_at
    ){

        return formatDate(
            event.published_at
        );
    }


    if(
        event?.detected_at
    ){

        return (
            '偵測 '
            +
            formatDate(
                event.detected_at
            )
        );
    }


    return '日期未提供';
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

const EVENT_TYPE_FILTER_OPTIONS = [
    '裁罰',
    '法規',
    '公告',
    '監理新聞',
];


function copyAdvancedFilters(
    filters
){

    return {
        types:
            new Set(
                filters.types
            ),

        departments:
            new Set(
                filters.departments
            ),
    };
}


function advancedFilterCount(
    filters=state.filters
){

    return (
        filters.types.size
        +
        filters.departments.size
    );
}


function responsibleDepartmentOptions(){

    return [
        ...RESPONSIBLE_DEPARTMENT_OPTIONS
    ];
}

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


            const typeOk =
                !state.filters.types.size
                ||
                state.filters.types.has(
                    type
                );


            if(!typeOk){

                return false;
            }


            const responsibleDepartment =
                departmentLabel(
                    event.analysis
                    ?.responsible_department
                );


            const departmentOk =
                !state.filters.departments.size
                ||
                state.filters.departments.has(
                    responsibleDepartment
                );


            if(!departmentOk){

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
