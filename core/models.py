# core/models.py
from datetime import datetime, date
from typing import Optional, Literal, List
from sqlmodel import SQLModel, Field, Relationship
from uuid import uuid4
from enum import Enum
from sqlalchemy import Column
from sqlalchemy.types import LargeBinary  # just for the annotation
from sqlalchemy import UniqueConstraint

class AssessmentKind(str, Enum):
    mcq = "mcq"
    cloze = "cloze"
    open = "open"
    flashcard = "flashcard"



def _uuid() -> str:  # deterministic UUIDs not important for now
    return str(uuid4())

# ---------- Users & Interests ----------
class User(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    email: str = Field(unique=True, index=True)
    full_name: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    enrollments: List["InterestEnrollment"] = Relationship(back_populates="user")


class Interest(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    slug: str = Field(unique=True, index=True)
    title: str
    daily_time_budget: int | None = None
    streak_gate_correct_in_row: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    enrollments: List["InterestEnrollment"] = Relationship(back_populates="interest")
    skills:      List["SkillNode"]           = Relationship(back_populates="interest")


class InterestEnrollment(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    interest_id: str = Field(foreign_key="interest.id")
    enrolled_on: datetime = Field(default_factory=datetime.utcnow)

    user:     User     = Relationship(back_populates="enrollments")
    interest: Interest = Relationship(back_populates="enrollments")


# ---------- Skill tree ----------
class SkillNode(SQLModel, table=True):
    id: str = Field(primary_key=True)
    interest_id: str = Field(foreign_key="interest.id")
    parent_id: str | None = Field(foreign_key="skillnode.id", default=None, index=True)
    label: str
    depth: int = 0  # cached for cheap tree queries

    interest: Interest           = Relationship(back_populates="skills")
    parent:   Optional["SkillNode"] = Relationship(back_populates="children", sa_relationship_kwargs={"remote_side": "SkillNode.id"})
    children:    List["SkillNode"]           = Relationship(back_populates="parent")
    assessments: List["AssessmentItem"]      = Relationship(back_populates="skill")


# ---------- Assessment & attempts ----------
class AssessmentItem(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    skill_id: str = Field(foreign_key="skillnode.id")
    kind: AssessmentKind = Field(default=AssessmentKind.flashcard)
    question: str
    answer: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    skill:     SkillNode         = Relationship(back_populates="assessments")
    attempts:  List["Attempt"]   = Relationship(back_populates="item")
    srs_meta: Optional["SpacedRepCard"] = Relationship(
    back_populates="item",
    sa_relationship_kwargs={"uselist": False}
    )


class Attempt(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    item_id: str = Field(foreign_key="assessmentitem.id")
    user_id: str = Field(foreign_key="user.id")
    ts: datetime = Field(default_factory=datetime.utcnow)
    is_correct: bool
    response: str | None = None
    latency_ms: int | None = None

    item: AssessmentItem = Relationship(back_populates="attempts")
    user: User           = Relationship()


class SpacedRepCard(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    item_id: str = Field(foreign_key="assessmentitem.id", unique=True)
    ease_factor: float = 2.5
    interval: int = 1
    due_on: date = Field(default_factory=date.today)
    streak: int = 0

    item: AssessmentItem = Relationship(back_populates="srs_meta")


# ---------- Progress snapshot ----------
class SkillProgress(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    skill_id: str = Field(foreign_key="skillnode.id")
    mastery: float = 0.0
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "skill_id"),)


# ---------- Embeddings ----------
class Embedding(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    object_type: str
    object_id: str
    vector: bytes = Field(sa_column=Column("vector", LargeBinary))  # pgvector uses type name "vector"
    dim: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

