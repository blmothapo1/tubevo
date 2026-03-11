"""
Team Seats & Client Workspaces — /api/teams/*

Phase 4: Allows users on paid plans to create teams, invite members,
and collaborate on video production.

Endpoints
---------
POST   /api/teams                        — Create a team
GET    /api/teams                        — List user's teams
GET    /api/teams/{id}                   — Team details + members
PATCH  /api/teams/{id}                   — Update team name/description
DELETE /api/teams/{id}                   — Delete team (owner only)
POST   /api/teams/{id}/invite            — Invite a member by email
GET    /api/teams/invites/pending        — List user's pending invitations
POST   /api/teams/invites/{token}/accept — Accept an invitation
POST   /api/teams/invites/{token}/decline — Decline an invitation
DELETE /api/teams/{id}/members/{user_id} — Remove a member
PATCH  /api/teams/{id}/members/{user_id} — Change member role
GET    /api/teams/{id}/activity          — Team video activity (aggregated)
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import Team, TeamMember, TeamInvite, User, VideoRecord
from backend.utils import PLAN_TEAM_SEAT_LIMITS, PLAN_MAX_TEAMS

logger = logging.getLogger("tubevo.backend.teams")

router = APIRouter(prefix="/api/teams", tags=["Teams"])

# ── Constants ────────────────────────────────────────────────────────
VALID_MEMBER_ROLES = frozenset({"admin", "editor", "viewer"})
INVITE_EXPIRY_DAYS = 7


# ── Schemas ──────────────────────────────────────────────────────────

class CreateTeamRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: str | None = Field(None, max_length=500)


class UpdateTeamRequest(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    description: str | None = Field(None, max_length=500)


class InviteMemberRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=320)
    role: str = Field("editor")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_MEMBER_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(sorted(VALID_MEMBER_ROLES))}")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address.")
        return v


class UpdateMemberRoleRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_MEMBER_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(sorted(VALID_MEMBER_ROLES))}")
        return v


class TeamMemberOut(BaseModel):
    user_id: str
    email: str
    full_name: str | None = None
    role: str
    joined_at: str


class TeamInviteOut(BaseModel):
    id: str
    team_id: str
    team_name: str
    email: str
    role: str
    invited_by_email: str
    status: str
    expires_at: str
    created_at: str


class TeamOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    owner_id: str
    owner_email: str
    member_count: int
    seat_limit: int
    created_at: str


class TeamDetailOut(TeamOut):
    members: list[TeamMemberOut]
    pending_invites: int


class TeamActivityItem(BaseModel):
    video_id: str
    topic: str
    title: str
    status: str
    created_by_email: str
    created_at: str


# ── Helpers ──────────────────────────────────────────────────────────

async def _get_team_or_404(team_id: str, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    return team


async def _require_team_role(
    team_id: str,
    user_id: str,
    db: AsyncSession,
    min_roles: frozenset[str] = frozenset({"owner", "admin"}),
) -> TeamMember:
    """Verify the user has one of the required roles in the team."""
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member or member.role not in min_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to perform this action.",
        )
    return member


async def _get_seat_count(team_id: str, db: AsyncSession) -> int:
    """Count current members in a team."""
    stmt = select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team_id)
    return (await db.execute(stmt)).scalar() or 0


async def _get_owner(team: Team, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.id == team.owner_id))
    return result.scalar_one()


# ── POST /api/teams — Create a team ─────────────────────────────────

@router.post("", response_model=TeamOut, status_code=201)
async def create_team(
    body: CreateTeamRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new team. The creator becomes the owner."""
    plan = current_user.plan or "free"
    max_teams = PLAN_MAX_TEAMS.get(plan, 0)
    seat_limit = PLAN_TEAM_SEAT_LIMITS.get(plan, 0)

    if max_teams == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teams are available on Starter, Pro, and Agency plans. Upgrade in Settings → Plan.",
        )

    # Check existing team count
    existing_count_stmt = (
        select(func.count())
        .select_from(Team)
        .where(Team.owner_id == current_user.id)
    )
    existing_count = (await db.execute(existing_count_stmt)).scalar() or 0
    if existing_count >= max_teams:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your {plan.title()} plan allows up to {max_teams} team(s). Upgrade for more.",
        )

    team = Team(
        name=body.name,
        owner_id=current_user.id,
        description=body.description,
    )
    db.add(team)
    await db.flush()

    # Auto-add owner as a member
    owner_member = TeamMember(
        team_id=team.id,
        user_id=current_user.id,
        role="owner",
    )
    db.add(owner_member)
    await db.commit()

    logger.info("Team '%s' created by %s (plan=%s)", body.name, current_user.email, plan)

    return TeamOut(
        id=team.id,
        name=team.name,
        description=team.description,
        owner_id=team.owner_id,
        owner_email=current_user.email,
        member_count=1,
        seat_limit=seat_limit,
        created_at=team.created_at.isoformat(),
    )


