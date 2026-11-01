"""US-05: 조기경보 신호와 영향 일정 (T17)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Business
from ..schemas import ForecastOut
from ..services import forecast_service
from .deps import business
from .forecasts import _out, _run

router = APIRouter(prefix="/api")


@router.get("/alerts/current", response_model=ForecastOut)
def current_alert(s: Session = Depends(get_session), b: Business = Depends(business)):
    r = forecast_service.latest(s, b.business_id)
    if r is None:
        r = forecast_service.run(s, b)
        s.commit()
    return _out(s, r, with_daily=False)


@router.get("/alerts/{run_id}/drivers")
def alert_drivers(run_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    r = _run(s, run_id, b)
    t = forecast_service.trigger_date(r)
    return {"run_id": run_id, "signal": r.signal.value, "trigger_date": t,
            "drivers": [dict(cash_event_id=e.cash_event_id, date=e.due_date, label=e.label, direction=e.direction.value, amount=e.amount, role=role)
                        for e, role in forecast_service.drivers(s, r)]}
