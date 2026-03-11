import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../lib/api';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import { FadeIn } from '../components/Motion';
import { useToast } from '../contexts/ToastContext';
import {
  Users, Plus, Mail, Shield, Edit3, Trash2, Crown,
  UserPlus, Copy, Check, Clock, ChevronDown, X,
  Eye, Film, AlertCircle, Settings, UserMinus,
  ExternalLink,
} from 'lucide-react';
import { SkeletonTeamList, SkeletonTeamDetail } from '../components/Skeleton';

/* ── Role badge ── */
const ROLE_STYLES = {
  owner:  'bg-amber-500/15 text-amber-400 border-amber-500/20',
  admin:  'bg-brand-500/15 text-brand-400 border-brand-500/20',
  editor: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  viewer: 'bg-surface-300/20 text-surface-600 border-surface-300/20',
};

function RoleBadge({ role }) {
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border ${ROLE_STYLES[role] || ROLE_STYLES.viewer}`}>
      {role}
    </span>
  );
}

/* ── Member row ── */
function MemberRow({ member, isOwnerOrAdmin, currentUserId, teamId, onRefresh }) {
  const toast = useToast();
  const [roleOpen, setRoleOpen] = useState(false);
  const [removing, setRemoving] = useState(false);

  const changeRole = async (newRole) => {
    setRoleOpen(false);
    try {
      await api.patch(`/api/teams/${teamId}/members/${member.user_id}`, { role: newRole });
      toast.success(`Role updated to ${newRole}`);
      onRefresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to change role');
    }
  };

  const removeMember = async () => {
    if (!confirm(`Remove ${member.email} from team?`)) return;
    setRemoving(true);
    try {
      await api.delete(`/api/teams/${teamId}/members/${member.user_id}`);
      toast.success(`${member.email} removed from team`);
      onRefresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to remove member');
    } finally {
      setRemoving(false);
    }
  };

  const isMe = member.user_id === currentUserId;
  const isOwner = member.role === 'owner';

  return (
    <div className="flex items-center gap-3 px-4 sm:px-5 py-3 hover:bg-white/[0.02] transition-colors duration-150">
      <div className="w-9 h-9 rounded-[10px] bg-brand-500/15 flex items-center justify-center shrink-0">
        {isOwner ? <Crown size={15} className="text-amber-400" /> : <Users size={15} className="text-brand-400" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-[13px] font-medium text-surface-900 truncate">
            {member.full_name || member.email}
          </p>
          {isMe && <span className="text-[9px] font-medium text-brand-400 bg-brand-500/10 px-1.5 py-0.5 rounded-full">YOU</span>}
        </div>
        <p className="text-[11px] text-surface-500 truncate">{member.email}</p>
      </div>
      <RoleBadge role={member.role} />

      {/* Actions (only for admins/owners, not on the owner) */}
      {isOwnerOrAdmin && !isOwner && (
        <div className="flex items-center gap-1 shrink-0 relative">
          {/* Role dropdown */}
          <button
            onClick={() => setRoleOpen(!roleOpen)}
            className="p-1.5 rounded-[6px] text-surface-500 hover:text-brand-400 hover:bg-brand-500/10 transition-colors"
            title="Change role"
          >
            <Edit3 size={14} />
          </button>
          <AnimatePresence>
            {roleOpen && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: -4 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: -4 }}
                className="absolute right-0 top-full mt-1 z-20 bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-[10px] p-1.5 shadow-xl min-w-[120px]"
              >
                {['admin', 'editor', 'viewer'].map((r) => (
                  <button
                    key={r}
                    onClick={() => changeRole(r)}
                    className={`w-full text-left px-3 py-1.5 rounded-[6px] text-[12px] font-medium capitalize transition-colors
                      ${member.role === r ? 'text-brand-400 bg-brand-500/10' : 'text-surface-700 hover:text-white hover:bg-white/[0.04]'}`}
                  >
                    {r}
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>

          <button
            onClick={removeMember}
            disabled={removing}
            className="p-1.5 rounded-[6px] text-surface-500 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40"
            title="Remove member"
          >
            <UserMinus size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Invite row ── */
function InviteRow({ invite, teamId, onRefresh }) {
  const isExpired = new Date(invite.expires_at) < new Date();

  const revoke = async () => {
    try {
      // Use the invites list endpoint to revoke — DELETE the invite via the token
      await api.post(`/api/teams/invites/${invite.token || invite.id}/decline`);
      onRefresh();
    } catch {
      // If decline doesn't work for revoking, just refresh
      onRefresh();
    }
  };

  return (
    <div className="flex items-center gap-3 px-4 sm:px-5 py-3 hover:bg-white/[0.02] transition-colors duration-150">
      <div className="w-9 h-9 rounded-[10px] bg-amber-500/10 flex items-center justify-center shrink-0">
        <Mail size={15} className="text-amber-400" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-medium text-surface-900 truncate">{invite.email}</p>
        <p className="text-[11px] text-surface-500">
          Invited as <span className="capitalize font-medium">{invite.role}</span>
          {' · '}{isExpired ? 'Expired' : `Expires ${new Date(invite.expires_at).toLocaleDateString()}`}
        </p>
      </div>
      <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full
        ${isExpired
          ? 'bg-red-500/10 text-red-400 border border-red-500/20'
          : invite.status === 'accepted'
            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
            : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
        }`}>
        {isExpired ? 'Expired' : invite.status}
      </span>
    </div>
  );
}