# ── GET /api/teams — List user's teams ──────────────────────────────

@router.get("", response_model=list[TeamOut])
async def list_teams(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all teams the current user belongs to."""
    # Find all team IDs the user is a member of
    member_stmt = (
        select(TeamMember.team_id)
        .where(TeamMember.user_id == current_user.id)
    )
    team_ids = (await db.execute(member_stmt)).scalars().all()

    if not team_ids:
        return []

    teams_stmt = select(Team).where(Team.id.in_(team_ids)).order_by(Team.created_at.desc())
    teams = (await db.execute(teams_stmt)).scalars().all()

    result = []
    for team in teams:
        owner = await _get_owner(team, db)
        member_count = await _get_seat_count(team.id, db)
        plan = owner.plan or "free"
        seat_limit = PLAN_TEAM_SEAT_LIMITS.get(plan, 0)

        result.append(TeamOut(
            id=team.id,
            name=team.name,
            description=team.description,
            owner_id=team.owner_id,
            owner_email=owner.email,
            member_count=member_count,
            seat_limit=seat_limit,
            created_at=team.created_at.isoformat(),
        ))

    return result


# ── GET /api/teams/{id} — Team details ──────────────────────────────

@router.get("/{team_id}", response_model=TeamDetailOut)
async def get_team(
    team_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get team details including members. User must be a member."""
    team = await _get_team_or_404(team_id, db)

    # Verify membership
    membership = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == current_user.id,
        )
    )
    if not membership.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Team not found.")

    # Fetch all members with user info
    members_stmt = (
        select(TeamMember, User)
        .join(User, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team_id)
        .order_by(TeamMember.joined_at)
    )
    rows = (await db.execute(members_stmt)).all()

    members = [
        TeamMemberOut(
            user_id=member.user_id,
            email=user.email,
            full_name=user.full_name,
            role=member.role,
            joined_at=member.joined_at.isoformat() if member.joined_at else "",
        )
        for member, user in rows
    ]

    # Count pending invites
    invite_count_stmt = (
        select(func.count())
        .select_from(TeamInvite)
        .where(TeamInvite.team_id == team_id, TeamInvite.status == "pending")
    )
    pending_invites = (await db.execute(invite_count_stmt)).scalar() or 0

    owner = await _get_owner(team, db)
    plan = owner.plan or "free"
    seat_limit = PLAN_TEAM_SEAT_LIMITS.get(plan, 0)

    return TeamDetailOut(
        id=team.id,
        name=team.name,
        description=team.description,
        owner_id=team.owner_id,
        owner_email=owner.email,
        member_count=len(members),
        seat_limit=seat_limit,
        created_at=team.created_at.isoformat(),
        members=members,
        pending_invites=pending_invites,
    )


# ── PATCH /api/teams/{id} — Update team ─────────────────────────────

@router.patch("/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: str,
    body: UpdateTeamRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update team name/description. Requires owner or admin role."""
    team = await _get_team_or_404(team_id, db)
    await _require_team_role(team_id, current_user.id, db, frozenset({"owner", "admin"}))

    if body.name is not None:
        team.name = body.name
    if body.description is not None:
        team.description = body.description
    team.updated_at = datetime.now(timezone.utc)

    await db.commit()

    owner = await _get_owner(team, db)
    member_count = await _get_seat_count(team_id, db)
    plan = owner.plan or "free"

    return TeamOut(
        id=team.id,
        name=team.name,
        description=team.description,
        owner_id=team.owner_id,
        owner_email=owner.email,
        member_count=member_count,
        seat_limit=PLAN_TEAM_SEAT_LIMITS.get(plan, 0),
        created_at=team.created_at.isoformat(),
    )


# ── DELETE /api/teams/{id} — Delete team ─────────────────────────────

@router.delete("/{team_id}")
async def delete_team(
    team_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a team. Owner only."""
    team = await _get_team_or_404(team_id, db)
    if team.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the team owner can delete the team.",
        )

    # Cascade deletes are handled by FK ondelete="CASCADE" on team_members and team_invites
    await db.execute(sa_delete(TeamInvite).where(TeamInvite.team_id == team_id))
    await db.execute(sa_delete(TeamMember).where(TeamMember.team_id == team_id))
    await db.delete(team)
    await db.commit()

    logger.info("Team '%s' deleted by %s", team.name, current_user.email)
    return {"detail": "Team deleted."}


