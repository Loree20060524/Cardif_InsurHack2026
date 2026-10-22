/* =====================================================
   監理影響圖
===================================================== */

function renderImpactChain(
    analysis
){

    const points =
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


    const pointItems =

        points.length

        ?

        points
        .slice(
            0,
            4
        )
        .map(

            item =>
                `<li>${esc(item)}</li>`
        )
        .join('')

        :

        `
        <li>
            待確認具體監理要求。
        </li>
        `;


    const departmentItems =

        departments.length

        ?

        departments
        .slice(
            0,
            4
        )
        .map(

            item => `

            <li>

                ${esc(
                    departmentLabel(
                        item.department
                    )
                )}

            </li>
            `
        )
        .join('')

        :

        `
        <li>
            待確認受影響部門。
        </li>
        `;


    const processItems =

        processes.length

        ?

        processes
        .slice(
            0,
            4
        )
        .map(

            item => `

            <li>
                ${esc(item.process)}
            </li>
            `
        )
        .join('')

        :

        `
        <li>
            待確認受影響流程。
        </li>
        `;


    return `

        <div class="impact-chain">


            <div class="chain-card">

                <div class="step">
                    01
                </div>

                <h4>
                    監理要求
                </h4>

                <ul>
                    ${pointItems}
                </ul>

            </div>


            <div class="chain-arrow">
                →
            </div>


            <div class="chain-card">

                <div class="step">
                    02
                </div>

                <h4>
                    受影響部門
                </h4>

                <ul>
                    ${departmentItems}
                </ul>

            </div>


            <div class="chain-arrow">
                →
            </div>


            <div class="chain-card">

                <div class="step">
                    03
                </div>

                <h4>
                    可能受影響流程
                </h4>

                <ul>
                    ${processItems}
                </ul>

            </div>


        </div>
    `;
}


/* =====================================================
   Process Cards
===================================================== */

function renderProcesses(
    processes
){

    if(
        !processes?.length
    ){

        return `

            <div class="empty">

                尚待確認可能受影響的流程。

            </div>
        `;
    }


    return `

        <div class="process-list">

            ${
                processes
                .map(

                    item => `

                    <div class="process-item">

                        <b>
                            ${esc(item.process)}
                        </b>

                        <small>

                            可能涉及：

                            ${
                                esc(
                                    departmentLabel(
                                        item.department
                                    )
                                )
                            }

                        </small>

                        <p>
                            ${esc(item.impact)}
                        </p>

                    </div>

                    `
                )
                .join('')
            }

        </div>
    `;
}