/* ── Create team modal ── */
function CreateTeamModal({ open, onClose, onCreated }) {
  const toast = useToast();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError('');
    try {
      await api.post('/api/teams', {
        name: name.trim(),
        description: description.trim() || null,
      });
      setName('');
      setDescription('');
      onClose();
      toast.success('Team created!');
      onCreated();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create team');
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className="relative w-full max-w-md mx-4 bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-[16px] p-6 shadow-2xl"
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-[16px] font-semibold text-white">Create Team</h3>
          <button onClick={onClose} className="p-1 rounded-[6px] text-surface-500 hover:text-white hover:bg-white/[0.04]">
            <X size={16} />
          </button>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-[12px] font-medium text-surface-600 mb-1.5">Team Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Marketing Team"
              className="w-full bg-white/[0.03] border border-[var(--border-subtle)] rounded-[10px] px-3.5 py-2.5 text-[13px] text-white placeholder:text-surface-500 focus:outline-none focus:border-brand-500/50 transition-colors"
              maxLength={200}
              required
              autoFocus
            />
          </div>
          <div>
            <label className="block text-[12px] font-medium text-surface-600 mb-1.5">Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What is this team working on?"
              className="w-full bg-white/[0.03] border border-[var(--border-subtle)] rounded-[10px] px-3.5 py-2.5 text-[13px] text-white placeholder:text-surface-500 focus:outline-none focus:border-brand-500/50 transition-colors resize-none"
              rows={3}
              maxLength={500}
            />
          </div>
          {error && (
            <div className="flex items-center gap-2 text-[12px] text-red-400 bg-red-500/10 px-3 py-2 rounded-[8px]">
              <AlertCircle size={14} /> {error}
            </div>
          )}
          <button
            type="submit"
            disabled={loading || !name.trim()}
            className="w-full h-[42px] rounded-[10px] bg-brand-500 hover:bg-brand-600 text-white text-[13px] font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? 'Creating…' : 'Create Team'}
          </button>
        </form>
      </motion.div>
    </div>
  );
}

