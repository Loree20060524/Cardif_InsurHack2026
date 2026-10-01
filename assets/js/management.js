/* =====================================================
   Management Events
===================================================== */

function managementEvents(){

    const typeOrder = {

        '裁罰':4,

        '法規':3,

        '公告':2,

        '監理新聞':1,
    };


    const riskOrder = {

        '高':4,

        '中':3,

        '低':2,

        '待確認':1,
    };


    return [

        ...state.events

    ]
    .sort(

        (
            a,
            b
        ) => {


            const analysisA =
                a.analysis
                ||
                {};


            const analysisB =
                b.analysis
                ||
                {};


            const riskDifference =

                (
                    riskOrder[
                        analysisB.risk_level
                    ]
                    ||
                    0
                )

                -

                (
                    riskOrder[
                        analysisA.risk_level
                    ]
                    ||
                    0
                );


            if(
                riskDifference
                !==
                0
            ){

                return riskDifference;
            }


            const typeDifference =

                (
                    typeOrder[
                        sourceType(b)
                    ]
                    ||
                    0
                )

                -

                (
                    typeOrder[
                        sourceType(a)
                    ]
                    ||
                    0
                );


            if(
                typeDifference
                !==
                0
            ){

                return typeDifference;
            }


            return (

                new Date(
                    b.published_at
                    ||
                    0
                ).getTime()

                -

                new Date(
                    a.published_at
                    ||
                    0
                ).getTime()
            );
        }
    )
    .slice(
        0,
        5
    );
}


/* =====================================================
   Management View
===================================================== */

function renderManagement(){

    const events =
        managementEvents();


    $('priorityList').innerHTML =

        events.length

        ?

        events
        .map(

            (
                event,
                index
            ) => {


                const analysis =
                    event.analysis
                    ||
                    {};


                return `

                <div class="priority-item">


                    <div class="rank">

                        ${index + 1}

                    </div>


                    <div>


                        <h4>

                            ${esc(
                                event.title
                            )}

                        </h4>


                        <p>

                            ${
                                analysis.risk_level

                                ?

                                `風險程度：${
                                    esc(
                                        analysis.risk_level
                                    )
                                } · `

                                :

                                ''
                            }

                            可能涉及：

                            ${
                                (
                                    analysis.departments
                                    ||
                                    []
                                )
                                .slice(
                                    0,
                                    2
                                )
                                .map(

                                    item =>

                                        esc(
                                            departmentLabel(
                                                item.department
                                            )
                                        )
                                )
                                .join(
                                    '、'
                                )

                                ||

                                '待確認'
                            }

                        </p>


                    </div>


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


                </div>

                `;
            }
        )
        .join('')

        :

        `
        <div class="empty">

            目前尚無足夠資訊。

        </div>
        `;


    renderTopics();
}


/* =====================================================
   Topic Trends
===================================================== */

function renderTopics(){

    const topics = [

        [

            '招攬／公平待客',

            [
                '招攬',
                '公平待客',
                '適合度',
                '業務員'
            ]
        ],


        [

            '資安／個資',

            [
                '資安',
                '個資',
                '資訊安全',
                '個人資料'
            ]
        ],


        [

            '內控／法遵',

            [
                '內部控制',
                '法遵',
                '法令遵循',
                '稽核'
            ]
        ],


        [

            '商品／精算',

            [
                '商品',
                '精算',
                '準備金',
                '費率'
            ]
        ],


        [

            '資本／清償能力',

            [
                '清償能力',
                '資本適足',
                '風險資本',
                'TIS',
                'ICS'
            ]
        ],


        [

            '投資管理',

            [
                '投資',
                '有價證券',
                '資產配置',
                '投資限額'
            ]
        ],
    ];


    const dated = state.events
        .map(event => ({ event, date: Date.parse(event.published_at || '') }))
        .filter(item => Number.isFinite(item.date));

    if (!dated.length) {
        $('trendList').innerHTML = '<p>目前沒有足夠的發布日期可比較主題變化。</p>';
        return;
    }

    const anchor = Math.max(...dated.map(item => item.date));
    const day = 24 * 60 * 60 * 1000;
    const recentStart = anchor - 30 * day;
    const priorStart = anchor - 60 * day;

    const counts = topics.map(([name, keywords]) => {
        const matches = dated.filter(({event, date}) => {
            if (date < priorStart || date > anchor) return false;
            // Count only official source text, never generated fallback advice.
            const text = `${event.title || ''} ${event.description || ''}`.toLowerCase();
            return keywords.some(keyword => text.includes(keyword.toLowerCase()));
        });
        return {
            name,
            recent: matches.filter(item => item.date >= recentStart).length,
            prior: matches.filter(item => item.date < recentStart).length,
        };
    }).sort((a, b) => b.recent - a.recent || b.prior - a.prior);

    const max = Math.max(1, ...counts.map(item => item.recent));
    const anchorLabel = new Date(anchor).toLocaleDateString('zh-TW');

    $('trendList').innerHTML = `
        <p class="trend-scope">以最新事件 ${esc(anchorLabel)} 為基準；近 30 日與前 30 日比較。僅計入目前收錄且有發布日期的官方事件。</p>
        ${counts.map(({name, recent, prior}) => `

            <div class="trend-row">


                <span>
                    ${esc(name)}
                </span>


                <div class="track">


                    <div

                        class="fill"

                        style="
                            width:
                            ${
                                Math.round(
                                    recent
                                    /
                                    max
                                    *
                                    100
                                )
                            }%
                        "
                    >
                    </div>


                </div>


                <b>
                    ${recent} / ${prior}
                </b>


            </div>

            `).join('')}`;
}


