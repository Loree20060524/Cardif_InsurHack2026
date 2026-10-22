/* =====================================================
   AI Analysis
===================================================== */

function notifyAIAnalysisState(
    event,
    status
){

    if(
        typeof document
        ===
        'undefined'
        ||
        typeof CustomEvent
        ===
        'undefined'
    ){

        return;
    }


    document.dispatchEvent(

        new CustomEvent(

            'regintel:ai-analysis-state',

            {

                detail:{

                    eventId:event?.id,

                    status,
                },
            }
        )
    );
}

async function ensureAIAnalysis(
    event,
    force = false
){

    if(
        !event?.id
        ||
        !state.ai.enabled
    ){

        return;
    }


    if(
        !force
        &&
        event.analysis
        ?.analysis_mode
        ===
        'AI 深度分析'
        && event.analysis?.support_review?.version
    ){

        return;
    }


    /* A known unreadable source cannot benefit from another automatic request. */
    if(
        !force && event.source_key !== 'fsc_announcement' && /未提供可解析的/.test(
            event.analysis?.analysis_note || ''
        )
    ){

        return;
    }


    if(
        !force && state.aiFailed.has(event.id)
    ){

        return;
    }


    if(
        state.aiLoading.has(
            event.id
        )
        ||
        (!force && state.aiRequested.has(
            event.id
        ))
    ){

        return;
    }


    state.aiRequested.add(
        event.id
    );

    state.aiFailed.delete(event.id);


    state.aiLoading.add(
        event.id
    );


    notifyAIAnalysisState(
        event,
        'loading'
    );


    let analysisStatus =
        'failed';


    if(
        event.id
        ===
        state.selected
    ){

        const element =
            $('aiAnalysisStatus');


        if(element){

            element.textContent =
                'AI 分析中…';


            element.className =
                'workflow ai-loading';
        }
    }


    try{

        const response =
            await fetch(

                `/api/analyze?id=${
                    encodeURIComponent(
                        event.id
                    )
                }${force ? '&force=1' : ''}`,

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

        const keepPreviousAnalysis = force
            && event.analysis?.analysis_mode === 'AI 深度分析'
            && (data.analysis?.analysis_mode !== 'AI 深度分析'
                || (event.analysis?.support_review?.unverified === 0 && data.analysis?.support_review?.unverified > 0));


        if(
            data.analysis
            &&
            typeof data.analysis
            ===
            'object'
            && !keepPreviousAnalysis
        ){

            event.analysis =
                data.analysis;
            if(data.analysis.source_title) event.title = data.analysis.source_title;
            if(data.analysis.source_url) event.url = data.analysis.source_url;
            if(data.analysis.source_description) event.description = data.analysis.source_description;
        }


        if(
            !data.ai_used
            &&
            data.message
        ){

            console.error(

                'AI 分析診斷：',

                data.message
            );
        }


        if(
            !keepPreviousAnalysis && event.analysis
            ?.analysis_mode
            ===
            'AI 深度分析'
            && !(event.analysis?.support_review?.unverified > 0)
        ){

            analysisStatus =
                'complete';

            state.aiFailed.delete(event.id);
        }

        else{
            /* Wait for an explicit retry or refresh before requesting again. */
            state.aiRequested.delete(event.id);
            state.aiFailed.add(event.id);
        }


        renderManagement();

    }

    catch(error){

        state.aiRequested.delete(event.id);
        state.aiFailed.add(event.id);

        console.error(
            error
        );


        toast(
            'AI 分析暫時無法完成。'
        );
    }

    finally{

        state.aiLoading.delete(
            event.id
        );


        notifyAIAnalysisState(
            event,
            analysisStatus
        );

        renderAdvancedFilters();
        renderList();

        if(event.id === state.selected){
            renderDetail(false);
        }
    }
}
