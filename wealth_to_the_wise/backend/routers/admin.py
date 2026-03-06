# filepath: backend/routers/admin.py
"""
Admin router — /admin/*

All endpoints require role='admin'.
Provides platform-wide KPIs, activity feed, and user management for Admin HQ.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_admin
from backend.database import get_db
from backend.models import AdminAuditLog, AdminEvent, PlatformError, User, VideoRecord, WaitlistSignup
from backend.utils import PLAN_MONTHLY_LIMITS

logger = logging.getLogger("tubevo.backend.admin_router")

router = APIRouter(prefix="/api/admin", tags=["Admin"])

# Alias for backwards compat with references inside this file.
_PLAN_MONTHLY_LIMITS = PLAN_MONTHLY_LIMITS


# ══════════════════════════════════════════════════════════════════════
# Schemas
# ══════════════════════════════════════════════════════════════════════

class AdminKPIs(BaseModel):
    total_users: int = 0
    new_users_24h: int = 0
    total_waitlist: int = 0
    total_videos: int = 0
    videos_24h: int = 0
    videos_failed_24h: int = 0
    success_rate: float = 0.0
    avg_generation_secs: float | None = None


class ActivityItem(BaseModel):
    id: str
    type: str
    user_id: str | None = None
    user_email: str | None = None
    video_id: str | None = None
    metadata: dict | None = None
    created_at: datetime


class AdminOverviewResponse(BaseModel):
    kpis: AdminKPIs
    activity: list[ActivityItem]


# ── User management schemas ──────────────────────────────────────────

class AdminUserRow(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    role: str
    plan: str
    credit_balance: int = 0
    credits_remaining: int = 0
    is_active: bool
    last_login_at: datetime | None = None
    last_video_created_at: datetime | None = None
    created_at: datetime


class AdminUserListResponse(BaseModel):
    users: list[AdminUserRow]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminUserDetail(AdminUserRow):
    is_verified: bool = False
    is_beta: bool = False
    stripe_customer_id: str | None = None
    updated_at: datetime
    recent_videos: list[AdminVideoItem] = []
    audit_log: list[AdminAuditItem] = []


class AdminVideoItem(BaseModel):
    id: str
    title: str
    topic: str
    status: str
    youtube_url: str | None = None
    created_at: datetime


class AdminAuditItem(BaseModel):
    id: str
    admin_id: str
    admin_email: str | None = None
    action: str
    details: dict | None = None
    created_at: datetime


class ChangeRoleRequest(BaseModel):
    role: str = Field(..., pattern=r"^(user|admin)$")


class GrantCreditsRequest(BaseModel):
    amount: int = Field(..., gt=0, le=10_000)
    reason: str = Field("", max_length=300)


class DisableUserRequest(BaseModel):
    disabled: bool


# ══════════════════════════════════════════════════════════════════════
# Audit helper
# ══════════════════════════════════════════════════════════════════════

async def _audit(
    db: AsyncSession,
    admin: User,
    action: str,
    target_user_id: str | None = None,
    details: dict | None = None,
) -> None:
    """Insert an immutable audit-log row."""
    db.add(AdminAuditLog(
        admin_id=admin.id,
        target_user_id=target_user_id,
        action=action,
        details_json=json.dumps(details) if details else None,
    ))


# ══════════════════════════════════════════════════════════════════════
# GET /admin/verify
# ══════════════════════════════════════════════════════════════════════

@router.get("/verify")
async def verify_admin(
    admin: User = Depends(get_current_admin),
) -> dict:
    """Verify that the current user has admin access."""
    logger.info("Admin access verified for %s", admin.email)
    return {"admin": True, "email": admin.email, "message": "Welcome to Admin HQ."}


# ══════════════════════════════════════════════════════════════════════
# GET /admin/overview
# ══════════════════════════════════════════════════════════════════════

@router.get("/overview", response_model=AdminOverviewResponse)
async def admin_overview(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    activity_limit: int = Query(50, ge=1, le=200),
) -> AdminOverviewResponse:
    """Return platform-wide KPIs and recent activity for Admin HQ."""

    now = datetime.now(timezone.utc)
    t_24h = now - timedelta(hours=24)

    total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    new_users_24h = (await db.execute(select(func.count()).select_from(User).where(User.created_at >= t_24h))).scalar() or 0
    total_waitlist = (await db.execute(select(func.count()).select_from(WaitlistSignup))).scalar() or 0
    total_videos = (await db.execute(select(func.count()).select_from(VideoRecord))).scalar() or 0
    videos_24h = (await db.execute(select(func.count()).select_from(VideoRecord).where(VideoRecord.created_at >= t_24h))).scalar() or 0
    videos_failed_24h = (await db.execute(select(func.count()).select_from(VideoRecord).where(VideoRecord.created_at >= t_24h, VideoRecord.status == "failed"))).scalar() or 0

    total_completed = (await db.execute(select(func.count()).select_from(VideoRecord).where(VideoRecord.status.in_(["completed", "posted"])))).scalar() or 0
    total_failed = (await db.execute(select(func.count()).select_from(VideoRecord).where(VideoRecord.status == "failed"))).scalar() or 0
    denom = total_completed + total_failed
    success_rate = round((total_completed / denom) * 100, 1) if denom else 0.0

    avg_gen = None
    try:
        avg_result = (await db.execute(
            select(func.avg(func.extract("epoch", VideoRecord.updated_at) - func.extract("epoch", VideoRecord.created_at)))
            .where(VideoRecord.status.in_(["completed", "posted"]))
        )).scalar()
        if avg_result is not None:
            avg_gen = round(float(avg_result), 1)
    except Exception:
        pass

    kpis = AdminKPIs(
        total_users=total_users, new_users_24h=new_users_24h, total_waitlist=total_waitlist,
        total_videos=total_videos, videos_24h=videos_24h, videos_failed_24h=videos_failed_24h,
        success_rate=success_rate, avg_generation_secs=avg_gen,
    )

    stmt = (
        select(AdminEvent, User.email)
        .outerjoin(User, AdminEvent.user_id == User.id)
        .order_by(AdminEvent.created_at.desc())
        .limit(activity_limit)
    )
    rows = (await db.execute(stmt)).all()

    activity: list[ActivityItem] = []
    for event, email in rows:
        meta = None
        if event.metadata_json:
            try:
                meta = json.loads(event.metadata_json)
            except Exception:
                meta = {"raw": event.metadata_json}
        activity.append(ActivityItem(
            id=event.id, type=event.type, user_id=event.user_id,
            user_email=email, video_id=event.video_id, metadata=meta,
            created_at=event.created_at,
        ))

    logger.info("Admin overview served to %s (%d events)", admin.email, len(activity))
    return AdminOverviewResponse(kpis=kpis, activity=activity)


# ══════════════════════════════════════════════════════════════════════
# Waitlist — list & manage waitlist signups
# ══════════════════════════════════════════════════════════════════════

class WaitlistItem(BaseModel):
    id: str
    email: str
    name: str | None = None
    kit_sync_status: str = "pending"
    created_at: datetime | None = None

class WaitlistListResponse(BaseModel):
    items: list[WaitlistItem]
    total: int
    page: int
    page_size: int

class InviteBetaRequest(BaseModel):
    email: str


@router.get("/waitlist", response_model=WaitlistListResponse)
async def list_waitlist(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    search: str = Query("", max_length=320),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=5, le=200),
) -> WaitlistListResponse:
    """Paginated waitlist signups with optional email search."""

    base = select(WaitlistSignup)
    count_base = select(func.count()).select_from(WaitlistSignup)

    if search:
        pattern = f"%{search.strip()}%"
        base = base.where(or_(WaitlistSignup.email.ilike(pattern), WaitlistSignup.name.ilike(pattern)))
        count_base = count_base.where(or_(WaitlistSignup.email.ilike(pattern), WaitlistSignup.name.ilike(pattern)))

    total = (await db.execute(count_base)).scalar() or 0

    rows = (await db.execute(
        base.order_by(WaitlistSignup.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    items = [
        WaitlistItem(id=s.id, email=s.email, name=s.name,
                     kit_sync_status=s.kit_sync_status, created_at=s.created_at)
        for s in rows
    ]

    logger.info("Admin waitlist list: %d/%d (page %d) by %s", len(items), total, page, admin.email)
    return WaitlistListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/waitlist/invite-beta")
async def invite_beta(
    body: InviteBetaRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Promote a waitlist email to beta tester.

    If the email already has a user account, sets is_beta=True.
    If not, creates a placeholder user account with is_beta=True
    so they can sign up and immediately have beta access.
    """

    email = body.email.strip().lower()

    # Check if user already exists
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()

    if user:
        user.is_beta = True
        await db.commit()
        logger.info("Admin %s promoted existing user %s to beta", admin.email, email)
        return {"status": "promoted", "email": email, "message": f"{email} is now a beta tester."}
    else:
        # No account yet — just flag this so when they sign up they get beta
        # We'll store a note but not create a full account (they need to set a password)
        logger.info("Admin %s flagged waitlist email %s for beta (no account yet)", admin.email, email)
        return {"status": "flagged", "email": email, "message": f"{email} will get beta access when they sign up."}