# ── POST /api/teams/{id}/invite — Invite a member ───────────────────

@router.post("/{team_id}/invite", status_code=201)
async def invite_member(
    team_id: str,
    body: InviteMemberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invite a user to the team by email. Requires owner or admin role."""
    team = await _get_team_or_404(team_id, db)
    await _require_team_role(team_id, current_user.id, db, frozenset({"owner", "admin"}))

    # Check seat limit
    owner = await _get_owner(team, db)
    plan = owner.plan or "free"
    seat_limit = PLAN_TEAM_SEAT_LIMITS.get(plan, 0)
    current_seats = await _get_seat_count(team_id, db)

    # Also count pending invites toward the limit
    pending_stmt = (
        select(func.count())
        .select_from(TeamInvite)
        .where(TeamInvite.team_id == team_id, TeamInvite.status == "pending")
    )
    pending_count = (await db.execute(pending_stmt)).scalar() or 0

    if current_seats + pending_count >= seat_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Team has reached the {seat_limit}-seat limit for the {plan.title()} plan. Upgrade to add more members.",
        )

    # Check if user is already a member
    existing_member = await db.execute(
        select(TeamMember)
        .join(User, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team_id, User.email == body.email)
    )
    if existing_member.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{body.email} is already a member of this team.",
        )

    # Check if there's already a pending invite for this email
    existing_invite = await db.execute(
        select(TeamInvite).where(
            TeamInvite.team_id == team_id,
            TeamInvite.email == body.email,
            TeamInvite.status == "pending",
        )
    )
    if existing_invite.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A pending invitation already exists for {body.email}.",
        )

    # Can't invite yourself
    if body.email == current_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can't invite yourself.",
        )

    invite = TeamInvite(
        team_id=team_id,
        email=body.email,
        role=body.role,
        invited_by=current_user.id,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(invite)
    await db.commit()

    logger.info(
        "Team invite sent: %s → %s (role=%s) in team '%s'",
        current_user.email, body.email, body.role, team.name,
    )

    # TODO: Send email notification when email service is ready

    return {
        "detail": f"Invitation sent to {body.email}.",
        "invite_id": invite.id,
        "token": invite.token,
        "expires_at": invite.expires_at.isoformat(),
    }


# ── GET /api/teams/invites/pending — User's pending invites ─────────

@router.get("/invites/pending", response_model=list[TeamInviteOut])
async def list_pending_invites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all pending invitations for the current user's email."""
    stmt = (
        select(TeamInvite, Team, User)
        .join(Team, TeamInvite.team_id == Team.id)
        .join(User, TeamInvite.invited_by == User.id)
        .where(
            TeamInvite.email == current_user.email,
            TeamInvite.status == "pending",
            TeamInvite.expires_at > datetime.now(timezone.utc),
        )
        .order_by(TeamInvite.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    return [
        TeamInviteOut(
            id=invite.id,
            team_id=invite.team_id,
            team_name=team.name,
            email=invite.email,
            role=invite.role,
            invited_by_email=inviter.email,
            status=invite.status,
            expires_at=invite.expires_at.isoformat(),
            created_at=invite.created_at.isoformat(),
        )
        for invite, team, inviter in rows
    ]


# ── POST /api/teams/invites/{token}/accept — Accept invitation ──────

@router.post("/invites/{token}/accept")
async def accept_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept a team invitation."""
    result = await db.execute(
        select(TeamInvite).where(
            TeamInvite.token == token,
            TeamInvite.status == "pending",
        )
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found or already used.")

    if invite.expires_at < datetime.now(timezone.utc):
        invite.status = "expired"
        await db.commit()
        raise HTTPException(status_code=410, detail="This invitation has expired.")

    if invite.email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation was sent to a different email address.",
        )

    # Check if already a member
    existing = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == invite.team_id,
            TeamMember.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        invite.status = "accepted"
        invite.accepted_at = datetime.now(timezone.utc)
        await db.commit()
        return {"detail": "You're already a member of this team."}

    # Add as member
    member = TeamMember(
        team_id=invite.team_id,
        user_id=current_user.id,
        role=invite.role,
        invited_by=invite.invited_by,
    )
    db.add(member)

    invite.status = "accepted"
    invite.accepted_at = datetime.now(timezone.utc)
    await db.commit()

    team = await _get_team_or_404(invite.team_id, db)
    logger.info(
        "%s accepted invite to team '%s' (role=%s)",
        current_user.email, team.name, invite.role,
    )

    return {"detail": f"You've joined team '{team.name}' as {invite.role}."}


# ── POST /api/teams/invites/{token}/decline — Decline invitation ────

@router.post("/invites/{token}/decline")
async def decline_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Decline a team invitation."""
    result = await db.execute(
        select(TeamInvite).where(
            TeamInvite.token == token,
            TeamInvite.status == "pending",
        )
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found or already used.")

    if invite.email != current_user.email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your invitation.")

    invite.status = "revoked"
    await db.commit()

    return {"detail": "Invitation declined."}


# ── PATCH /api/teams/{id}/members/{user_id} — Change role ───────────

@router.patch("/{team_id}/members/{user_id}")
async def update_member_role(
    team_id: str,
    user_id: str,
    body: UpdateMemberRoleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change a member's role. Requires owner or admin role."""
    team = await _get_team_or_404(team_id, db)
    requester = await _require_team_role(team_id, current_user.id, db, frozenset({"owner", "admin"}))

    # Can't change owner's role
    if user_id == team.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change the owner's role.",
        )

    # Admins can't change other admins' roles — only owner can
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    target_member = result.scalar_one_or_none()
    if not target_member:
        raise HTTPException(status_code=404, detail="Member not found.")

    if target_member.role == "admin" and requester.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the team owner can change an admin's role.",
        )

    target_member.role = body.role
    await db.commit()

    return {"detail": f"Role updated to {body.role}."}


# ── DELETE /api/teams/{id}/members/{user_id} — Remove member ────────

@router.delete("/{team_id}/members/{user_id}")
async def remove_member(
    team_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from the team. Owner/admin, or the member themselves (leave)."""
    team = await _get_team_or_404(team_id, db)

    # Owner can't be removed
    if user_id == team.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The team owner cannot be removed. Transfer ownership first or delete the team.",
        )

    # Self-removal (leaving) is always allowed
    is_self = user_id == current_user.id

    if not is_self:
        # Must be owner or admin to remove others
        await _require_team_role(team_id, current_user.id, db, frozenset({"owner", "admin"}))

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")

    await db.delete(member)
    await db.commit()

    action = "left" if is_self else "removed"
    logger.info("User %s %s team '%s'", user_id, action, team.name)

    return {"detail": f"Member {action} from team."}


# ── GET /api/teams/{id}/activity — Team video activity ──────────────

@router.get("/{team_id}/activity", response_model=list[TeamActivityItem])
async def team_activity(
    team_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recent video activity from all team members."""
    team = await _get_team_or_404(team_id, db)

    # Verify membership
    membership = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == current_user.id,
        )
    )
    if not membership.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Team not found.")

    # Get all member user IDs
    member_ids_stmt = (
        select(TeamMember.user_id).where(TeamMember.team_id == team_id)
    )
    member_ids = (await db.execute(member_ids_stmt)).scalars().all()

    # Fetch recent videos from all members
    videos_stmt = (
        select(VideoRecord, User)
        .join(User, VideoRecord.user_id == User.id)
        .where(VideoRecord.user_id.in_(member_ids))
        .order_by(VideoRecord.created_at.desc())
        .limit(50)
    )
    rows = (await db.execute(videos_stmt)).all()

    return [
        TeamActivityItem(
            video_id=video.id,
            topic=video.topic,
            title=video.title,
            status=video.status,
            created_by_email=user.email,
            created_at=video.created_at.isoformat() if video.created_at else "",
        )
        for video, user in rows
    ]
