"""US-09: What-if 시나리오 실행과 기준안 비교."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain import scenario as sc
from ..domain.enums import ContractType
from ..models import Business, Counterparty, Scenario
from ..services import scenario_service
from .deps import business

router = APIRouter(prefix="/api")


# 상한(60일·90%·100%·10%p)은 AC에 없는 값으로, 오타를 막으려고 정했다. AC-07이 요구하는 것은 0 거부다.
class SettlementDelay(BaseModel):
    counterparty_id: int
    days: int = Field(ge=1, le=60, description="지연 일수 1~60일")


class ScenarioIn(BaseModel):
    settlement_delay: SettlementDelay | None = None
    revenue_drop_pct: float | None = Field(default=None, gt=0, le=90, description="매출 감소율(%) 0 초과 90 이하")
    cost_rise_pct: float | None = Field(default=None, gt=0, le=100, description="원가 상승률(%) 0 초과 100 이하")
    rate_rise_pp: float | None = Field(default=None, gt=0, le=10, description="변동금리 상승폭(%p) 0 초과 10 이하")

    @model_validator(mode="after")
    def at_least_one(self):
        if not (self.settlement_delay or self.revenue_drop_pct or self.cost_rise_pct or self.rate_rise_pp):
            raise ValueError("조건을 하나 이상 고르세요")
        return self

    def conditions(self) -> sc.Conditions:
        d = self.settlement_delay
        return sc.Conditions(delay_counterparty_id=d.counterparty_id if d else None, delay_days=d.days if d else 0,
                             revenue_drop_pct=self.revenue_drop_pct or 0, cost_rise_pct=self.cost_rise_pct or 0, rate_rise_pp=self.rate_rise_pp or 0)


@router.post("/scenarios", status_code=201)
def create_scenario(body: ScenarioIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    if body.settlement_delay:  # 매입처를 고르면 아무 일정도 안 바뀐 채 "변화 없음"으로 보이므로 미리 막는다
        cp = s.get(Counterparty, body.settlement_delay.counterparty_id)
        if not cp or cp.business_id != b.business_id or not any(c.contract_type == ContractType.SALES for c in cp.contracts):
            raise HTTPException(422, detail="정산을 미룰 매출처를 고르세요")
    out = scenario_service.run(s, b, body.conditions())
    s.commit()
    return out


@router.get("/scenarios/{scenario_id}/comparison")
def scenario_comparison(scenario_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    scn = s.get(Scenario, scenario_id)
    if not scn or scn.business_id != b.business_id:
        raise HTTPException(404, detail="시나리오가 없습니다")
    out = scenario_service.compare(s, b, scenario_service.conditions_of(scn))
    out.pop("_forecast")
    return {"scenario_id": scenario_id, "kinds": scenario_service.conditions_of(scn).kinds(), **out}
