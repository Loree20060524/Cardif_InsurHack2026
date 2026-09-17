/* =====================================================
   AI Analysis
===================================================== */

async function ensureAIAnalysis(
    event
){

    if(
        !event?.id
        ||
        !state.ai.enabled
    ){

        return;
    }


    if(
        event.analysis
        ?.analysis_mode
        ===
        'AI 深度分析'
    ){

        return;
    }


    if(
        state.aiLoading.has(
            event.id
        )
        ||
        state.aiRequested.has(
            event.id
        )
    ){

        return;
    }


    state.aiRequested.add(
        event.id
    );


    state.aiLoading.add(
        event.id
    );


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
                }`,

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


        if(
            data.analysis
            &&
            typeof data.analysis
            ===
            'object'
        ){

            event.analysis =
                data.analysis;
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
            event.id
            ===
            state.selected
        ){

            renderDetail(
                false
            );
        }


        renderManagement();

    }

    catch(error){

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
    }
}
