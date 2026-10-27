/* =====================================================
   Detail
===================================================== */

function eventReviewPresentation(analysis){
    if(analysis.analysis_mode !== 'AI 深度分析') return null;
    const review = analysis.support_review;
    if(!review){
        return {tone:'pending', label:'依據待核對',
            message:'此分析尚未做來源支持核對，可重新分析以補齊紀錄。', canRetry:true};
    }
    const counts = ['requested', 'supported', 'withheld', 'unverified'];
    const validCounts = counts.every(key=>Number.isInteger(review[key]) && review[key] >= 0)
        && review.requested > 0 && review.supported + review.withheld === review.requested
        && review.unverified <= review.withheld;
    if(!validCounts){
        return {tone:'pending', label:'依據待核對',
            message:'目前尚無完整的來源核對紀錄，可重新分析後查看結果。', canRetry:true};
    }
    if(review.unverified > 0){
        return {tone:'pending', label:'部分依據待核對',
            message:`本次有 ${review.unverified} 項結論尚待完成來源核對，相關判讀暫不顯示。可查看核對明細或重新分析。`, canRetry:true};
    }
    return {tone:'complete', label:'依據已核對',
        message:review.withheld > 0
            ? `已完成 ${review.requested} 項來源核對，保留 ${review.supported} 項具原文支持的內容；其餘 ${review.withheld} 項未採用。`
            : `已完成 ${review.requested} 項來源核對，引用原文與逐項結果可於下方查看。`, canRetry:false};
}

