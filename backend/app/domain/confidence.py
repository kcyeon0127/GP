"""경보 신뢰도 규칙 (US-18). 요인별 점수를 더해 등급을 정하는 순수 함수다.

점수는 0~100이고, 요인마다 배점(constants의 CONF_W_*) 안에서 비율만큼 받는다.
CONF_HIGH 이상 높음, CONF_MEDIUM 이상 보통, 미만 낮음. 낮음이면 대응안·AI 설명을 보류한다.
"""
from dataclasses import dataclass, field

from .constants import CONF_HIGH, CONF_MEDIUM


@dataclass(frozen=True)
class Factor:
    key: str
    ratio: float  # 0~1
    weight: int
    reason: str  # 사장님이 읽는 짧은 이유
    missing: list[str] = field(default_factory=list)  # 등록하면 점수가 오르는 것


def ratio(have: int, total: int) -> float:
    return have / total if total else 0.0


def assess(factors: list[Factor], cap_medium: bool = False) -> dict:
    """cap_medium: 서버 문제로 일부 근거를 확인하지 못했을 때 높음을 보통으로 낮춘다 (확인 못 한 것을 높다고 하지 않는다)."""
    total = sum(f.weight for f in factors)
    score = round(sum(f.ratio * f.weight for f in factors) * 100 / total) if total else 0
    level = "HIGH" if score >= CONF_HIGH else "MEDIUM" if score >= CONF_MEDIUM else "LOW"
    if cap_medium and level == "HIGH":
        level = "MEDIUM"
    return {"level": level, "score": score, "reasons": [f.reason for f in factors],
            "missing": list(dict.fromkeys(m for f in factors for m in f.missing)),
            "factors": [{"key": f.key, "points": round(f.ratio * f.weight, 1), "weight": f.weight} for f in factors]}
