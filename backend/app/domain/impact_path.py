"""위험 영향 경로 (US-08). 시나리오 결과에서 문제 원인 → 잔액 부족일 → 막히는 지급 순서를 만드는 순수 함수다.

- 출발: 시나리오가 바꾼 일정 (정산 지연·매출 감소면 매출 입금, 원가 상승이면 매입 지급, 금리 상승이면 변동금리 상환)
- 부족일: 시나리오 잔액이 4주(28일) 안에서 처음 0원 아래로 내려가는 날. 없으면 빈 경로다 (AC-03).
- 부족 구간: 부족일부터 잔액이 다시 0원 이상이 되기 전날까지
- 영향받는 지급: 부족 구간 안의 출금. 지급일 순, 같은 날이면 금액 큰 순으로 번호를 붙인다 (AC-02).
- 원인: 부족 구간이 끝나기 전에 바뀐 일정. 같은 출처(계약·대출)는 한 단계로 묶는다.
근거 ID는 US-07 형식(P1, P2 ...)을 원인 → 지급 순서로 붙인다.
"""
from dataclasses import dataclass
from datetime import date

from .constants import ALERT_DAYS
from .scenario import Item

KIND_KO = {"SETTLEMENT_DELAY": "정산 지연", "REVENUE_DROP": "매출 감소", "COST_RISE": "원가 상승", "RATE_RISE": "금리 상승"}


@dataclass(frozen=True)
class Source:
    """예정 입출금 하나의 출처 (금융지도 노드와 맞출 키)."""
    source_type: str  # CONTRACT / FIXED_COST / LOAN
    source_id: int


def shortage_window(base_date: date, daily: list[tuple[date, int]]) -> tuple[date, date] | None:
    """4주 안 첫 부족일과, 그 부족이 이어지는 마지막 날."""
    start = next((i for i, (d, b) in enumerate(daily[:ALERT_DAYS]) if b < 0), None)
    if start is None:
        return None
    end = start
    while end + 1 < len(daily) and daily[end + 1][1] < 0:
        end += 1
    return daily[start][0], daily[end][0]


def build(base_date: date, before: list[Item], after: list[Item], base_daily: list[tuple[date, int]],
          scen_daily: list[tuple[date, int]], sources: dict[int, Source], kinds: list[str]) -> dict:
    """before/after는 같은 순서의 원본·시나리오 일정 (scenario.apply 결과)."""
    win = shortage_window(base_date, scen_daily)
    if win is None:
        return {"shortage": None, "steps": [], "message": "4주 안에 잔액이 부족해지지 않아 강조할 경로가 없어요."}
    first, last = win
    scen_bal, base_bal = dict(scen_daily), dict(base_daily)

    # 원인: 부족 구간이 끝나기 전에 원래 있었거나 옮겨 온 일정 중 바뀐 것
    groups: dict[Source, list[tuple[Item, Item]]] = {}
    for i, a in zip(before, after):
        if (i.due_date, i.amount) == (a.due_date, a.amount):
            continue
        if base_date <= i.due_date <= last or base_date <= a.due_date <= last:
            groups.setdefault(sources[i.event_id], []).append((i, a))
    causes = []
    for src, pairs in sorted(groups.items(), key=lambda kv: (kv[1][0][0].due_date, kv[0].source_id)):
        i0, a0 = pairs[0]
        # 부족 구간 끝날까지 이 출처 때문에 잔액이 달라진 금액 (음수 = 그만큼 덜 남음)
        effect = sum((a.amount if a.due_date <= last else 0) - (i.amount if i.due_date <= last else 0) for i, a in pairs)
        if effect == 0:
            continue
        causes.append(dict(role="CAUSE", source=src, label=i0.label, kind=i0.kind, party_id=i0.party_id,
                           date=i0.due_date, after_date=a0.due_date, amount=effect, events=[i.event_id for i, _ in pairs]))

    pays = [a for a in after if a.amount < 0 and first <= a.due_date <= last]
    pays.sort(key=lambda a: (a.due_date, a.amount, a.event_id))  # amount가 음수라 금액 큰 순
    steps: list[dict] = []
    n = 0
    for c in causes:
        n += 1
        steps.append({**c, "evidence_id": f"P{n}", "order": None})
    steps.append(dict(role="SHORTAGE", label="잔액 부족 시작", date=first, end_date=last, amount=-scen_bal[first],
                      evidence_id=None, order=None, source=None, events=[]))
    for k, a in enumerate(pays, 1):
        n += 1
        steps.append(dict(role="PAYMENT", order=k, evidence_id=f"P{n}", source=sources[a.event_id], label=a.label, kind=a.kind,
                          party_id=a.party_id, date=a.due_date, amount=-a.amount, balance=scen_bal[a.due_date],
                          new=base_bal[a.due_date] >= 0, events=[a.event_id]))
    title = " + ".join(KIND_KO.get(k, k) for k in kinds)
    low = min(b for d, b in scen_daily if first <= d <= last)
    return {"shortage": dict(first_date=first, last_date=last, amount=-scen_bal[first], min_balance=low),
            "steps": steps, "message": f"{title} 때문에 {first.month}/{first.day}부터 잔액이 부족해지고, 지급 {len(pays)}건이 막혀요."}