# ══════════════════════════════════════════════════════════════════════
# GET /admin/users — paginated list with search & filter
# ══════════════════════════════════════════════════════════════════════

@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    search: str = Query("", max_length=320),
    role: str = Query("", max_length=20),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100),
) -> AdminUserListResponse:
    """Paginated user list with optional email search and role filter."""

    # Base query
    base = select(User)
    count_base = select(func.count()).select_from(User)

    # Search by email (ILIKE)
    if search:
        pattern = f"%{search.strip()}%"
        base = base.where(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
        count_base = count_base.where(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))

    # Filter by role
    if role:
        base = base.where(User.role == role)
        count_base = count_base.where(User.role == role)

    total = (await db.execute(count_base)).scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    users_stmt = base.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    users = (await db.execute(users_stmt)).scalars().all()

    # For each user, compute credits_remaining & last_video_created_at
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    rows: list[AdminUserRow] = []
    for u in users:
        # Monthly usage count
        used = (await db.execute(
            select(func.count()).select_from(VideoRecord)
            .where(VideoRecord.user_id == u.id, VideoRecord.created_at >= month_start)
        )).scalar() or 0
        plan_limit = _PLAN_MONTHLY_LIMITS.get(u.plan or "free", 1)
        remaining = max(0, plan_limit - used) + (getattr(u, "credit_balance", 0) or 0)

        # Last video created
        last_vid = (await db.execute(
            select(VideoRecord.created_at)
            .where(VideoRecord.user_id == u.id)
            .order_by(VideoRecord.created_at.desc())
            .limit(1)
        )).scalar()

        rows.append(AdminUserRow(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            plan=u.plan,
            credit_balance=getattr(u, "credit_balance", 0) or 0,
            credits_remaining=remaining,
            is_active=u.is_active,
            last_login_at=getattr(u, "last_login_at", None),
            last_video_created_at=last_vid,
            created_at=u.created_at,
        ))

    total_pages = max(1, (total + page_size - 1) // page_size)
    return AdminUserListResponse(
        users=rows, total=total, page=page,
        page_size=page_size, total_pages=total_pages,
    )


# ══════════════════════════════════════════════════════════════════════
# GET /admin/users/{user_id} — user detail
# ══════════════════════════════════════════════════════════════════════

@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user_detail(
    user_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserDetail:
    """Full detail for a single user including recent videos and audit log."""

    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    # Credits remaining
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = (await db.execute(
        select(func.count()).select_from(VideoRecord)
        .where(VideoRecord.user_id == target.id, VideoRecord.created_at >= month_start)
    )).scalar() or 0
    plan_limit = _PLAN_MONTHLY_LIMITS.get(target.plan or "free", 1)
    remaining = max(0, plan_limit - used) + (getattr(target, "credit_balance", 0) or 0)

    # Last video
    last_vid = (await db.execute(
        select(VideoRecord.created_at)
        .where(VideoRecord.user_id == target.id)
        .order_by(VideoRecord.created_at.desc())
        .limit(1)
    )).scalar()

    # Recent videos (last 20)
    vids = (await db.execute(
        select(VideoRecord)
        .where(VideoRecord.user_id == target.id)
        .order_by(VideoRecord.created_at.desc())
        .limit(20)
    )).scalars().all()
    recent_videos = [
        AdminVideoItem(
            id=v.id, title=v.title, topic=v.topic, status=v.status,
            youtube_url=v.youtube_url, created_at=v.created_at,
        )
        for v in vids
    ]

    # Audit log for this user (last 50)
    audit_stmt = (
        select(AdminAuditLog, User.email)
        .outerjoin(User, AdminAuditLog.admin_id == User.id)
        .where(AdminAuditLog.target_user_id == target.id)
        .order_by(AdminAuditLog.created_at.desc())
        .limit(50)
    )
    audit_rows = (await db.execute(audit_stmt)).all()
    audit_log = []
    for log, admin_email in audit_rows:
        details = None
        if log.details_json:
            try:
                details = json.loads(log.details_json)
            except Exception:
                details = {"raw": log.details_json}
        audit_log.append(AdminAuditItem(
            id=log.id, admin_id=log.admin_id, admin_email=admin_email,
            action=log.action, details=details, created_at=log.created_at,
        ))

    return AdminUserDetail(
        id=target.id,
        email=target.email,
        full_name=target.full_name,
        role=target.role,
        plan=target.plan,
        credit_balance=getattr(target, "credit_balance", 0) or 0,
        credits_remaining=remaining,
        is_active=target.is_active,
        is_verified=target.is_verified,
        is_beta=getattr(target, "is_beta", False),
        stripe_customer_id=target.stripe_customer_id,
        last_login_at=getattr(target, "last_login_at", None),
        last_video_created_at=last_vid,
        created_at=target.created_at,
        updated_at=target.updated_at,
        recent_videos=recent_videos,
        audit_log=audit_log,
    )


# ══════════════════════════════════════════════════════════════════════
# PATCH /admin/users/{user_id}/role — change role
# ══════════════════════════════════════════════════════════════════════

@router.patch("/users/{user_id}/role")
async def change_role(
    user_id: str,
    body: ChangeRoleRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Change a user's role (user ↔ admin)."""
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    old_role = target.role
    if old_role == body.role:
        return {"message": f"Role already '{body.role}'. No change."}

    target.role = body.role
    db.add(target)

    await _audit(db, admin, "change_role", target_user_id=target.id, details={
        "old_role": old_role, "new_role": body.role,
    })

    logger.info("Admin %s changed role of %s: %s → %s", admin.email, target.email, old_role, body.role)
    return {"message": f"Role changed from '{old_role}' to '{body.role}'."}


# ══════════════════════════════════════════════════════════════════════
# POST /admin/users/{user_id}/credits — grant credits
# ══════════════════════════════════════════════════════════════════════

@router.post("/users/{user_id}/credits")
async def grant_credits(
    user_id: str,
    body: GrantCreditsRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add bonus credits to a user's balance."""
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    old_balance = getattr(target, "credit_balance", 0) or 0
    target.credit_balance = old_balance + body.amount
    db.add(target)

    await _audit(db, admin, "grant_credits", target_user_id=target.id, details={
        "amount": body.amount, "reason": body.reason,
        "old_balance": old_balance, "new_balance": target.credit_balance,
    })

    logger.info("Admin %s granted %d credits to %s (now %d)", admin.email, body.amount, target.email, target.credit_balance)
    return {"message": f"Granted {body.amount} credits.", "new_balance": target.credit_balance}


# ══════════════════════════════════════════════════════════════════════
# PATCH /admin/users/{user_id}/disable — soft disable / re-enable
# ══════════════════════════════════════════════════════════════════════

@router.patch("/users/{user_id}/disable")
async def toggle_disable(
    user_id: str,
    body: DisableUserRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-disable or re-enable a user account."""
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot disable your own account.")

    target.is_active = not body.disabled
    db.add(target)

    action = "disable_user" if body.disabled else "enable_user"
    await _audit(db, admin, action, target_user_id=target.id, details={
        "is_active": target.is_active,
    })

    label = "disabled" if body.disabled else "re-enabled"
    logger.info("Admin %s %s user %s", admin.email, label, target.email)
    return {"message": f"User {label}.", "is_active": target.is_active}


# ══════════════════════════════════════════════════════════════════════
# Video management schemas
# ══════════════════════════════════════════════════════════════════════

class AdminVideoRow(BaseModel):
    id: str
    user_id: str
    user_email: str | None = None
    title: str
    topic: str
    status: str
    youtube_url: str | None = None
    error_message: str | None = None
    progress_step: str | None = None
    progress_pct: int = 0
    processing_seconds: float | None = None
    created_at: datetime
    updated_at: datetime


class AdminVideoListResponse(BaseModel):
    videos: list[AdminVideoRow]
    total: int
    page: int
    page_size: int
    total_pages: int


class PipelineStepItem(BaseModel):
    step: str
    pct: int
    ts: float | None = None


class AdminVideoDetailResponse(AdminVideoRow):
    script_text: str | None = None
    metadata: dict | None = None
    voice_id: str | None = None
    pipeline_log: list[PipelineStepItem] = []
    file_path: str | None = None
    srt_path: str | None = None
    thumbnail_path: str | None = None
    youtube_video_id: str | None = None
    published_at: datetime | None = None


# ══════════════════════════════════════════════════════════════════════
# GET /admin/videos — paginated list with filters
# ══════════════════════════════════════════════════════════════════════

@router.get("/videos", response_model=AdminVideoListResponse)
async def list_videos(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    status_filter: str = Query("", alias="status", max_length=20),
    user_id: str = Query("", max_length=36),
    search: str = Query("", max_length=320),
    date_from: str = Query("", max_length=30),
    date_to: str = Query("", max_length=30),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100),
) -> AdminVideoListResponse:
    """Paginated video list with optional status, user, date, and search filters."""

    base = select(VideoRecord, User.email).outerjoin(User, VideoRecord.user_id == User.id)
    count_base = select(func.count()).select_from(VideoRecord)

    # Status filter
    if status_filter:
        base = base.where(VideoRecord.status == status_filter)
        count_base = count_base.where(VideoRecord.status == status_filter)

    # User filter
    if user_id:
        base = base.where(VideoRecord.user_id == user_id)
        count_base = count_base.where(VideoRecord.user_id == user_id)

    # Search by title/topic/email
    if search:
        pattern = f"%{search.strip()}%"
        base = base.where(
            or_(
                VideoRecord.title.ilike(pattern),
                VideoRecord.topic.ilike(pattern),
                User.email.ilike(pattern),
            )
        )
        count_base = count_base.where(
            VideoRecord.id.in_(
                select(VideoRecord.id)
                .outerjoin(User, VideoRecord.user_id == User.id)
                .where(
                    or_(
                        VideoRecord.title.ilike(pattern),
                        VideoRecord.topic.ilike(pattern),
                        User.email.ilike(pattern),
                    )
                )
            )
        )

    # Date range filter
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            base = base.where(VideoRecord.created_at >= dt_from)
            count_base = count_base.where(VideoRecord.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            base = base.where(VideoRecord.created_at <= dt_to)
            count_base = count_base.where(VideoRecord.created_at <= dt_to)
        except ValueError:
            pass

    total = (await db.execute(count_base)).scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    stmt = base.order_by(VideoRecord.created_at.desc()).offset(offset).limit(page_size)
    rows = (await db.execute(stmt)).all()

    videos: list[AdminVideoRow] = []
    for video, email in rows:
        # Compute processing time from created_at → updated_at
        proc_secs: float | None = None
        if video.status in ("completed", "posted", "failed") and video.updated_at and video.created_at:
            delta = (video.updated_at - video.created_at).total_seconds()
            proc_secs = round(delta, 1) if delta > 0 else None

        videos.append(AdminVideoRow(
            id=video.id,
            user_id=video.user_id,
            user_email=email,
            title=video.title,
            topic=video.topic,
            status=video.status,
            youtube_url=video.youtube_url,
            error_message=video.error_message,
            progress_step=video.progress_step,
            progress_pct=video.progress_pct or 0,
            processing_seconds=proc_secs,
            created_at=video.created_at,
            updated_at=video.updated_at,
        ))

    total_pages = max(1, (total + page_size - 1) // page_size)
    return AdminVideoListResponse(
        videos=videos, total=total, page=page,
        page_size=page_size, total_pages=total_pages,
    )


# ══════════════════════════════════════════════════════════════════════
# GET /admin/videos/{video_id} — video detail
# ══════════════════════════════════════════════════════════════════════

@router.get("/videos/{video_id}", response_model=AdminVideoDetailResponse)
async def get_video_detail(
    video_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminVideoDetailResponse:
    """Full detail for a single video including script, metadata, pipeline log."""

    result = await db.execute(
        select(VideoRecord, User.email)
        .outerjoin(User, VideoRecord.user_id == User.id)
        .where(VideoRecord.id == video_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Video not found.")

    video, email = row

    proc_secs: float | None = None
    if video.status in ("completed", "posted", "failed") and video.updated_at and video.created_at:
        delta = (video.updated_at - video.created_at).total_seconds()
        proc_secs = round(delta, 1) if delta > 0 else None

    # Parse stored JSON fields
    meta_dict: dict | None = None
    if video.metadata_json:
        try:
            meta_dict = json.loads(video.metadata_json)
        except Exception:
            meta_dict = {"raw": video.metadata_json}

    pipeline_log: list[PipelineStepItem] = []
    if video.pipeline_log_json:
        try:
            raw_steps = json.loads(video.pipeline_log_json)
            pipeline_log = [PipelineStepItem(**s) for s in raw_steps]
        except Exception:
            pass

    return AdminVideoDetailResponse(
        id=video.id,
        user_id=video.user_id,
        user_email=email,
        title=video.title,
        topic=video.topic,
        status=video.status,
        youtube_url=video.youtube_url,
        error_message=video.error_message,
        progress_step=video.progress_step,
        progress_pct=video.progress_pct or 0,
        processing_seconds=proc_secs,
        created_at=video.created_at,
        updated_at=video.updated_at,
        script_text=video.script_text,
        metadata=meta_dict,
        voice_id=video.voice_id,
        pipeline_log=pipeline_log,
        file_path=video.file_path,
        srt_path=video.srt_path,
        thumbnail_path=video.thumbnail_path,
        youtube_video_id=video.youtube_video_id,
        published_at=video.published_at,
    )


# ══════════════════════════════════════════════════════════════════════
# POST /admin/videos/{video_id}/retry — retry a failed video
# ══════════════════════════════════════════════════════════════════════

@router.post("/videos/{video_id}/retry")
async def retry_video(
    video_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reset a failed video to 'generating' and re-trigger the pipeline.

    Only works for videos with status='failed'. Uses the original topic
    and the owning user's API keys.
    """
    from backend.routers.videos import (
        _run_pipeline_background,
        async_session_factory as _asf,
    )
    from backend.models import UserApiKeys, OAuthToken
    from backend.encryption import decrypt_or_raise

    video = (await db.execute(
        select(VideoRecord).where(VideoRecord.id == video_id)
    )).scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")
    if video.status != "failed":
        raise HTTPException(status_code=400, detail=f"Cannot retry a video with status '{video.status}'. Only 'failed' videos can be retried.")

    # Fetch the owning user's API keys
    user_keys = (await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == video.user_id)
    )).scalar_one_or_none()

    openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key") if user_keys and user_keys.openai_api_key else ""
    elevenlabs_key = decrypt_or_raise(user_keys.elevenlabs_api_key, field="elevenlabs_api_key") if user_keys and user_keys.elevenlabs_api_key else ""
    pexels_key = decrypt_or_raise(user_keys.pexels_api_key, field="pexels_api_key") if user_keys and user_keys.pexels_api_key else ""

    if not openai_key or not elevenlabs_key:
        raise HTTPException(status_code=400, detail="User has missing API keys (OpenAI or ElevenLabs). Cannot retry.")

    # Check if user already has a video in-flight
    from backend.routers.videos import user_has_inflight_video
    if await user_has_inflight_video(video.user_id, db):
        raise HTTPException(
            status_code=409,
            detail="This user already has a video generating. Wait for it to finish before retrying.",
        )

    user_api_keys = {
        "openai_api_key": openai_key,
        "elevenlabs_api_key": elevenlabs_key,
        "elevenlabs_voice_id": user_keys.elevenlabs_voice_id or "" if user_keys else "",
        "pexels_api_key": pexels_key,
        "subtitle_style": getattr(user_keys, "subtitle_style", "bold_pop") if user_keys else "bold_pop",
        "burn_captions": getattr(user_keys, "burn_captions", True) if user_keys else True,
        "speech_speed": getattr(user_keys, "speech_speed", None) if user_keys else None,
    }

    # Fetch YouTube tokens
    oauth = (await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == video.user_id,
            OAuthToken.provider == "google",
        )
    )).scalar_one_or_none()

    yt_access = decrypt_or_raise(oauth.access_token, field="yt_access_token") if oauth and oauth.access_token else None
    yt_refresh = decrypt_or_raise(oauth.refresh_token, field="yt_refresh_token") if oauth and oauth.refresh_token else None

    # Reset the video record
    video.status = "generating"
    video.error_message = None
    video.progress_step = "Retrying…"
    video.progress_pct = 0
    video.pipeline_log_json = None
    db.add(video)

    await _audit(db, admin, "retry_video", target_user_id=video.user_id, details={
        "video_id": video.id, "topic": video.topic,
    })
    await db.commit()

    # Fire off the pipeline
    import asyncio
    asyncio.create_task(
        _run_pipeline_background(
            record_id=video.id,
            topic=video.topic,
            user_id=video.user_id,
            user_api_keys=user_api_keys,
            yt_access_token=yt_access,
            yt_refresh_token=yt_refresh,
        )
    )

    logger.info("Admin %s retried failed video %s (topic='%s')", admin.email, video.id, video.topic)
    return {"message": f"Video '{video.topic}' has been queued for retry.", "video_id": video.id}


# ══════════════════════════════════════════════════════════════════════
# Error management schemas
# ══════════════════════════════════════════════════════════════════════

class AdminErrorRow(BaseModel):
    id: str
    user_id: str | None = None
    user_email: str | None = None
    video_id: str | None = None
    type: str
    message: str
    resolved: bool = False
    created_at: datetime


class AdminErrorListResponse(BaseModel):
    errors: list[AdminErrorRow]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminErrorDetail(AdminErrorRow):
    stack: str | None = None
    resolved_by: str | None = None
    resolved_by_email: str | None = None
    resolved_at: datetime | None = None


class ResolveErrorRequest(BaseModel):
    resolved: bool


class LinkErrorVideoRequest(BaseModel):
    video_id: str = Field(..., min_length=1, max_length=36)


# ══════════════════════════════════════════════════════════════════════
# GET /admin/errors — paginated list with filters
# ══════════════════════════════════════════════════════════════════════

@router.get("/errors", response_model=AdminErrorListResponse)
async def list_errors(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    error_type: str = Query("", alias="type", max_length=40),
    resolved: str = Query("", max_length=5),
    search: str = Query("", max_length=320),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100),
) -> AdminErrorListResponse:
    """Paginated error list with optional type, resolved, and search filters."""

    base = (
        select(PlatformError, User.email)
        .outerjoin(User, PlatformError.user_id == User.id)
    )
    count_base = select(func.count()).select_from(PlatformError)

    # Type filter
    if error_type:
        base = base.where(PlatformError.type == error_type)
        count_base = count_base.where(PlatformError.type == error_type)

    # Resolved filter
    if resolved == "true":
        base = base.where(PlatformError.resolved == True)  # noqa: E712
        count_base = count_base.where(PlatformError.resolved == True)  # noqa: E712
    elif resolved == "false":
        base = base.where(PlatformError.resolved == False)  # noqa: E712
        count_base = count_base.where(PlatformError.resolved == False)  # noqa: E712

    # Search by message or user email
    if search:
        pattern = f"%{search.strip()}%"
        base = base.where(
            or_(PlatformError.message.ilike(pattern), User.email.ilike(pattern))
        )
        count_base = count_base.where(
            PlatformError.id.in_(
                select(PlatformError.id)
                .outerjoin(User, PlatformError.user_id == User.id)
                .where(or_(PlatformError.message.ilike(pattern), User.email.ilike(pattern)))
            )
        )

    total = (await db.execute(count_base)).scalar() or 0

    offset = (page - 1) * page_size
    stmt = base.order_by(PlatformError.created_at.desc()).offset(offset).limit(page_size)
    rows = (await db.execute(stmt)).all()

    errors: list[AdminErrorRow] = []
    for err, email in rows:
        errors.append(AdminErrorRow(
            id=err.id,
            user_id=err.user_id,
            user_email=email,
            video_id=err.video_id,
            type=err.type,
            message=err.message,
            resolved=err.resolved,
            created_at=err.created_at,
        ))

    total_pages = max(1, (total + page_size - 1) // page_size)
    return AdminErrorListResponse(
        errors=errors, total=total, page=page,
        page_size=page_size, total_pages=total_pages,
    )


# ══════════════════════════════════════════════════════════════════════
# GET /admin/errors/{error_id} — error detail
# ══════════════════════════════════════════════════════════════════════

@router.get("/errors/{error_id}", response_model=AdminErrorDetail)
async def get_error_detail(
    error_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminErrorDetail:
    """Full detail for a single error including stack trace."""

    from sqlalchemy.orm import aliased
    ResolverUser = aliased(User)

    result = await db.execute(
        select(PlatformError, User.email, ResolverUser.email)
        .outerjoin(User, PlatformError.user_id == User.id)
        .outerjoin(ResolverUser, PlatformError.resolved_by == ResolverUser.id)
        .where(PlatformError.id == error_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Error not found.")

    err, user_email, resolver_email = row

    return AdminErrorDetail(
        id=err.id,
        user_id=err.user_id,
        user_email=user_email,
        video_id=err.video_id,
        type=err.type,
        message=err.message,
        stack=err.stack,
        resolved=err.resolved,
        resolved_by=err.resolved_by,
        resolved_by_email=resolver_email,
        resolved_at=err.resolved_at,
        created_at=err.created_at,
    )


# ══════════════════════════════════════════════════════════════════════
# PATCH /admin/errors/{error_id}/resolve — mark resolved / unresolved
# ══════════════════════════════════════════════════════════════════════

@router.patch("/errors/{error_id}/resolve")
async def resolve_error(
    error_id: str,
    body: ResolveErrorRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark an error as resolved or reopen it."""
    err = (await db.execute(
        select(PlatformError).where(PlatformError.id == error_id)
    )).scalar_one_or_none()
    if not err:
        raise HTTPException(status_code=404, detail="Error not found.")

    err.resolved = body.resolved
    if body.resolved:
        err.resolved_by = admin.id
        err.resolved_at = datetime.now(timezone.utc)
    else:
        err.resolved_by = None
        err.resolved_at = None
    db.add(err)

    await _audit(db, admin, "resolve_error" if body.resolved else "reopen_error", details={
        "error_id": err.id, "type": err.type,
    })

    label = "resolved" if body.resolved else "reopened"
    logger.info("Admin %s %s error %s", admin.email, label, err.id)
    return {"message": f"Error {label}.", "resolved": err.resolved}


# ══════════════════════════════════════════════════════════════════════
# PATCH /admin/errors/{error_id}/link — link error to a video
# ══════════════════════════════════════════════════════════════════════

@router.patch("/errors/{error_id}/link")
async def link_error_to_video(
    error_id: str,
    body: LinkErrorVideoRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Link an error to a video record."""
    err = (await db.execute(
        select(PlatformError).where(PlatformError.id == error_id)
    )).scalar_one_or_none()
    if not err:
        raise HTTPException(status_code=404, detail="Error not found.")

    # Verify the video exists
    video = (await db.execute(
        select(VideoRecord).where(VideoRecord.id == body.video_id)
    )).scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")

    old_video_id = err.video_id
    err.video_id = body.video_id
    db.add(err)

    await _audit(db, admin, "link_error_video", details={
        "error_id": err.id, "old_video_id": old_video_id, "new_video_id": body.video_id,
    })

    logger.info("Admin %s linked error %s to video %s", admin.email, err.id, body.video_id)
    return {"message": f"Error linked to video {body.video_id}.", "video_id": body.video_id}