/* ── Invite modal ── */
function InviteModal({ open, onClose, teamId, onInvited }) {
  const toast = useToast();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('editor');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);
    setError('');
    try {
      await api.post(`/api/teams/${teamId}/invite`, {
        email: email.trim().toLowerCase(),
        role,
      });
      toast.success(`Invite sent to ${email.trim()}`);
      setEmail('');
      setRole('editor');
      onClose();
      onInvited();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to send invite');
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className="relative w-full max-w-md mx-4 bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-[16px] p-6 shadow-2xl"
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-[16px] font-semibold text-white">Invite Team Member</h3>
          <button onClick={onClose} className="p-1 rounded-[6px] text-surface-500 hover:text-white hover:bg-white/[0.04]">
            <X size={16} />
          </button>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-[12px] font-medium text-surface-600 mb-1.5">Email Address</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="colleague@company.com"
              className="w-full bg-white/[0.03] border border-[var(--border-subtle)] rounded-[10px] px-3.5 py-2.5 text-[13px] text-white placeholder:text-surface-500 focus:outline-none focus:border-brand-500/50 transition-colors"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="block text-[12px] font-medium text-surface-600 mb-1.5">Role</label>
            <div className="grid grid-cols-3 gap-2">
              {['admin', 'editor', 'viewer'].map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRole(r)}
                  className={`py-2 rounded-[8px] text-[12px] font-medium capitalize transition-all border
                    ${role === r
                      ? 'bg-brand-500/15 border-brand-500/30 text-brand-400'
                      : 'bg-white/[0.02] border-[var(--border-subtle)] text-surface-600 hover:text-white hover:bg-white/[0.04]'
                    }`}
                >
                  {r}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-surface-500 mt-1.5">
              {role === 'admin' && 'Can manage members and team settings'}
              {role === 'editor' && 'Can create and edit videos'}
              {role === 'viewer' && 'Can view team videos and analytics'}
            </p>
          </div>
          {error && (
            <div className="flex items-center gap-2 text-[12px] text-red-400 bg-red-500/10 px-3 py-2 rounded-[8px]">
              <AlertCircle size={14} /> {error}
            </div>
          )}
          <button
            type="submit"
            disabled={loading || !email.trim()}
            className="w-full h-[42px] rounded-[10px] bg-brand-500 hover:bg-brand-600 text-white text-[13px] font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? 'Sending…' : 'Send Invite'}
          </button>
        </form>
      </motion.div>
    </div>
  );
}

