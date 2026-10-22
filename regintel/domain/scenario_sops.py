"""Self-authored example procedures, kept separate from official evidence."""

from __future__ import annotations

import re


DEMO_SOPS = (
    {
        "id": "demo-data-sharing", "title": "客戶資料提供與委外確認流程",
        "topics": ("個資", "個人資料", "客戶資料", "名單", "廠商", "委外", "外包"),
        "owner": "示範窗口：業務承辦、法遵與資訊安全人員",
        "form": "示範表單：資料提供需求確認單",
        "steps": [
            "記錄使用目的、資料欄位、接收對象及是否涉及境外處理。",
            "整理相關法規依據與待確認事項，交由法遵及資料權責人員確認。",
            "在需求單記錄必要欄位、傳輸方式、存取權限及保存／刪除安排，依公司實際核准流程辦理。",
        ],
    },
    {
        "id": "demo-claims", "title": "理賠文件受理與補件確認流程",
        "topics": ("理賠", "補件", "診斷", "醫療", "保險金", "受益人"),
        "owner": "示範窗口：理賠承辦與文件覆核人員",
        "form": "示範表單：理賠文件檢核紀錄",
        "steps": [
            "先確認申請項目、申請人身分及已備文件，避免在問答中輸入客戶個資。",
            "核對實際保單條款、官方規範與公司文件清單；缺少依據時記錄待確認項目。",
            "由理賠權責人員確認應備文件及補件內容，再向申請人說明後續程序。",
        ],
    },
    {
        "id": "demo-sales", "title": "商品說明與招攬素材覆核流程",
        "topics": ("招攬", "銷售", "話術", "文宣", "廣告", "商品說明", "保證獲利", "保證收益"),
        "owner": "示範窗口：業務、商品與法遵覆核人員",
        "form": "示範表單：招攬素材覆核紀錄",
        "steps": [
            "整理預計使用的素材、溝通對象、通路及欲表達的商品內容。",
            "逐項比對實際商品條款、風險說明與檢索到的官方規範，標記待查證的宣稱。",
            "送交公司實際權責人員覆核並保存版本紀錄，再依核准流程使用。",
        ],
    },
)


def matching_demo_sops(user_text: str) -> list[dict]:
    """Match only user-provided facts; model-expanded searches are not evidence of a task."""
    def positive_match(term: str) -> bool:
        # A mentioned activity may explicitly be outside this scenario.
        text = re.sub(r"(?:不進行|不涉及|不處理|不做|沒有|不|無)[^，。；、\n]{0,8}" + re.escape(term), "", user_text)
        return term in text

    ranked = sorted(DEMO_SOPS, key=lambda sop: sum(positive_match(term) for term in sop["topics"]), reverse=True)
    return [
        {key: value for key, value in sop.items() if key != "topics"}
        for sop in ranked if any(positive_match(term) for term in sop["topics"])
    ][:2]
