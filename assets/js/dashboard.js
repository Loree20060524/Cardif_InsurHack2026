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

                    state.selected =
                        button.dataset.tickerId;


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


                    updateAdvancedFilterPresentation();
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
    };


    renderAdvancedFilters();
}


function applyAdvancedFilterDraft(){

    state.filters =
        copyAdvancedFilters(
            state.filterDraft
        );


    state.advancedFilterOpen =
        false;


    const visible =
        filteredEvents();


    if(
        visible.length
        &&
        !visible.some(
            event =>
                event.id
                ===
                state.selected
        )
    ){

        state.selected =
            visible[0].id;
    }


    renderAdvancedFilters();

    renderList();

    renderDetail();
}


/* =====================================================
   Event List
===================================================== */

function renderList(){

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
        <button type="button" class="d-source-option ${state.sourceTypeFilter === type ? 'active' : ''}"
            data-source-type="${esc(type)}" aria-pressed="${state.sourceTypeFilter === type}">
            <span>${esc(type)}</span><small>${count}</small>
        </button>
    `).join('');

    $('sourceTypeList').querySelectorAll('[data-source-type]').forEach(button => {
        button.onclick = () => {
            state.sourceTypeFilter = button.dataset.sourceType;
            renderList();
        };
    });

    const allFiltered = filteredEvents();
    const list = allFiltered
        .filter(event => state.sourceTypeFilter === '全部' || sourceType(event) === state.sourceTypeFilter)
        .slice()
        .sort((a, b) => {
            const dateValue = event => event.published_at || event.detected_at || '';
            return new Date(dateValue(b)).getTime() - new Date(dateValue(a)).getTime();
        });

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
    if(!list.some(event => event.id === state.selected)){
        state.selected = list[0].id;
    }


    $('eventList').innerHTML =

        list
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


                    state.selected =
                        button.dataset.id.trim();


                    renderList();


                    renderDetail();
                };
        }
    );

    if(previousSelected !== state.selected){
        renderDetail();
    }
}
