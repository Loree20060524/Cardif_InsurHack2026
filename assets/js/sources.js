/* =====================================================
   Source Status
===================================================== */

function groupHealth(
    items
){

    const ok =

        items.filter(

            (
                [
                    ,
                    source
                ]
            ) =>
                source.ok

        ).length;


    if(
        ok
        ===
        items.length
    ){

        return 'ok';
    }


    if(
        ok > 0
    ){

        return 'partial';
    }


    return 'fail';
}


function groupStatusText(
    items
){

    const ok =

        items.filter(

            (
                [
                    ,
                    source
                ]
            ) =>
                source.ok

        ).length;


    if(
        ok
        ===
        items.length
    ){

        return '正常';
    }


    if(
        ok > 0
    ){

        return '部分來源可用';
    }


    return '暫時無法更新';
}


function sourceStatusText(
    source
){

    const labels = {

        updated:
            '已更新',

        not_modified:
            '本次無異動',

        source_cooldown:
            '使用既有資料',

        manual_cooldown:
            '更新冷卻中',

        http_error:
            '來源連線異常',

        ssl_error:
            'SSL 憑證異常',

        timeout:
            '連線逾時',

        dns_error:
            '網域解析異常',

        network_error:
            '網路連線異常',

        parse_error:
            '資料解析異常',

        robots_blocked:
            '依網站規則停止擷取',

        error:
            '來源暫時異常',
    };


    return (

        `${
            labels[
                source.status
            ]
            ||
            '來源狀態'
        } · ${
            source.count
            ||
            0
        } 筆`
    );
}


function renderSources(){

    const entries =
        Object.entries(
            sourceGroups()
        );


    if(
        !entries.length
    ){

        $('sourceStatusList').innerHTML = `

            <div class="empty">

                尚未取得資料來源狀態。

            </div>
        `;

        return;
    }


    $('sourceStatusList').innerHTML =

        entries
        .map(

            (
                [
                    group,
                    items
                ]
            ) => `

            <div class="source-group">


                <div class="source-group-head">


                    <b>


                        <span
                            class="
                                dot
                                ${groupHealth(items)}
                            "
                        >
                        </span>


                        ${esc(group)}


                    </b>


                    <small>

                        ${esc(
                            groupStatusText(
                                items
                            )
                        )}

                    </small>


                </div>


                ${
                    items
                    .map(

                        (
                            [
                                key,
                                source
                            ]
                        ) => `

                        <details class="source-pipe">


                            <summary>


                                <span>

                                    ${esc(
                                        source.label
                                        ||
                                        key
                                    )}

                                </span>


                                <span>

                                    ${esc(
                                        sourceStatusText(
                                            source
                                        )
                                    )}

                                </span>


                            </summary>


                            <div class="diag">


                                <div>

                                    接入方式：

                                    ${esc(
                                        source.access_type
                                        ||
                                        '—'
                                    )}

                                </div>


                                <div>

                                    來源網域：

                                    ${esc(
                                        source.endpoint_host
                                        ||
                                        '—'
                                    )}

                                </div>


                                <div>

                                    上次檢查：

                                    ${esc(
                                        formatDateTime(
                                            source.checked_at
                                        )
                                    )}

                                </div>


                                <div>

                                    上次成功：

                                    ${esc(
                                        formatDateTime(
                                            source.last_success_at
                                        )
                                    )}

                                </div>


                                ${
                                    source.error

                                    ?

                                    `
                                    <div class="diag-error">

                                        ${esc(source.error)}

                                    </div>
                                    `

                                    :

                                    ''
                                }


                                <div
                                    style="
                                        margin-top:8px
                                    "
                                >


                                    ${
                                        source.dataset_url

                                        ?

                                        `
                                        <a

                                            href="${esc(
                                                source.dataset_url
                                            )}"

                                            target="_blank"

                                            rel="noopener noreferrer"
                                        >

                                            查看官方資料集

                                        </a>
                                        `

                                        :

                                        ''
                                    }


                                    ${
                                        source.dataset_url
                                        &&
                                        source.public_url

                                        ?

                                        '　'

                                        :

                                        ''
                                    }


                                    ${
                                        source.public_url

                                        ?

                                        `
                                        <a

                                            href="${esc(
                                                source.public_url
                                            )}"

                                            target="_blank"

                                            rel="noopener noreferrer"
                                        >

                                            查看官方網站

                                        </a>
                                        `

                                        :

                                        ''
                                    }


                                </div>


                            </div>


                        </details>

                        `
                    )
                    .join('')
                }


            </div>

            `
        )
        .join('');
}


/* =====================================================
   System Status
===================================================== */

function updateSystemStatus(){

    const groups =
        sourceGroups();


    const total =
        Object.keys(
            groups
        ).length;


    const healthy =
        sourceHealthyGroupCount();


    $('systemStatus').innerHTML =

        `${healthy}/${total || 5} 類來源可用`

        +

        ` · `

        +

        `<b>${
            state.stale
            ?
            '部分來源異常'
            :
            '資料已更新'
        }</b>`;


    $('aiStatus').innerHTML =

        state.ai.enabled

        ?

        (
            `<b>AI 已啟用</b> · `

            +

            `${
                esc(
                    state.ai.provider
                    ||
                    'Ollama（本機）'
                )
            }`

            +

            (
                state.ai.model

                ?

                ` · ${esc(
                    state.ai.model
                )}`

                :

                ''
            )
        )

        :

        '<b>AI 未啟用</b> · 規則備援';
}
