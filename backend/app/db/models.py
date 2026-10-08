from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, JSON, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
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
    # Explicit precision/scale (0.0-100.0, matching every round(x, 1) call
    # site that computes this value) -- an unconstrained Numeric stores the
    # exact binary expansion of the Python float (e.g. 88.4 becomes
    # 88.400000000000005684...), since Postgres has no scale to round to.
    total_score_pct: Mapped[Optional[float]] = mapped_column(Numeric(4, 1), nullable=True)
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
    # Who's assigned to review this specific review -- a real reference to a
    # User account (not the free-text created_by/approved_by above, which
    # belong to a separate, unrelated feature: uploading an already-completed
    # sheet). A real FK, not a denormalized name/email, so it stays correct
    # if the assigned user's email changes and to support emailing them later.
    reviewer_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)

    project: Mapped[Optional["Project"]] = relationship(back_populates="platform_reviews")


class OrgSettings(Base):
    """Singleton row (id always 1) holding org-wide defaults."""

    __tablename__ = "org_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    default_llm_provider: Mapped[str] = mapped_column(String, nullable=False)
    default_ollama_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    devops_pat_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    devops_pat_last4: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    devops_pat_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    devops_pat_updated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    auto_compile_modes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class ClauseChecklist(Base):
    __tablename__ = "clause_checklists"
    __table_args__ = (UniqueConstraint("platform", "sub_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    sub_id: Mapped[str] = mapped_column(String, nullable=False)
    checklist_text: Mapped[str] = mapped_column(String, nullable=False)


class SampleTemplate(Base):
    __tablename__ = "sample_templates"

    platform: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # see app.auth.permissions.ALL_ROLES
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProjectManager(Base):
    """Which project_manager users may see which projects (many-to-many)."""

    __tablename__ = "project_managers"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)


class ProjectPlatform(Base):
    """Which tracked platforms (app.quarterly.TRACKED_PLATFORMS) a project has."""

    __tablename__ = "project_platforms"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    platform: Mapped[str] = mapped_column(String, primary_key=True)


class ReviewCycle(Base):
    """A project's review for one calendar quarter, started by a coordinator."""

    __tablename__ = "review_cycles"
    __table_args__ = (UniqueConstraint("project_id", "year", "quarter"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    initiated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewCycleAssignment(Base):
    __tablename__ = "review_cycle_assignments"

    cycle_id: Mapped[str] = mapped_column(ForeignKey("review_cycles.id", ondelete="CASCADE"), primary_key=True)
    platform: Mapped[str] = mapped_column(String, primary_key=True)
    reviewer_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    devops_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    devops_branch: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    url_submitted_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    url_submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # waiting_for_url -> queued -> running -> completed | failed (see app.automation.worker)
    run_status: Mapped[str] = mapped_column(String, nullable=False, default="waiting_for_url", server_default="waiting_for_url")
    run_phase: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    run_progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_kind: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # "url" | "system"
    review_id: Mapped[Optional[str]] = mapped_column(ForeignKey("platform_reviews.id", ondelete="SET NULL"), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_assigned_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewer_assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationOutbox(Base):
    """Workflow emails waiting to be sent (Part 3's mailer marks sent_at)."""

    __tablename__ = "notification_outbox"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event: Mapped[str] = mapped_column(String, nullable=False)
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
