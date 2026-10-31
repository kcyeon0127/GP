"""요청·응답 DTO (Pydantic). 입력 검증은 여기서, 업무 판단은 서비스에서 한다."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .domain.enums import PayCycle, RateType

Money = Field(gt=0, description="원 단위, 0보다 커야 한다")
PayDay = Field(ge=1, le=31, description="월 결제일(1~31). 주간이면 요일(1=월 … 7=일)")


class CounterpartyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    trade_type: Literal["SALES", "PURCHASE"]
    pay_cycle: PayCycle
    pay_day: int = PayDay
    amount: int = Money
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def weekly_day(self):
        if self.pay_cycle == PayCycle.WEEKLY and self.pay_day > 7:
            raise ValueError("주간 결제는 요일 번호(1~7)를 입력하세요")
        return self


class CounterpartyOut(CounterpartyIn):
    counterparty_id: int
    contract_id: int
    next_due_dates: list[date]


class FixedCostIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    pay_cycle: Literal["MONTHLY", "QUARTERLY"]
    pay_day: int = PayDay
    months: str | None = Field(default=None, description="분기 고정비 지급 월, 예: 3,6,9,12")
    amount: int = Money
    payee: str | None = Field(default=None, description="임대인 등 지급 상대. 있으면 임대(LEASE) 계약으로 금융지도에 연결")


class FixedCostOut(FixedCostIn):
    fixed_cost_id: int
    next_due_dates: list[date]


class LoanIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    lender: str = Field(min_length=1, max_length=100)
    principal: int = Field(ge=0)
    interest_rate: float = Field(ge=0, le=30)
    rate_type: RateType = RateType.FIXED
    installment: int = Money
    repay_day: int = Field(ge=1, le=31)
    maturity_date: date | None = None


class LoanOut(LoanIn):
    loan_id: int
    next_due_dates: list[date]


class ForecastIn(BaseModel):
    base_date: date | None = None
    current_balance: int | None = None
    safety_balance: int | None = Field(default=None, ge=0)


class DailyBalance(BaseModel):
    date: date
    balance: int


class ForecastOut(BaseModel):
    run_id: int
    base_date: date
    start_balance: int
    safety_balance: int
    signal: str
    first_shortage_date: date | None
    shortage_amount: int | None
    max_shortage_amount: int | None
    min_balance: int
    min_balance_date: date
    first_below_safe_date: date | None
    has_events: bool
    message: str
    daily: list[DailyBalance] | None = None
