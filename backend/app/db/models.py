from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    platform_reviews: Mapped[list["PlatformReview"]] = relationship(back_populates="project")


class PlatformReview(Base):
    __tablename__ = "platform_reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    project_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_score_pct: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    llm_provider: Mapped[str] = mapped_column(String, nullable=False)
    llm_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    compile_check_mode: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    workbook_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Excludes code_context/prompt_log -- those can run to 120,000 characters
    # each and aren't needed for the approval record, only the live debug
    # view, which stays ephemeral (lost on restart) exactly as today.
    result_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Optional["Project"]] = relationship(back_populates="platform_reviews")