/* ── Pending invites for the current user ── */
function PendingInvitesBanner({ invites, onAccepted }) {
  const [processing, setProcessing] = useState(null);

  const respond = async (token, action) => {
    setProcessing(token);
    try {
      await api.post(`/api/teams/invites/${token}/${action}`);
      onAccepted();
    } catch (err) {
      alert(err.response?.data?.detail || `Failed to ${action} invite`);
    } finally {
      setProcessing(null);
    }
  };

  if (!invites?.length) return null;

  return (
    <FadeIn delay={0.1}>
      <div className="card p-4 border-l-2 border-l-amber-500/60 mb-6">
        <p className="text-[13px] font-semibold text-white mb-3 flex items-center gap-2">
          <Mail size={15} className="text-amber-400" />
          You have {invites.length} pending team invitation{invites.length !== 1 ? 's' : ''}
        </p>
        <div className="space-y-2">
          {invites.map((inv) => (
            <div key={inv.id} className="flex items-center gap-3 p-3 rounded-[10px] bg-white/[0.02]">
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-medium text-surface-900">{inv.team_name}</p>
                <p className="text-[11px] text-surface-500">
                  Invited by {inv.invited_by_email} · Role: <span className="capitalize">{inv.role}</span>
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => respond(inv.token, 'accept')}
                  disabled={processing === inv.token}
                  className="px-3 py-1.5 rounded-[8px] bg-brand-500 hover:bg-brand-600 text-white text-[11px] font-semibold transition-colors disabled:opacity-40"
                >
                  Accept
                </button>
                <button
                  onClick={() => respond(inv.token, 'decline')}
                  disabled={processing === inv.token}
                  className="px-3 py-1.5 rounded-[8px] bg-white/[0.04] hover:bg-red-500/15 text-surface-600 hover:text-red-400 text-[11px] font-semibold transition-colors disabled:opacity-40"
                >
                  Decline
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </FadeIn>
  );
}

/* ── Team detail view ── */
function TeamDetail({ teamId, userId, onBack, onRefreshList }) {
  const [team, setTeam] = useState(null);
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [tab, setTab] = useState('members');
  const [activity, setActivity] = useState([]);
  const [actLoading, setActLoading] = useState(false);

  const fetchTeam = useCallback(async () => {
    try {
      const { data } = await api.get(`/api/teams/${teamId}`);
      setTeam(data);
    } catch {
      setTeam(null);
    } finally {
      setLoading(false);
    }
  }, [teamId]);

  const fetchActivity = useCallback(async () => {
    setActLoading(true);
    try {
      const { data } = await api.get(`/api/teams/${teamId}/activity`);
      setActivity(data);
    } catch {
      setActivity([]);
    } finally {
      setActLoading(false);
    }
  }, [teamId]);

  useEffect(() => {
    fetchTeam();
  }, [fetchTeam]);

  useEffect(() => {
    if (tab === 'activity') fetchActivity();
  }, [tab, fetchActivity]);

  const myRole = team?.members?.find((m) => m.user_id === userId)?.role;
  const isOwnerOrAdmin = myRole === 'owner' || myRole === 'admin';

  if (loading) {
    return <SkeletonTeamDetail />;
  }

  if (!team) {
    return (
      <EmptyState icon={AlertCircle} title="Team not found" subtitle="This team may have been deleted." />
    );
  }

  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <button onClick={onBack} className="text-[12px] text-surface-500 hover:text-brand-400 transition-colors mb-1 flex items-center gap-1">
            ← Back to teams
          </button>
          <h2 className="text-[20px] font-bold text-white">{team.name}</h2>
          {team.description && <p className="text-[13px] text-surface-600 mt-0.5">{team.description}</p>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <div className="text-[11px] text-surface-500 bg-white/[0.03] px-3 py-1.5 rounded-[8px] border border-[var(--border-subtle)]">
            {team.member_count}/{team.seat_limit} seats
          </div>
          {isOwnerOrAdmin && (
            <button
              onClick={() => setInviteOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-[8px] bg-brand-500 hover:bg-brand-600 text-white text-[12px] font-semibold transition-colors"
            >
              <UserPlus size={14} /> Invite
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 mb-5 p-1 bg-white/[0.02] rounded-[10px] w-fit">
        {['members', 'activity'].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-[8px] text-[12px] font-medium capitalize transition-all
              ${tab === t ? 'bg-brand-500/15 text-brand-400' : 'text-surface-600 hover:text-white'}`}
          >
            {t === 'members' ? `Members (${team.member_count})` : 'Activity'}
          </button>
        ))}
      </div>

      {/* Members tab */}
      {tab === 'members' && (
        <FadeIn>
          <div className="card divide-y divide-[var(--border-subtle)] overflow-hidden">
            {team.members?.map((m) => (
              <MemberRow
                key={m.user_id}
                member={m}
                isOwnerOrAdmin={isOwnerOrAdmin}
                currentUserId={userId}
                teamId={teamId}
                onRefresh={() => { fetchTeam(); onRefreshList(); }}
              />
            ))}
          </div>

          {/* Pending invites count */}
          {team.pending_invites > 0 && (
            <p className="text-[12px] text-surface-500 mt-3 flex items-center gap-1.5">
              <Clock size={13} /> {team.pending_invites} pending invite{team.pending_invites !== 1 ? 's' : ''}
            </p>
          )}
        </FadeIn>
      )}

      {/* Activity tab */}
      {tab === 'activity' && (
        <FadeIn>
          {actLoading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="card p-4 flex items-center gap-3">
                  <div className="skeleton w-8 h-8 rounded-[8px]" />
                  <div className="flex-1 space-y-2">
                    <div className="skeleton h-3.5 w-2/3 rounded-[6px]" />
                    <div className="skeleton h-3 w-1/3 rounded-[6px]" />
                  </div>
                </div>
              ))}
            </div>
          ) : activity.length === 0 ? (
            <EmptyState icon={Film} title="No team activity yet" subtitle="Videos created by team members will show here." />
          ) : (
            <div className="card divide-y divide-[var(--border-subtle)] overflow-hidden">
              {activity.map((v) => (
                <div key={v.video_id} className="flex items-center gap-3 px-4 sm:px-5 py-3 hover:bg-white/[0.02] transition-colors">
                  <div className="w-8 h-8 rounded-[8px] bg-brand-500/10 flex items-center justify-center shrink-0">
                    <Film size={14} className="text-brand-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] font-medium text-surface-900 truncate">{v.title || v.topic}</p>
                    <p className="text-[11px] text-surface-500">{v.created_by_email} · {new Date(v.created_at).toLocaleDateString()}</p>
                  </div>
                  <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full
                    ${v.status === 'published' ? 'bg-emerald-500/10 text-emerald-400' :
                      v.status === 'failed' ? 'bg-red-500/10 text-red-400' :
                      'bg-surface-300/20 text-surface-600'}`}>
                    {v.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </FadeIn>
      )}

      <InviteModal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        teamId={teamId}
        onInvited={() => { fetchTeam(); onRefreshList(); }}
      />
    </>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   MAIN PAGE
   ══════════════════════════════════════════════════════════════════════ */
export default function Team() {
  const [teams, setTeams] = useState([]);
  const [pendingInvites, setPendingInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedTeam, setSelectedTeam] = useState(null);
  const [userId, setUserId] = useState(null);

  const fetchTeams = useCallback(async () => {
    try {
      const { data } = await api.get('/api/teams');
      setTeams(data);
    } catch {
      setTeams([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchPendingInvites = useCallback(async () => {
    try {
      const { data } = await api.get('/api/teams/invites/pending');
      setPendingInvites(data);
    } catch {
      setPendingInvites([]);
    }
  }, []);

  const fetchUserId = useCallback(async () => {
    try {
      const { data } = await api.get('/auth/me');
      setUserId(data.id);
    } catch {}
  }, []);

  useEffect(() => {
    fetchTeams();
    fetchPendingInvites();
    fetchUserId();
  }, [fetchTeams, fetchPendingInvites, fetchUserId]);

  const refreshAll = () => {
    fetchTeams();
    fetchPendingInvites();
  };

  return (
    <div className="max-w-4xl mx-auto">
      <PageHeader
        title="Team"
        subtitle="Collaborate with your team on video production"
        actions={
          !selectedTeam && (
            <button
              onClick={() => setCreateOpen(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-[10px] bg-brand-500 hover:bg-brand-600 text-white text-[13px] font-semibold transition-colors"
            >
              <Plus size={15} /> New Team
            </button>
          )
        }
      />

      {/* Pending invites banner */}
      {!selectedTeam && (
        <PendingInvitesBanner invites={pendingInvites} onAccepted={refreshAll} />
      )}

      {/* Team detail view */}
      {selectedTeam ? (
        <FadeIn>
          <TeamDetail
            teamId={selectedTeam}
            userId={userId}
            onBack={() => setSelectedTeam(null)}
            onRefreshList={fetchTeams}
          />
        </FadeIn>
      ) : loading ? (
        <SkeletonTeamList />
      ) : teams.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No teams yet"
          subtitle="Create a team to collaborate with others on video production. Available on Starter plans and above."
          action={
            <button
              onClick={() => setCreateOpen(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-[10px] bg-brand-500 hover:bg-brand-600 text-white text-[13px] font-semibold transition-colors mx-auto mt-4"
            >
              <Plus size={15} /> Create Your First Team
            </button>
          }
        />
      ) : (
        <FadeIn>
          <div className="grid gap-3">
            {teams.map((t, i) => (
              <motion.button
                key={t.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05, duration: 0.2 }}
                onClick={() => setSelectedTeam(t.id)}
                className="card p-5 text-left hover:border-brand-500/30 transition-all duration-200 group w-full"
              >
                <div className="flex items-center gap-4">
                  <div className="w-11 h-11 rounded-[12px] bg-gradient-to-br from-brand-500/20 to-brand-600/10 flex items-center justify-center shrink-0">
                    <Users size={20} className="text-brand-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <h3 className="text-[15px] font-semibold text-white group-hover:text-brand-400 transition-colors truncate">
                        {t.name}
                      </h3>
                      {t.owner_id === userId && (
                        <span className="text-[9px] font-semibold text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded-full">OWNER</span>
                      )}
                    </div>
                    <p className="text-[12px] text-surface-500">
                      {t.member_count} member{t.member_count !== 1 ? 's' : ''} · {t.seat_limit} seats
                    </p>
                    {t.description && (
                      <p className="text-[11px] text-surface-500 mt-1 truncate">{t.description}</p>
                    )}
                  </div>
                  <ChevronDown size={16} className="text-surface-500 -rotate-90 group-hover:text-brand-400 transition-colors shrink-0" />
                </div>
              </motion.button>
            ))}
          </div>
        </FadeIn>
      )}

      <CreateTeamModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={refreshAll}
      />
    </div>
  );
}
