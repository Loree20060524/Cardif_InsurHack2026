/* =====================================================
   Latest News Ticker
===================================================== */

function renderTicker(){

    const ticker =
        $('latestTicker');


    const track =
        $('latestTickerTrack');


    const latest =
        state.events.slice(0, 6);


    if(!latest.length){

        ticker.classList.add(
            'hidden'
        );


        track.innerHTML = '';


        return;
    }


    const renderGroup =
        duplicate => `

            <div
                class="ticker-group"
                ${duplicate ? 'aria-hidden="true"' : ''}
            >
                ${latest.map(

                    event => `

                        <button
                            type="button"
                            class="ticker-item"
                            data-ticker-id="${esc(event.id)}"
                            ${duplicate ? 'tabindex="-1"' : ''}
                        >
                            <span>
                                ${esc(sourceType(event))}
                            </span>

                            <time>
                                ${esc(formatEventDate(event))}
                            </time>

                            <strong>
                                ${esc(event.title)}
                            </strong>
                        </button>

                    `
                ).join('')}
            </div>
        `;


    track.innerHTML =
        renderGroup(false)
        +
        renderGroup(true);


    track.style.setProperty(
        '--ticker-duration',
        `${Math.max(36, latest.length * 8)}s`
    );


    ticker.classList.remove(
        'hidden'
    );


    track
    .querySelectorAll('[data-ticker-id]')
    .forEach(

        button => {

            button.onclick =
                () => {

                    state.selected = button.dataset.tickerId;
                    renderList();
                    renderDetail();


                    const selected =
                        document.querySelector(
                            '.event.active'
                        );


                    if(selected){

                        selected.scrollIntoView({
                            behavior:'smooth',
                            block:'nearest',
                        });
                    }
                };
        }
    );
}


/* =====================================================
   Advanced Filters
===================================================== */

function advancedFilterOption(
    value,
    group
){

    const selected =
        state.filterDraft[
            group
        ].has(
            value
        );


    return `
        <label class="advanced-filter-option">
            <input
                type="checkbox"
                data-advanced-filter-group="${esc(group)}"
                value="${esc(value)}"
                ${selected ? 'checked' : ''}
            >
            <span>${esc(value)}</span>
        </label>
    `;
}


function updateAdvancedFilterPresentation(){

    const appliedCount =
        advancedFilterCount();


    const draftCount =
        advancedFilterCount(
            state.filterDraft
        );


    $('advancedFilterButton')
    .classList
    .toggle(
        'active',
        state.advancedFilterOpen
    );


    $('advancedFilterButton')
    .setAttribute(
        'aria-expanded',
        String(
            state.advancedFilterOpen
        )
    );


    $('advancedFilterPanel')
    .classList
    .toggle(
        'hidden',
        !state.advancedFilterOpen
    );


    $('advancedFilterCount').textContent =
        appliedCount;


    $('advancedFilterCount')
    .classList
    .toggle(
        'hidden',
        !appliedCount
    );


    $('advancedFilterDraftSummary').textContent =

        draftCount

        ?

        `已選擇 ${draftCount} 個條件`

        :

        '尚未選擇條件';
}


function renderAdvancedFilters(){

    $('typeFilterOptions').innerHTML =
        EVENT_TYPE_FILTER_OPTIONS
        .map(
            value =>
                advancedFilterOption(
                    value,
                    'types'
                )
        )
        .join('');


    $('departmentFilterOptions').innerHTML =
        responsibleDepartmentOptions()
        .map(
            value =>
                advancedFilterOption(
                    value,
                    'departments'
                )
        )
        .join('');


    $('riskFilterOptions').innerHTML =
        RISK_LEVEL_FILTER_OPTIONS
        .map(
            value =>
                advancedFilterOption(
                    value,
                    'riskLevels'
                )
        )
        .join('');


    $('importanceFilterOptions').innerHTML =
        IMPORTANCE_FILTER_OPTIONS
        .map(
            value =>
                advancedFilterOption(
                    value,
                    'importanceLevels'
                )
        )
        .join('');


    document
    .querySelectorAll(
        '[data-advanced-filter-group]'
    )
    .forEach(

        input => {

            input.onchange =
                () => {

                    const selected =
                        state.filterDraft[
                            input.dataset
                            .advancedFilterGroup
                        ];


                    if(input.checked){

                        selected.add(
                            input.value
                        );

                    }else{

                        selected.delete(
                            input.value
                        );
                    }


                    applyAdvancedFilterDraft(false);
                };
        }
    );


    updateAdvancedFilterPresentation();
}


function setAdvancedFilterOpen(
    open
){

    state.advancedFilterOpen =
        open;


    if(open){

        state.filterDraft =
            copyAdvancedFilters(
                state.filters
            );
    }


    renderAdvancedFilters();
}


function clearAdvancedFilterDraft(){

    state.filterDraft = {
        types:new Set(),
        departments:new Set(),
        riskLevels:new Set(),
        importanceLevels:new Set(),
    };
    state.query = '';
    $('search').value = '';
    applyAdvancedFilterDraft(false);
    renderAdvancedFilters();
}


function applyAdvancedFilterDraft(closePanel=true){

    state.pagination.intel.page = 1;

    state.filters =
        copyAdvancedFilters(
            state.filterDraft
        );


    if(closePanel) state.advancedFilterOpen = false;
    // Keep checkbox focus while applying a change immediately.
    if(closePanel) renderAdvancedFilters();
    else updateAdvancedFilterPresentation();
    renderList();
}

