"""Self-authored company knowledge for the competition's Theme 4 demo."""

from __future__ import annotations

import re
from collections import Counter

from .knowledge_search import search_tokens
from .text import clean_text


DEMO_NOTE = "以下為自建示範企業文件，非真實公司制度或官方法規；實際作業請以公司正式文件為準。"
VERSION = "1.0"
UPDATED = "2026-10-20"
CATEGORIES = ("SOP", "表單", "新人訓練", "專業術語", "IT 支援")


def document(key, number, title, category, keywords, sections):
    return {"id": key, "number": number, "title": title, "category": category, "keywords": keywords,
            "version": VERSION, "updated": UPDATED,
            "sections": [{"id": f"section-{index}", "title": heading, "text": text}
                         for index, (heading, text) in enumerate(sections, 1)]}


DOCUMENTS = (
    document("data-sharing", "DEMO-SOP-001", "客戶資料提供與委外作業指引", "SOP", ("客戶資料", "名單", "個資", "個人資料", "委外", "外包", "廠商"), [
        ("先釐清資料用途與接收對象", "承辦人先釐清使用目的、接收對象及對方執行的工作，整理預計提供的資料欄位名稱，由資料權責人員確認必要性。描述作業即可，不在問答中貼上實際客戶名單或個資。"),
        ("整理處理安排與確認窗口", "資料提供前，整理處理地點、傳輸管道、存取權限、保存及刪除安排，交資料權責人員與資訊安全人員確認；使用依據、授權與契約交法令遵循確認。境外或條件不明時應保留待確認事項。"),
        ("使用哪份表單", "可使用《資料提供需求確認單》整理用途、必要欄位、接收對象、處理地點、傳輸權限及待確認文件，帶給資料權責人員、法令遵循與資訊安全人員討論。表單與本指引是示範，不構成核准。"),
    ]),
    document("data-request-form", "DEMO-FORM-001", "資料提供需求確認單", "表單", ("客戶資料", "名單", "委外", "外包", "廠商", "資料提供", "確認單"), [
        ("用途與填寫方式", "本表供資料提供或委外需求討論，填寫工作目的、必要資料欄位、接收對象、處理地點、傳輸及存取安排、保存刪除安排與待確認文件。僅使用欄位名稱，不附客戶實際個資。"),
        ("空白表單", "工作目的：＿＿＿＿\n資料欄位及必要性：＿＿＿＿\n接收對象及執行工作：＿＿＿＿\n處理地點：＿＿＿＿\n傳輸及存取安排：＿＿＿＿\n保存與刪除安排：＿＿＿＿\n待確認文件與問題：＿＿＿＿\n擬洽詢窗口：＿＿＿＿\n此表僅供示範討論，非正式核准文件。"),
    ]),
    document("claims-intake", "DEMO-SOP-002", "理賠文件受理與補件指引", "SOP", ("理賠", "補件", "受理", "保險金", "診斷", "醫療"), [
        ("確認受理問題", "接到理賠文件或補件詢問時，先確認申請項目、適用保單條款及已備文件的種類，向理賠權責人員核對公司正式文件清單。不可直接以示範清單取代實際保單要求。"),
        ("記錄與確認下一步", "使用《理賠文件詢問紀錄》記下已備與待確認的文件種類、需洽詢的理賠窗口及回覆事項，由權責人員確認後再說明受理或補件方向。問答及示範表單不填入診斷內容或實際個資。"),
    ]),
    document("claims-form", "DEMO-FORM-002", "理賠文件詢問紀錄", "表單", ("理賠", "補件", "文件", "受理", "保險金"), [
        ("用途", "理賠文件詢問紀錄供承辦人整理申請項目、文件種類、未明事項及應洽詢的權責窗口，不用來判定是否理賠或決定應備文件。"),
        ("空白表單", "詢問項目：＿＿＿＿\n待查保單條款或文件清單：＿＿＿＿\n已備文件種類：＿＿＿＿\n待確認文件種類：＿＿＿＿\n待洽詢窗口與問題：＿＿＿＿\n確認後的回覆事項：＿＿＿＿\n請勿記入實際客戶個資或醫療內容。"),
    ]),
    document("sales-review", "DEMO-SOP-003", "招攬素材與商品文宣覆核指引", "SOP", ("招攬", "文宣", "素材", "廣告", "話術", "商品說明", "保證獲利"), [
        ("整理欲使用的素材", "送審前整理商品名稱、溝通對象、使用通路、素材版本及欲表達的內容，對照實際商品條款與風險說明，將未能確認的宣稱列為待查事項。"),
        ("尋找覆核文件與窗口", "使用《招攬素材覆核需求單》附上素材版本與待確認宣稱，交業務、商品及法令遵循等實際權責人員覆核，依公司正式核准流程使用並保存版本紀錄。"),
    ]),
    document("sales-form", "DEMO-FORM-003", "招攬素材覆核需求單", "表單", ("招攬", "文宣", "素材", "廣告", "話術", "送審"), [
        ("空白表單", "商品名稱：＿＿＿＿\n使用通路與溝通對象：＿＿＿＿\n素材版本與用途：＿＿＿＿\n欲表達的商品內容：＿＿＿＿\n待核對條款或宣稱：＿＿＿＿\n擬洽詢覆核窗口：＿＿＿＿\n確認結果與版本紀錄：＿＿＿＿\n本表為自建示範，實際送審依公司正式流程辦理。"),
    ]),
    document("account-faq", "DEMO-IT-001", "帳號、忘記密碼與登入 FAQ", "IT 支援", ("密碼", "忘記", "登入", "登不進", "帳號", "鎖定", "驗證碼", "mfa"), [
        ("忘記密碼或帳號鎖定", "忘記密碼時，從公司指定的正式登入頁使用忘記密碼或帳號解鎖功能；若公司未提供自助功能，透過正式 IT 支援管道確認處理方式。不要把密碼、驗證碼或復原碼提供給聊天助手或同事。"),
        ("無法登入怎麼查", "無法登入時，先確認系統名稱、錯誤訊息、帳號輸入方式及是否使用公司指定的登入入口；若需要 VPN，先檢查連線。帳號鎖定或驗證問題持續時，停止反覆嘗試，整理不含機密的錯誤資訊交 IT 確認。"),
    ]),
    document("vpn-faq", "DEMO-IT-002", "VPN 連線與遠端存取 FAQ", "IT 支援", ("vpn", "遠端", "連線", "在家", "內網"), [
        ("VPN 連不上時先做什麼", "VPN 無法連線時，先確認一般網路可用，再確認使用公司核准的 VPN 客戶端與指定入口；查看是否有連線、驗證或服務異常訊息。若不清楚入口、版本或權限，向 IT 確認，不自行停用安全防護或安裝來源不明工具。"),
        ("需要提供 IT 哪些資訊", "VPN 問題持續時，記錄發生時間、使用的裝置與作業系統、VPN 客戶端版本、錯誤訊息及是否能使用一般網路，透過正式 IT 管道回報。使用《IT 問題回報紀錄》整理資訊，遮蔽帳號個資，不提供密碼或驗證碼。"),
    ]),
    document("network-faq", "DEMO-IT-003", "網路連線與內部系統存取 FAQ", "IT 支援", ("網路", "斷線", "wifi", "wi-fi", "無法上網", "網站", "內部系統"), [
        ("區分網路與系統問題", "無法上網或開啟內部系統時，先確認網路是否已連接，再區分所有網站都無法使用、僅內部網站無法使用，或只有單一系統異常。內部網站可能需要公司指定網路或 VPN；依正式 IT 說明確認連線條件。"),
        ("如何回報", "記錄受影響的網站或系統、錯誤訊息、發生時間及影響範圍，使用《IT 問題回報紀錄》向正式 IT 支援管道回報。不要為排除問題自行修改公司安全設定。"),
    ]),
    document("it-ticket", "DEMO-FORM-004", "IT 問題回報紀錄", "表單", ("it", "回報", "報修", "登入", "vpn", "網路", "錯誤"), [
        ("空白表單", "受影響的系統或服務：＿＿＿＿\n問題開始時間：＿＿＿＿\n錯誤訊息（遮蔽個資）：＿＿＿＿\n裝置、作業系統與程式版本：＿＿＿＿\n目前網路或 VPN 狀態：＿＿＿＿\n已確認的項目與影響範圍：＿＿＿＿\n請勿填入密碼、驗證碼、復原碼或機密資料。此表為示範紀錄，非真實報修送件。"),
    ]),
    document("new-starter", "DEMO-TRAIN-001", "新人文件查找與提問指南", "新人訓練", ("新人", "新進", "到職", "入職", "訓練", "員工手冊"), [
        ("從工作任務找文件", "新人可用自己的工作描述搜尋相關 SOP、表單及術語，例如資料提供、理賠受理或文宣覆核。先閱讀文件適用範圍、版本與權責窗口，再依公司正式文件確認作業。"),
        ("如何提出清楚的問題", "詢問作業時，說明想完成的任務、已確認條件及卡住的地方；詢問 IT 問題時，補充系統名稱、錯誤訊息與發生時間。若找不到依據，向實際權責窗口確認，不把示範資料當成公司正式規定。"),
    ]),
    document("glossary", "DEMO-TERM-001", "保險公司常見職能與作業術語", "專業術語", ("術語", "名詞", "sop", "法遵", "內控", "核保", "理賠", "委外", "意思"), [
        ("SOP、法遵與內控", "SOP 是作業標準程序，整理特定任務的步驟、文件與權責。法遵通常指法令遵循職能，協助確認規範與適用問題；內控指內部控制，關注作業的控制設計與執行。實際分工依公司組織與正式制度確認。"),
        ("核保、理賠與委外", "核保通常指承保條件與風險的評估作業；理賠指依保單與相關依據受理、審查給付申請的作業。委外指將特定工作交由外部對象處理，具體範圍、權責與要求須查正式文件。此為學習用的概括說明。"),
    ]),
)