/* =====================================================
   AI Management Summary
===================================================== */

async function generateManagementReport(){

    const button =
        $('reportBtn');


    const box =
        $('reportBox');


    button.disabled =
        true;


    button.textContent =
        '分析中…';


    box
    .classList
    .remove(
        'hidden'
    );


    box.innerHTML = `

        <div class="management-report-title">

            管理摘要產生中…

        </div>


        <div class="management-summary-text">

            AI 正在綜合近期監理事件，
            分析近期風險、優先事件與重複出現的監理主題。

        </div>

    `;


    try{

        const response =
            await fetch(

                '/api/management-summary',

                {
                    cache:'no-store'
                }
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.ok
        ){

            throw new Error(

                data.error

                ||

                `HTTP ${response.status}`
            );
        }


        const report =
            data.summary
            ||
            {};


        const events =

            Array.isArray(
                report.priority_events
            )

            ?

            report.priority_events

            :

            [];


        const actions =

            Array.isArray(
                report.priority_actions
            )

            ?

            report.priority_actions

            :

            [];


        const trends =

            Array.isArray(
                report.trend_observations
            )

            ?

            report.trend_observations

            :

            [];


        box.innerHTML = `


            <div class="management-report-title">

                ${esc(
                    report.headline
                    ||
                    '本期監理事件管理摘要'
                )}

            </div>


            <div class="management-overview">


                <div class="management-stat">

                    <span>
                        整體風險程度
                    </span>

                    <b>

                        ${esc(
                            report.risk_outlook
                            ||
                            '待確認'
                        )}

                    </b>

                </div>


                <div class="management-stat">

                    <span>
                        優先關注事件
                    </span>

                    <b>
                        ${events.length} 件
                    </b>

                </div>


                <div class="management-stat">

                    <span>
                        近期主題觀察
                    </span>

                    <b>
                        ${trends.length} 項
                    </b>

                </div>


            </div>


            <div class="management-section">


                <h3>
                    管理重點
                </h3>


                <div class="management-summary-text">

                    ${esc(
                        report.summary
                        ||
                        '目前尚無足夠資訊產生管理摘要。'
                    )}

                </div>


            </div>


            ${
                events.length

                ?

                `
                <div class="management-section">


                    <h3>
                        優先關注事件
                    </h3>


                    ${
                        events
                        .map(

                            (
                                item,
                                index
                            ) => `

                            <div class="management-event">


                                <div class="management-event-number">

                                    ${
                                        String(
                                            index + 1
                                        )
                                        .padStart(
                                            2,
                                            '0'
                                        )
                                    }

                                </div>


                                <div>


                                    <b>

                                        ${esc(
                                            item.title
                                            ||
                                            '未命名事件'
                                        )}

                                    </b>


                                    <p>

                                        ${esc(
                                            item.reason
                                            ||
                                            (
                                                '建議確認事件對'
                                                +
                                                '公司的實際影響。'
                                            )
                                        )}

                                    </p>


                                </div>


                            </div>

                            `
                        )
                        .join('')
                    }


                </div>
                `

                :

                ''
            }


            ${
                trends.length

                ?

                `
                <div class="management-section">


                    <h3>
                        近期主題觀察
                    </h3>


                    ${
                        trends
                        .map(

                            item => `

                            <div class="trend-observation">

                                ${esc(item)}

                            </div>

                            `
                        )
                        .join('')
                    }


                </div>
                `

                :

                ''
            }


            ${
                actions.length

                ?

                `
                <div class="management-section">


                    <h3>
                        建議管理方向
                    </h3>


                    <ul class="management-actions">


                        ${
                            actions
                            .map(

                                item => `

                                <li>

                                    ${esc(item)}

                                </li>

                                `
                            )
                            .join('')
                        }


                    </ul>


                </div>
                `

                :

                ''
            }


            <div class="management-note">


                <b>
                    系統說明：
                </b>


                ${esc(
                    report.management_note
                    ||
                    (
                        '本摘要供管理階層快速掌握'
                        +
                        '監理風險與趨勢，最終適用性'
                        +
                        '仍需由相關單位確認。'
                    )
                )}


            </div>


        `;

    }

    catch(error){

        console.error(
            error
        );


        box.innerHTML = `

            <div class="management-report-title">

                管理摘要暫時無法產生

            </div>


            <div class="management-summary-text">

                請確認本機 Ollama 服務與模型是否正常運作。

                <br><br>

                ${esc(error.message)}

            </div>

        `;
    }

    finally{

        button.disabled =
            false;


        button.textContent =
            '產生 AI 管理摘要';
    }
}
