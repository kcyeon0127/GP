"""양식 6 §3.1 Enum 정의. PostgreSQL ENUM 타입과 같은 값이다."""
from enum import Enum


class CounterpartyRole(str, Enum):
    SUPPLIER = "SUPPLIER"  # 매입처
    CUSTOMER = "CUSTOMER"  # 매출처
    LENDER = "LENDER"  # 금융기관


class ContractType(str, Enum):
    PURCHASE = "PURCHASE"
    SALES = "SALES"
    LEASE = "LEASE"
    LOAN = "LOAN"


class PayCycle(str, Enum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"


class CashDirection(str, Enum):
    IN = "IN"
    OUT = "OUT"


class CashSource(str, Enum):
    CONTRACT = "CONTRACT"
    FIXED_COST = "FIXED_COST"
    LOAN = "LOAN"


class RateType(str, Enum):
    FIXED = "FIXED"
    VARIABLE = "VARIABLE"


class SignalLevel(str, Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"


class EvidenceRef(str, Enum):
    GRAPH_PATH = "GRAPH_PATH"
    CASH_EVENT = "CASH_EVENT"
    DOCUMENT_CHUNK = "DOCUMENT_CHUNK"


class PlanStatus(str, Enum):
    PROPOSED = "PROPOSED"  # 제시만 됨. 일정에 반영되지 않는다 (US-10 AC-03)
    APPROVED = "APPROVED"  # 대표가 승인해 예정 입출금에 반영됨
    DECLINED = "DECLINED"  # 같은 요청의 다른 후보를 승인함
    EXPIRED = "EXPIRED"  # 대응안을 다시 요청해 이전 후보가 밀려남
    CANCELLED = "CANCELLED"  # 승인을 되돌림
