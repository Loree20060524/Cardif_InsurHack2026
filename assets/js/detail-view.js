/* =====================================================
   Detail
===================================================== */

function renderDetail(
    triggerAI=true
){

    const event = state.selected === null
        ? null
        : (
            state.events.find(
                item => item.id === state.selected
            )
            || state.events[0]
        );


    if(!event){

        $('eventDetail').innerHTML = `
            <div class="d-empty">
                ${state.events.length ? '請調整搜尋或篩選條件。' : '尚未取得可顯示的監理資訊。'}
            </div>
        `;

        return;
    }


    state.selected =
        event.id;


    const analysis =
        event.analysis
        ||
        {};


    const isAI =
        analysis.analysis_mode
        ===
        'AI 深度分析';


    const aiIsLoading =
        state.aiLoading.has(
            event.id
        );

    const aiFailed =
        state.aiFailed.has(
            event.id
        );

    const aiHasInsufficientContent =
        /未提供可解析的/.test(
            analysis.analysis_note || ''
        );


    const regulatoryPoints =
        analysis.regulatory_points
        ||
        [];


    const departments =
        analysis.departments
        ||
        [];


    const processes =
        analysis.impact_processes
        ||
        [];


    const attention =
        analysis.attention_items
        ||
        [];


    const actions =
        analysis.actions
        ||
        [];


    const eventNature =
        analysis.event_nature
        ||
        '';


    const showNature =

        eventNature
        ===
        '裁罰／處分'

        &&

        sourceType(
            event
        )
        !==
        '裁罰';


    $('eventDetail').innerHTML = `


        <div class="detail-title">


            <div class="detail-meta">


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


                ${
                    showNature

                    ?

                    `
                    <span class="workflow">

                        系統判斷：

                        ${esc(eventNature)}

                    </span>
                    `

                    :

                    ''
                }


                <span

                    id="aiAnalysisStatus"

                    class="
                        workflow
                        ${
                            isAI

                            ?

                            'ai'

                            :

                            (
                                aiIsLoading

                                ?

                                'ai-loading'

                                :

                                ''
                            )
                        }
                    "
                >

                    ${
                        isAI

                        ?

                        'AI 深度分析'

                        :

                        (
                            state.ai.enabled

                            ?

                            (
                                aiIsLoading

                                ?

                                'AI 分析中…'

                                :

                                (
                                    aiFailed

                                    ?

                                    'AI 分析未完成'

                                    :

                                    'AI 待分析'
                                )
                            )

                            :

                            '規則備援'
                        )
                    }

                </span>


            </div>


            <h2>

                ${esc(
                    event.title
                )}

            </h2>


            <p>

                ${esc(
                    formatEventDate(
                        event
                    )
                )}

                ·

                ${esc(
                    analysis.analysis_note

                    ||

                    (
                        '系統提供初步整理，'
                        +
                        '最終適用性仍需由'
                        +
                        '相關單位確認。'
                    )
                )}

            </p>


            ${
                (isAI || state.ai.enabled)

                ?

                `
                <div class="ai-grid">


                    <div class="ai-stat">

                        <span>
                            風險程度
                        </span>

                        <b>

                            ${esc(
                                isAI
                                ? (analysis.risk_level || '待確認')
                                : (aiIsLoading ? '分析中…' : '待 AI 分析')
                            )}

                        </b>

                    </div>


                    <div class="ai-stat">

                        <span>
                            重要性
                        </span>

                        <b>

                            ${esc(
                                isAI
                                ? (analysis.importance || '待確認')
                                : (aiIsLoading ? '分析中…' : '待 AI 分析')
                            )}

                        </b>

                    </div>


                    <div class="ai-stat">

                        <span>
                            主要責任部門
                        </span>

                        <b>

                                ${esc(
                                    isAI
                                    ? departmentLabel(analysis.responsible_department || '待確認')
                                    : (aiIsLoading ? '分析中…' : '待 AI 分析')
                                )}

                        </b>

                    </div>


                </div>
                `

                :

                ''
            }


        </div>


        <div class="block">


            <h3>

                ${
                    isAI

                    ?

                    'AI 重點摘要'

                    :

                    '發生什麼？'
                }

            </h3>


            <div class="summary">

                ${esc(
                    analysis.summary

                    ||

                    event.description

                    ||

                    '尚無摘要'
                )}


                <br>


                <a

                    class="source-link"

                    href="${esc(event.url)}"

                    target="_blank"

                    rel="noopener noreferrer"
                >

                    查看官方原始來源 →

                </a>


            </div>


        </div>


        <div class="block">


            <h3>
                監理影響圖
            </h3>


            ${renderImpactChain(
                analysis
            )}


        </div>


        ${
            regulatoryPoints.length

            ?

            `
            <div class="block">


                <h3>
                    ${isAI ? 'AI 判讀的監理重點' : '初步監理重點'}
                </h3>


                <ul class="attention-list">

                    ${
                        regulatoryPoints
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


        <div class="block">


            <h3>
                哪些部門可能受影響？
            </h3>


            <div class="impact-row">


                ${
                    departments.length

                    ?

                    departments
                    .map(

                        item => `

                        <div class="impact">


                            <b>

                                ${esc(
                                    departmentLabel(
                                        item.department
                                    )
                                )}

                            </b>


                            <p>
                                ${esc(item.reason)}
                            </p>


                        </div>

                        `
                    )
                    .join('')

                    :

                    `
                    <div class="empty">

                        尚待確認可能受影響的單位。

                    </div>
                    `
                }


            </div>


        </div>


        <div class="block">


            <h3>
                可能受影響流程
            </h3>


            ${renderProcesses(
                processes
            )}


        </div>


        <div class="block">


            <h3>
                需要注意的事項
            </h3>


            ${
                attention.length

                ?

                `
                <ul class="attention-list">

                    ${
                        attention
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
                `

                :

                `
                <div class="empty">

                    尚無額外注意事項。

                </div>
                `
            }


        </div>


        <div class="block">


            <h3>
                建議因應
            </h3>


            ${
                actions.length

                ?

                `
                <ul class="recommendations">

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
                `

                :

                `
                <div class="empty">

                    待相關單位確認後建立因應措施。

                </div>
                `
            }


        </div>


        <div class="ai-note">


            ${
                state.ai.enabled

                ?

                (
                    isAI

                    ?

                    `此分析由 ${
                        esc(
                            analysis.ai_provider
                            ||
                            state.ai.provider
                            ||
                            '本機 AI'
                        )
                    }｜${
                        esc(
                            analysis.ai_model
                            ||
                            state.ai.model
                            ||
                            '語言模型'
                        )
                    } 依官方來源內容產生，並保留人工覆核。`

                    :

                    (
                        aiIsLoading

                        ?

                        'AI 正在讀取官方來源內容並進行監理影響分析。'

                        :

                        (
                            aiFailed

                            ?

                            'AI 深度分析尚未完成；以下內容為規則備援結果，請人工覆核。'

                            :

                            '以下先顯示規則備援結果；AI 深度分析完成後會更新風險、影響部門與因應建議。'
                        )
                    )
                )

                :

                'AI 尚未啟用，目前顯示規則式備援內容。'
            }


        </div>


        ${
            state.ai.enabled

            ?

            `
            <div class="d-ai-controls">
                ${
                    aiIsLoading
                    ? '<span>正在依來源內容進行分析…</span>'
                    : (
                        aiHasInsufficientContent
                        ? '<span>來源內文不足，暫無法進行可靠的深度分析。</span>'
                        : `<button type="button" class="d-detail-retry" id="retryAI">${aiFailed ? '重試 AI 分析' : '進行 AI 深度分析'}</button>`
                    )
                }
            </div>
            `

            :

            ''
        }


        <div class="detail-actions">


            <button

                class="btn primary"

                id="makeBrief"
            >

                產生主管摘要

            </button>


            <button

                class="btn"

                id="copyLink"
            >

                複製官方來源連結

            </button>


        </div>


    `;


    $('makeBrief').onclick =
        () =>
            showSingleBrief(
                event
            );


    $('copyLink').onclick =
        async () => {


            try{

                await navigator
                .clipboard
                .writeText(
                    event.url
                );


                toast(
                    '已複製官方來源連結。'
                );

            }

            catch{

                toast(
                    '瀏覽器未允許自動複製。'
                );
            }
        };

    const retryAIButton = $('retryAI');
    if(retryAIButton){
        retryAIButton.onclick = () => {
            state.aiFailed.delete(event.id);
            state.aiRequested.delete(event.id);
            ensureAIAnalysis(event);
            renderDetail(false);
        };
    }


    if(triggerAI){

        ensureAIAnalysis(
            event
        );
    }
}


/* =====================================================
   Single Event Brief
===================================================== */

function showSingleBrief(
    event
){

    const analysis =
        event.analysis
        ||
        {};


    const departments = (

        analysis.departments
        ||
        []

    )
    .slice(
        0,
        3
    )
    .map(

        item =>
            departmentLabel(
                item.department
            )
    )
    .join(
        '、'
    )

    ||

    '待確認';


    const processes = (

        analysis.impact_processes
        ||
        []

    )
    .slice(
        0,
        3
    )
    .map(

        item =>
            item.process
    )
    .join(
        '、'
    )

    ||

    '待確認';


    const mainDepartment =
        departmentLabel(

            analysis.responsible_department

            ||

            analysis.departments?.[0]?.department

            ||

            '待確認'
        );


    alert(

`${
    analysis.analysis_mode === 'AI 深度分析'
    ?
    'AI 主管摘要'
    :
    '主管摘要（規則備援）'
}

事件：${event.title}

事件類型：${analysis.event_nature || sourceType(event)}

風險程度：${analysis.risk_level || '待確認'}

重要性：${analysis.importance || '待確認'}

主要責任部門：${mainDepartment}

可能受影響部門：${departments}

可能受影響流程：${processes}

主管重點：${analysis.management_summary || analysis.summary || '待確認'}

※ AI／系統分析供初步研判，最終判斷仍應由相關單位確認。`

    );
}
