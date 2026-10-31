"""PostgreSQL 테이블 (양식 6 §3.1 ERD). 원본 데이터는 모두 여기 있고 Neo4j는 파생 저장소다."""
from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, CheckConstraint, Date, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import EMBEDDING_DIM
from .db import Base
from .domain.enums import CashDirection, CashSource, ContractType, CounterpartyRole, EvidenceRef, PayCycle, RateType, SignalLevel


def pg_enum(e, name):
    return Enum(e, name=name, values_callable=lambda x: [m.value for m in x])


class Business(Base):
    __tablename__ = "business"
    business_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    current_balance: Mapped[int] = mapped_column(BigInteger)
    safety_balance: Mapped[int] = mapped_column(BigInteger)
    base_date: Mapped[date] = mapped_column(Date)


class Counterparty(Base):
    __tablename__ = "counterparty"
    __table_args__ = (UniqueConstraint("business_id", "name", name="uq_counterparty_business_name"),)
    counterparty_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.business_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[CounterpartyRole] = mapped_column(pg_enum(CounterpartyRole, "counterparty_role"))
    contracts: Mapped[list["Contract"]] = relationship(back_populates="counterparty", cascade="all, delete-orphan", passive_deletes=True)


class Contract(Base):
    __tablename__ = "contract"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_contract_amount"), CheckConstraint("pay_day BETWEEN 1 AND 31", name="ck_contract_pay_day"))
    contract_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.business_id", ondelete="CASCADE"))
    counterparty_id: Mapped[int] = mapped_column(ForeignKey("counterparty.counterparty_id", ondelete="CASCADE"))
    contract_type: Mapped[ContractType] = mapped_column(pg_enum(ContractType, "contract_type"))
    pay_cycle: Mapped[PayCycle] = mapped_column(pg_enum(PayCycle, "pay_cycle"))
    pay_day: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(BigInteger)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    counterparty: Mapped[Counterparty] = relationship(back_populates="contracts")


class FixedCost(Base):
    __tablename__ = "fixed_cost"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_fixed_cost_amount"), CheckConstraint("pay_day BETWEEN 1 AND 31", name="ck_fixed_cost_pay_day"))
    fixed_cost_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.business_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    pay_cycle: Mapped[PayCycle] = mapped_column(pg_enum(PayCycle, "pay_cycle"))
    pay_day: Mapped[int] = mapped_column(Integer)
    months: Mapped[str | None] = mapped_column(String(40))  # 분기 고정비 지급 월, 예: "3,6,9,12"
    amount: Mapped[int] = mapped_column(BigInteger)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contract.contract_id", ondelete="SET NULL"))


class Loan(Base):
    __tablename__ = "loan"
    __table_args__ = (CheckConstraint("installment > 0", name="ck_loan_installment"), CheckConstraint("repay_day BETWEEN 1 AND 31", name="ck_loan_repay_day"))
    loan_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.business_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    lender: Mapped[str] = mapped_column(String(100))
    principal: Mapped[int] = mapped_column(BigInteger)
    interest_rate: Mapped[float] = mapped_column(Numeric(5, 2))
    rate_type: Mapped[RateType] = mapped_column(pg_enum(RateType, "rate_type"))
    installment: Mapped[int] = mapped_column(BigInteger)
    repay_day: Mapped[int] = mapped_column(Integer)
    maturity_date: Mapped[date | None] = mapped_column(Date)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contract.contract_id", ondelete="SET NULL"))


class CashEvent(Base):
    __tablename__ = "cash_event"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_cash_event_amount"),)
    cash_event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.business_id", ondelete="CASCADE"))
    source_type: Mapped[CashSource] = mapped_column(pg_enum(CashSource, "cash_source"))
    source_id: Mapped[int] = mapped_column(BigInteger)
    label: Mapped[str] = mapped_column(String(120))
    direction: Mapped[CashDirection] = mapped_column(pg_enum(CashDirection, "cash_direction"))
    amount: Mapped[int] = mapped_column(BigInteger)
    due_date: Mapped[date] = mapped_column(Date)

    @property
    def signed(self) -> int:
        return self.amount if self.direction == CashDirection.IN else -self.amount


class ForecastRun(Base):
    __tablename__ = "forecast_run"
    run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.business_id", ondelete="CASCADE"))
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenario.scenario_id"))
    base_date: Mapped[date] = mapped_column(Date)
    start_balance: Mapped[int] = mapped_column(BigInteger)
    safety_balance: Mapped[int] = mapped_column(BigInteger)
    first_shortage_date: Mapped[date | None] = mapped_column(Date)
    shortage_amount: Mapped[int | None] = mapped_column(BigInteger)
    max_shortage_amount: Mapped[int | None] = mapped_column(BigInteger)
    min_balance: Mapped[int] = mapped_column(BigInteger)
    min_balance_date: Mapped[date] = mapped_column(Date)
    first_below_safe_date: Mapped[date | None] = mapped_column(Date)
    signal: Mapped[SignalLevel] = mapped_column(pg_enum(SignalLevel, "signal_level"))


class ForecastDaily(Base):
    __tablename__ = "forecast_daily"
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_run.run_id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger)


class Scenario(Base):
    """Sprint 2(US-09)에서 쓴다. forecast_run.scenario_id FK 대상이라 테이블만 먼저 만든다."""
    __tablename__ = "scenario"
    scenario_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.business_id", ondelete="CASCADE"))
    shock_type: Mapped[str] = mapped_column(String(30))
    params: Mapped[str] = mapped_column(Text)


class Document(Base):
    __tablename__ = "document"
    document_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.business_id", ondelete="CASCADE"))
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contract.contract_id", ondelete="SET NULL"))
    key: Mapped[str] = mapped_column(String(20))  # 예: D06
    title: Mapped[str] = mapped_column(String(200))


class DocumentChunk(Base):
    __tablename__ = "document_chunk"
    chunk_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.document_id", ondelete="CASCADE"))
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contract.contract_id", ondelete="SET NULL"))
    key: Mapped[str] = mapped_column(String(20), unique=True)  # 예: D06-3
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))


class Evidence(Base):
    __tablename__ = "evidence"
    evidence_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_run.run_id", ondelete="CASCADE"))
    ref_type: Mapped[EvidenceRef] = mapped_column(pg_enum(EvidenceRef, "evidence_ref"))
    ref_id: Mapped[str] = mapped_column(String(40))
    rank: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