function setIntelSourceType(type){
    state.filters.types = new Set(type === '全部' ? [] : [type]);
    state.filterDraft.types = new Set(state.filters.types);
    state.pagination.intel.page = 1;
    renderAdvancedFilters();
    renderList();
}

function renderActiveIntelFilters(){
    const element = $('intelActiveFilters');
    if(!element) return;
    const labels = {types:'類型', departments:'部門', riskLevels:'風險', importanceLevels:'重要性'};
    const conditions = Object.entries(labels).flatMap(([group,label]) =>
        [...state.filters[group]].map(value => ({group,value,label:`${label}：${value}`})));
    if(state.query.trim()) conditions.unshift({group:'query',value:state.query,label:`關鍵字：${state.query.trim()}`});
    element.hidden = !conditions.length;
    element.innerHTML = conditions.length ? `<span>目前條件</span>${conditions.map(item =>
        `<button type="button" data-filter-group="${item.group}" data-filter-value="${esc(item.value)}" aria-label="移除${esc(item.label)}">${esc(item.label)} <span aria-hidden="true">×</span></button>`
    ).join('')}<button type="button" class="d-clear-filters" data-clear-filters>清除所有篩選</button>` : '';
    element.querySelectorAll('[data-filter-group]').forEach(button => {
        button.onclick = () => {
            const {filterGroup,filterValue} = button.dataset;
            if(filterGroup === 'query'){
                state.query = '';
                $('search').value = '';
            }else state.filters[filterGroup].delete(filterValue);
            state.filterDraft = copyAdvancedFilters(state.filters);
            state.pagination.intel.page = 1;
            renderAdvancedFilters();
            renderList();
        };
    });
    const clear = element.querySelector('[data-clear-filters]');
    if(clear) clear.onclick = clearAdvancedFilterDraft;
}


/* =====================================================
   Event List
===================================================== */

function ledgerEvents(){
    return filteredEvents()
        .slice()
        .sort((a, b) => {
            const dateValue = event => new Date(event.published_at || event.detected_at || 0).getTime() || 0;
            return dateValue(b) - dateValue(a);
        });
}

function renderList(){
    renderActiveIntelFilters();
    const sourceCounts = new Map();

    state.events.forEach(event => {
        const type = sourceType(event);
        sourceCounts.set(type, (sourceCounts.get(type) || 0) + 1);
    });

    const sourceOptions = [
        ['全部', state.events.length],
        ...['法規', '公告', '裁罰', '監理新聞', '監理資訊']
            .filter(type => sourceCounts.has(type))
            .map(type => [type, sourceCounts.get(type)]),
    ];

    $('sourceTypeList').innerHTML = sourceOptions.map(([type, count]) => `
        <button type="button" class="d-source-option ${(type === '全部' ? !state.filters.types.size : state.filters.types.has(type)) ? 'active' : ''}"
            data-source-type="${esc(type)}" aria-pressed="${type === '全部' ? !state.filters.types.size : state.filters.types.has(type)}">
            <span>${esc(type)}</span><small>${count}</small>
        </button>
    `).join('');

    $('sourceTypeList').querySelectorAll('[data-source-type]').forEach(button => {
        button.onclick = () => {
            setIntelSourceType(button.dataset.sourceType);
        };
    });

    const list = ledgerEvents();
    const page = pageWindow('intel', list);
    renderPagination('intel', list, renderList);

    $('ledgerResultCount').textContent = `共 ${list.length} 筆`;
    $('ledgerStatus').textContent = state.lastSync
        ? `${state.events.length} 筆來源資料 · 更新時間 ${formatDate(state.lastSync)}${state.stale ? ' · 部分來源更新受限' : ''}`
        : `${state.events.length} 筆來源資料`;


    if(!list.length){

        $('eventList').innerHTML = `

            <div class="d-empty">
                目前沒有符合條件的監理訊號。
            </div>
        `;

        state.selected = null;
        $('eventDetail').innerHTML = '<div class="d-empty">請調整搜尋或篩選條件。</div>';

        return;
    }

    const previousSelected = state.selected;
    if(!page.items.some(event => event.id === state.selected)){
        state.selected = page.items[0].id;
    }


    $('eventList').innerHTML =

        page.items
        .map(

            event => `

            <button

                type="button"

                class="
                    d-row
                    ${
                        event.id
                        ===
                        state.selected

                        ?

                        'active'

                        :

                        ''
                    }
                "

                data-id="${esc(event.id)}"
            >


                <time class="d-row-date">${esc(formatEventDate(event))}</time>
                <span class="d-row-type">${esc(sourceType(event))}</span>
                <span class="d-row-copy">
                    <strong>${esc(event.title)}</strong>
                    <small>${esc(event.source)}</small>
                </span>


            </button>

            `
        )
        .join('');


    document
    .querySelectorAll(
        '.d-row'
    )
    .forEach(

        button => {

            button.onclick =
                () => {


                    state.selected = button.dataset.id.trim();
                    renderList();
                    renderDetail();
                    if(typeof window !== 'undefined' && window.matchMedia('(max-width:900px)').matches){
                        const detail = $('eventDetail');
                        detail.focus({preventScroll:true});
                        detail.scrollIntoView({block:'start'});
                    }
                };
        }
    );

    if(previousSelected !== state.selected){
        renderDetail();
    }
}
