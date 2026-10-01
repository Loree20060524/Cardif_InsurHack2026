from __future__ import annotations

import unittest

from regintel.domain.classification import detect_departments
from regintel.domain.rules import AI_ALLOWED_DEPARTMENTS


class DepartmentTaxonomyTests(unittest.TestCase):

    def test_competition_taxonomy_has_fourteen_responsibility_functions(
        self,
    ) -> None:
        self.assertEqual(len(AI_ALLOWED_DEPARTMENTS), 14)
        self.assertEqual(
            AI_ALLOWED_DEPARTMENTS,
            [
                "法令遵循",
                "法務",
                "風險管理",
                "內部稽核",
                "業務通路／行銷",
                "商品／精算",
                "核保／新契約／保單營運",
                "理賠",
                "客戶服務／申訴",
                "資訊科技",
                "資訊安全／個資治理",
                "財務／會計",
                "投資／資產負債管理",
                "人力資源",
            ],
        )

    def test_combined_functions_are_not_returned_twice(self) -> None:
        departments = detect_departments(
            "保險商品費率與責任準備金調整，並更新廣告文宣及銷售話術。",
            "商品與銷售規範修正",
        )
        names = [
            item["department"]
            for item in departments
        ]

        self.assertEqual(
            names.count("商品／精算"),
            1,
        )
        self.assertEqual(
            names.count("業務通路／行銷"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
