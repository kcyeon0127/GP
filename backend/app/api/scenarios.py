"""US-09: What-if 시나리오 실행과 기준안 비교. US-08: 시나리오의 위험 영향 경로."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
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

    def conditions(self) -> sc.Conditions:
        d = self.settlement_delay
        return sc.Conditions(delay_counterparty_id=d.counterparty_id if d else None, delay_days=d.days if d else 0,
                             revenue_drop_pct=self.revenue_drop_pct or 0, cost_rise_pct=self.cost_rise_pct or 0, rate_rise_pp=self.rate_rise_pp or 0)


@router.post("/scenarios", status_code=201)
def create_scenario(body: ScenarioIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    # 값 범위와 달리 빠진 칸이 없는 오류라 공통 검증 처리기로 보내면 "필수 항목을 확인하세요"로 뭉개진다
    if not (body.settlement_delay or body.revenue_drop_pct or body.cost_rise_pct or body.rate_rise_pp):
        raise HTTPException(422, detail="조건을 하나 이상 고르세요")
    if body.settlement_delay:  # 매입처를 고르면 아무 일정도 안 바뀐 채 "변화 없음"으로 보이므로 미리 막는다
        cp = s.get(Counterparty, body.settlement_delay.counterparty_id)
        if not cp or cp.business_id != b.business_id or not any(c.contract_type == ContractType.SALES for c in cp.contracts):
            raise HTTPException(422, detail="정산을 미룰 매출처를 고르세요")
    out = scenario_service.run(s, b, body.conditions())
    s.commit()
    return out


@router.get("/scenarios")
def list_scenarios(s: Session = Depends(get_session), b: Business = Depends(business)):
    """US-08 AC-06: 저장된 시나리오를 골라 경로를 바꿔 보려고 최근 20개를 돌려준다."""
    return scenario_service.list_scenarios(s, b)


def _scenario(s: Session, scenario_id: int, b: Business) -> Scenario:
    scn = s.get(Scenario, scenario_id)
    if not scn or scn.business_id != b.business_id:
        raise HTTPException(404, detail="시나리오가 없습니다")
    return scn


@router.get("/scenarios/{scenario_id}/impact-path")
def scenario_impact_path(scenario_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    """US-08: 문제 원인 → 잔액 부족일 → 먼저 막히는 지급 순서. 4주 안 부족이 없으면 steps가 빈 목록이다."""
    out = scenario_service.impact_path(s, b, _scenario(s, scenario_id, b))
    s.commit()  # 그래프가 오래돼 다시 맞췄을 수 있다
    return out


@router.get("/scenarios/{scenario_id}/comparison")
def scenario_comparison(scenario_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    scn = _scenario(s, scenario_id, b)
    out = scenario_service.compare(s, b, scenario_service.conditions_of(scn))
    out.pop("_forecast")
    return {"scenario_id": scenario_id, "kinds": scenario_service.conditions_of(scn).kinds(), **out}
