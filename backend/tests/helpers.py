"""API 테스트 공용 데이터."""


def register_sample(c) -> None:
    """정산 지연 사례: 11/5 +120만, 11/10 임대료 -150만, 11/25 원리금 -280만, 11/28 정산 +300만."""
    c.post("/api/counterparties", json={"name": "청춘마켓", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 5, "amount": 1_200_000}).raise_for_status()
    c.post("/api/fixed-costs", json={"name": "임대료", "pay_cycle": "MONTHLY", "pay_day": 10, "amount": 1_500_000, "payee": "건물주"}).raise_for_status()
    c.post("/api/loans", json={"name": "운영자금대출", "lender": "○○은행", "principal": 60_000_000, "interest_rate": 5.1,
                               "rate_type": "VARIABLE", "installment": 2_800_000, "repay_day": 25}).raise_for_status()
    c.post("/api/counterparties", json={"name": "한빛식자재", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 28, "amount": 3_000_000}).raise_for_status()
