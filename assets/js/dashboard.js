/* =====================================================
   Metrics
===================================================== */

function renderMetrics(){

    const penalties =

        state.events.filter(

            event =>

                sourceType(
                    event
                )
                ===
                '裁罰'

        ).length;


    const laws =

        state.events.filter(

            event =>

                sourceType(
                    event
                )
                ===
                '法規'

                &&

                !!event.change_status

        ).length;


    const sourceCount =
        Object.keys(
            sourceGroups()
        ).length;


    const items = [

        [

            '最新訊號',

            state.events.length,

            '目前偵測到的相關監理資訊'
        ],

        [

            '裁罰案例',

            penalties,

            '可比對同業缺失與內部流程'
        ],

        [

            '法規異動',

            laws,

            '確認異動內容與生效時程'
        ],

        [

            '資料來源',

            sourceCount,

            '官方與公開監理來源'
        ],
    ];


    $('metrics').innerHTML =

        items
        .map(

            item => `

            <div class="metric">

                <span>
                    ${esc(item[0])}
                </span>

                <strong>
                    ${esc(item[1])}
                </strong>

                <small>
                    ${esc(item[2])}
                </small>

            </div>

            `
        )
        .join('');
}


/* =====================================================
   Event List
===================================================== */

function renderList(){

    const list =
        filteredEvents();


    if(!list.length){

        $('eventList').innerHTML = `

            <div class="empty">
                目前沒有符合條件的監理訊號。
            </div>
        `;

        return;
    }


    $('eventList').innerHTML =

        list
        .map(

            event => `

            <button

                class="
                    event
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

                data-id="
                    ${esc(event.id)}
                "
            >


                <div class="event-top">


                    <span
                        class="
                            badge
                            ${sourceTone(event)}
                        "
                    >

                        ${esc(
                            sourceType(
                                event
                            )
                        )}

                    </span>


                    ${
                        event.change_status

                        ?

                        `
                        <span class="workflow">

                            ${esc(
                                event.change_status
                            )}

                        </span>
                        `

                        :

                        ''
                    }


                    <time>

                        ${esc(
                            formatDate(
                                event.published_at
                            )
                        )}

                    </time>


                </div>


                <h4>

                    ${esc(
                        event.title
                    )}

                </h4>


                <p>

                    ${esc(
                        event.source
                    )}

                    ·

                    ${esc(
                        workflowStatus(
                            event
                        )
                    )}

                </p>


            </button>

            `
        )
        .join('');


    document
    .querySelectorAll(
        '.event'
    )
    .forEach(

        button => {

            button.onclick =
                () => {


                    state.selected =
                        button.dataset.id;


                    renderList();


                    renderDetail();
                };
        }
    );
}
