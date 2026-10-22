"""Bounded product-role and draft guards, not a legal applicability engine."""

import re


DEPARTMENT_GUIDANCE = (
    "部門是一般職能的建議關注對象，不是已確認的公司權責。先從原文涉及作業找執行職能，再列必要的諮詢或檢查職能。"
    "退費、保全及懸帳作業優先考慮保單營運、客服與財務會計；系統權限涉及資訊科技，姓名檢核涉及洗錢防制。"
    "資金投資與增資優先考慮投資／資產負債管理及風險；通路訪問涉及通路管理與相關作業。"
    "法務處理法律諮詢，法令遵循評估監理適用性，內部稽核獨立查核；不可把它們當成退費付款、投資交易或客戶訪問的執行單位。"
    "只列有具體作業關聯的職能，不因提到裁罰就一律以法務為主責，也不要求每個事件列齊所有部門。"
)


def is_draft_event(event: dict, text: str = "") -> bool:
    title = event.get("title", "")
    return bool(re.search(r"草案|預告", title) or re.search(r"修正草案.{0,12}(?:預告|公告)|研擬.{0,100}修正草案", text))


def department_hints(text: str) -> list[dict]:
    """Source-bound candidates for the model; never published as an AI result."""
    signals = (
        ("核保／新契約／保單營運", r"退費|懸帳|保全|保單復效"),
        ("客戶服務／申訴", r"客戶服務|退款聯繫|款項退還|客戶申訴"),
        ("財務／會計", r"會計|付款憑證|款項沖轉|懸帳款項"),
        ("資訊科技", r"系統.{0,12}(?:功能|權限|控管)|帳號及密碼"),
        ("投資／資產負債管理", r"資金運用|創業投資|投資比例|參與增資"),
        ("業務通路／行銷", r"經紀人公司|銀行.{0,12}(?:要保|訪問)|招攬控管"),
    )
    hints = []
    for department, pattern in signals:
        match = re.search(pattern, text)
        if match:
            start = max(text.rfind("。", 0, match.start()), text.rfind("；", 0, match.start())) + 1
            end = text.find("。", match.end())
            quote = text[start:min(end + 1 if end >= 0 else len(text), match.end() + 90)]
            hints.append({"department": department, "source_excerpt": quote})
    return hints


def unfilled_template(text: str) -> bool:
    return bool(re.search(r"\.{3}|…|需填入(?:具體|可選)|TODO|TBD", text))


def interpretation_issue(statement: dict, sources: list[dict]) -> str:
    kind = statement.get("kind", "fact")
    text = statement["text"]
    process = statement.get("process", "")
    department = statement.get("department", "")
    if kind != "fact" and unfilled_template(text):
        return "內容仍是未填寫的格式範本，沒有具體的來源作業關聯。"
    if (kind in {"process", "department", "recommendation", "inference"}
            and any(source.get("is_law_comparison") for source in sources)
            and re.search(r"新增|新設|擴大", text) and re.search(r"義務|要求|機制|程序", text)):
        return "文字差異不能直接推成新增實質義務，部門與建議應描述可能涉及的作業。"
    if department == "業務通路／行銷" and re.search(r"退費|懸帳|款項退還", process or text):
        if not re.search(r"佣金|退佣|通路退費|招攬", process or text):
            return "原文未支持將退費或懸帳作業指定為行銷職能，須確認實際作業單位。"
    if kind == "process" and department in {"法務", "法令遵循", "內部稽核"}:
        operational = re.search(r"退費|付款|款項退還|投資|訪問|懸帳|保全|沖轉", process)
        advisory = re.search(r"法律|法令|法規|適用性|稽核|查核|合規|遵循", process)
        if operational and not advisory:
            return "作業執行流程與諮詢或查核職能混淆，尚無依據指定為承辦部門。"
    if kind in {"recommendation", "process", "department", "inference"} and sources and all(source.get("is_draft") for source in sources):
        for requirement in re.finditer(r"(?:應|必須|須|需).{0,10}(?:調整|修改|制定|建立|執行|增資|符合|遵循|遵守)", text):
            if not re.search(r"是否|評估|確認|檢查", text[max(0, requirement.start() - 5):requirement.start()]):
                return "草案只支持盤點、評估與追蹤等準備方向，不能把許可或草案改寫成必須執行的措施。"
        conditional = re.search(r"若|如公司|草案準備|預告階段|可先|待正式|追蹤|建議", text)
        mandatory = re.search(r"應|必須|須|需", text)
        immediate_compliance = re.search(r"確保符合(?:修正後|新)|遵守新規|已生效|現行法定", text)
        future = re.search(r"待正式|正式發布後|若.{0,20}(?:生效|通過|公布)", text)
        if (mandatory and not conditional) or (immediate_compliance and not future):
            return "草案的準備建議缺少適用條件，不能指定為已生效的執行或遵循義務。"
    return ""