def get_document(key: str) -> dict:
    found = next((item for item in DOCUMENTS if item["id"] == key), None)
    if found is None:
        raise ValueError("找不到這份示範文件。")
    return found


def metadata(item: dict) -> dict:
    return {key: item[key] for key in ("id", "number", "title", "category", "version", "updated")} | {
        "url": f"/api/enterprise-knowledge/document?id={item['id']}",
        "download_url": f"/api/enterprise-knowledge/document?id={item['id']}&download=1",
    }


def search_documents(question: str, category: str = "全部") -> list[dict]:
    """Rank actual document sections, with task vocabulary supporting everyday wording."""
    query = question.lower()
    terms = set(search_tokens(query, query=True))
    generic = {"文件", "表單", "流程", "如何", "處理", "公司", "什麼", "需要", "怎麼", "問題", "可以", "相關"}
    specific = terms - generic
    rows = []
    wants_form = bool(re.search("表單|確認單|需求單|紀錄|報修", query))
    for item in DOCUMENTS:
        if category != "全部" and item["category"] != category:
            continue
        matched = [word for word in item["keywords"] if word in query and word not in generic]
        # Generic SOP/term words alone should not outrank a concrete work or IT issue.
        strong = [word for word in matched if word not in {"sop", "意思", "連線", "文件", "登入", "回報"}]
        for section in item["sections"]:
            text_terms = set(search_tokens(item["title"] + " " + section["title"] + " " + section["text"]))
            overlap = specific & text_terms
            if not matched and len(overlap) < 2:
                continue
            score = len(overlap) + 9 * len(strong) + 3 * len(matched)
            if item["category"] == "表單" and wants_form:
                score += 14
            if item["title"].lower() in query:
                score += 40
            rows.append((score, item, section))
    rows.sort(key=lambda row: row[0], reverse=True)
    minimum_score = max(4, rows[0][0] * 0.2) if rows else 4
    selected, per_document = [], Counter()
    for score, item, section in rows:
        # Weak incidental word overlap should not add an unrelated FAQ to the answer.
        if score < minimum_score:
            continue
        if per_document[item["id"]] >= 2:
            continue
        per_document[item["id"]] += 1
        selected.append({**metadata(item), "source_id": f"K{len(selected) + 1}", "section": section["title"],
                         "section_id": section["id"], "text": clean_text(section["text"]), "score": score,
                         "url": metadata(item)["url"] + "#" + section["id"]})
        if len(selected) == 4:
            break
    return selected