function renderEventEvidence(analysis, {isLoading=false, updateFailed=false}={}){
    const presentation = eventReviewPresentation(analysis);
    if(!presentation) return '';
    const review = analysis.support_review;
    const sources = new Map((review?.sources || []).map(source=>[source.source_id, source]));
    const labels = {summary:'摘要', management_summary:'主管摘要', event_nature:'事件性質', rating:'分級理由',
        responsible_department:'建議關注部門', regulatory_points:'監理重點', departments:'部門影響',
        impact_processes:'流程影響', attention_items:'注意事項', actions:'建議做法'};
    const link = source=>{
        try{
            const url = new URL(source.url);
            if(['https:', 'http:'].includes(url.protocol)){
                return `<a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">${esc(source.title || '官方來源')}</a>`;
            }
        }catch(_){ /* Keep the title readable when the URL is unavailable. */ }
        return esc(source.title || '官方來源');
    };
    return `
        <section class="detail-evidence-panel ${presentation.tone}" aria-label="分析依據核對">
            <div class="detail-evidence-header">
                <div>
                    <strong>來源核對</strong>
                    <p role="status">${esc(presentation.message)}</p>
                </div>
                ${presentation.canRetry && state.ai.enabled ? `<button type="button" class="detail-review-retry" id="retryEvidenceReview" ${isLoading ? 'disabled' : ''}>${isLoading ? '重新分析中…' : '重新分析'}</button>` : ''}
            </div>
            ${updateFailed && presentation.tone === 'complete' ? '<p class="detail-review-update">本次更新未完成，目前顯示前次已核對的分析結果。</p>' : ''}
        ${review ? `
        <details class="block detail-review">
            <summary>查看原文與核對明細</summary>
            <p>核對 ${esc(review.requested)} 項，保留 ${esc(review.supported)} 項，省略 ${esc(review.withheld)} 項。</p>
            ${analysis.verification_notice ? `<p>${esc(analysis.verification_notice)}</p>` : ''}
            <p>採模型判讀、條件及金額檢查，仍可能誤判或漏判；法規適用性須由專業人員確認。</p>
            ${review.source_is_excerpt ? '<p>本次只核對生成時使用的來源節錄，未涵蓋全文。</p>' : ''}
            ${review.program_facts ? `<p>${esc(review.program_facts)}。這部分由程式整理，未計入模型核對項數。</p>` : ''}
            ${(review.checks || []).map(row=>`<div class="detail-review-item">
                <b>${esc(labels[row.id.split(':')[0]] || '分析內容')} · ${row.status === 'supported' ? '保留' : (row.status === 'unverified' ? '未完成核對' : '省略')}</b>
                ${row.status === 'supported' ? `<p>${esc(row.text)}</p>${(row.citations || []).map(citation=>`<blockquote>${esc(citation.quote)}<br>${link(sources.get(citation.source_id) || {})}</blockquote>`).join('')}` : `<p>${esc(row.reason)}</p>`}
            </div>`).join('')}
        </details>` : ''}
        </section>`;
}

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

    const hasLawComparison = analysis.content_source === '官方條文前後對照';

    const analysisNote = String(analysis.analysis_note || '')
        .replace(/規則(?:式)?備援(?:分析|結果|內容)?/g, '依規則產生的初步整理')
        .replace(/(?:AI\s*)?深度分析/g, 'AI 分析');


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

    const showAnalysisValues =
        isAI || aiFailed || aiHasInsufficientContent;
    let analysisStatus = isAI ? 'AI 分析' : (state.ai.enabled ? (aiHasInsufficientContent ? 'AI 分析未完成' : 'AI 待分析') : '初步整理');
    if(aiFailed && !isAI) analysisStatus = 'AI 分析未完成';
    if(aiIsLoading) analysisStatus = isAI ? '重新分析中…' : 'AI 分析中…';
    const reviewPresentation = eventReviewPresentation(analysis);

    const unresolvedAiFields =
        isAI
        ? [
            ['風險程度', analysis.risk_level],
            ['重要性', analysis.importance],
        ]
            .filter(([, value]) => !value || value === '待確認')
            .map(([label]) => label)
        : [];


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


                <span id="aiAnalysisStatus" role="status" class="workflow ${aiIsLoading ? 'ai-loading' : (isAI ? 'ai' : '')}">
                    ${esc(analysisStatus)}
                </span>
                ${reviewPresentation ? `<span id="aiReviewStatus" class="workflow review-${reviewPresentation.tone}" title="${esc(reviewPresentation.message)}">${esc(reviewPresentation.label)}</span>` : ''}


            </div>


            <h2>

                ${esc(
                    event.title
                )}

            </h2>


            <p>${esc(formatEventDate(event))} · ${esc(event.source || '官方資料')}</p>
            ${!isAI && analysisNote ? `<p class="detail-source-note">${esc(analysisNote)}</p>` : ''}
            ${unresolvedAiFields.length ? `<p class="detail-source-note">${esc(unresolvedAiFields.join('、'))}的分級依據尚待確認，目前暫不顯示評級。</p>` : ''}


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
                                showAnalysisValues
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
                                showAnalysisValues
                                ? (analysis.importance || '待確認')
                                : (aiIsLoading ? '分析中…' : '待 AI 分析')
                            )}

                        </b>

                    </div>


                    <div class="ai-stat">

                        <span>
                            建議關注部門
                        </span>

                        <b>

                                ${esc(
                                    showAnalysisValues
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
            <p class="detail-rating-reason">關注部門依公開監理資訊初步推估，實際適用性與權責須由公司確認。</p>
            ${analysis.rating_reason && analysis.support_review ? `<p class="detail-rating-reason">分級依據：${esc(analysis.rating_reason)}</p>` : ''}


        </div>

        ${renderEventEvidence(analysis, {isLoading:aiIsLoading, updateFailed:aiFailed})}

        <div class="block">


            <h3>

                ${
                    isAI

                    ?

                    (hasLawComparison ? '條文差異摘要' : '重點摘要')

                    :

                    '內容摘要'
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


        ${renderLawComparisonSection(event)}

        <details class="block detail-impact-overview">
            <summary>查看影響關聯圖</summary>
            ${renderImpactChain(
                analysis
            )}


        </details>


        ${
            regulatoryPoints.length

            ?

            `
            <div class="block">


                <h3>
                    ${hasLawComparison ? '已確認的文字差異' : (isAI ? '監理重點' : '初步監理重點')}
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
                ${hasLawComparison || analysis.support_review ? '可能受影響部門（初步判讀）' : '受影響部門'}
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

                        目前尚無可列示的部門影響判讀，待完成適用性評估後確認。

                    </div>
                    `
                }


            </div>


        </div>


        <div class="block">


            <h3>
                ${hasLawComparison || analysis.support_review ? '可能受影響流程（初步判讀）' : '可能受影響流程'}
            </h3>


            ${renderProcesses(
                processes
            )}


        </div>


        <div class="block">


            <h3>
                ${hasLawComparison ? '注意事項（AI 推論）' : '注意事項'}
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

                    ${analysis.support_review ? '目前尚無具充分依據的注意事項，可參閱官方原文。' : '尚無額外注意事項。'}

                </div>
                `
            }


        </div>


        <div class="block">


            <h3>
                建議做法
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


        <${isAI ? 'details' : 'div'} class="ai-note">
            ${isAI ? '<summary>分析說明與模型資訊</summary>' : ''}
            ${isAI && analysisNote ? `<p>${esc(analysisNote)}</p>` : ''}


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
                            (aiFailed || aiHasInsufficientContent)

                            ?

                            (
                                aiHasInsufficientContent
                                ? '官方來源未提供可解析內容，以下為依規則產生的初步整理；取得完整原文後才能進行 AI 分析。'
                                : 'AI 分析尚未完成；以下為依規則產生的初步整理，請人工覆核。'
                            )

                            :

                            '以下先顯示依規則產生的初步整理；AI 分析完成後會更新風險、可能受影響部門與建議做法。'
                        )
                    )
                )

                :

                'AI 尚未啟用，目前顯示依規則產生的初步整理。'
            }


        </${isAI ? 'details' : 'div'}>


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
                        : `<button type="button" class="d-detail-retry" id="retryAI">${aiFailed ? '重試 AI 分析' : (isAI ? '重新分析' : '進行 AI 分析')}</button>`
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

                id="addToManagement"
            >

                加入管理摘要

            </button>


            <button

                class="btn"

                id="copyLink"
            >

                複製官方來源連結

            </button>


        </div>

        <p class="detail-actions-note">可在管理摘要頁選擇一筆或多筆資訊，再產生報告。</p>


    `;


    $('addToManagement').onclick =
        () =>
            addToManagementSummary(
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

    for(const id of ['retryAI', 'retryEvidenceReview']){
        const retryAIButton = $(id);
        if(!retryAIButton) continue;
        retryAIButton.onclick = () => {
            state.aiFailed.delete(event.id);
            state.aiRequested.delete(event.id);
            ensureAIAnalysis(event, true);
            renderDetail(false);
        };
    }


    bindLawComparison(event);

    if(triggerAI){

        ensureAIAnalysis(
            event
        );
    }
}
