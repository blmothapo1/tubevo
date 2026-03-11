import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import api from '../lib/api';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import { FadeIn } from '../components/Motion';
import {
  BarChart3, TrendingUp, Eye, ThumbsUp, MessageCircle,
  Target, Lightbulb, Award, ArrowUpRight, ArrowDownRight,
  RefreshCw, ChevronDown, ExternalLink, Sparkles,
  MousePointerClick, Clock,
} from 'lucide-react';

/* ── Animated number ── */
function AnimNum({ value, suffix = '' }) {
  return (
    <motion.span
      key={value}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      {typeof value === 'number' ? value.toLocaleString() : value}{suffix}
    </motion.span>
  );
}

/* ── Mini sparkline (pure CSS) ── */
function MiniBar({ data, color = 'bg-brand-500', height = 32 }) {
  if (!data || data.length === 0) return null;
  const max = Math.max(...data, 1);
  return (
    <div className="flex items-end gap-[2px]" style={{ height }}>
      {data.slice(-14).map((v, i) => (
        <div
          key={i}
          className={`${color} rounded-[2px] opacity-70 min-w-[3px] flex-1 transition-all duration-300`}
          style={{ height: `${Math.max(2, (v / max) * 100)}%` }}
        />
      ))}
    </div>
  );
}

/* ── Stat card ── */
function StatCard({ icon: Icon, iconColor, gradient, label, value, suffix, sub, sparkData, sparkColor, delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay, ease: [0.25, 0.1, 0.25, 1] }}
      className="card p-5 max-sm:p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <div className={`w-9 h-9 rounded-[10px] bg-gradient-to-br ${gradient} flex items-center justify-center`}>
          <Icon size={17} className={iconColor} />
        </div>
        {sparkData && <MiniBar data={sparkData} color={sparkColor || 'bg-brand-400'} />}
      </div>
      <p className="text-[24px] sm:text-[28px] font-bold text-white tabular-nums tracking-tight leading-none mb-1">
        <AnimNum value={value} suffix={suffix} />
      </p>
      <p className="text-[13px] font-medium text-surface-800">{label}</p>
      {sub && <p className="text-[11px] text-surface-500 mt-0.5">{sub}</p>}
    </motion.div>
  );
}

/* ── Engagement gauge ── */
function EngagementGauge({ score, label }) {
  const pct = Math.min(100, Math.max(0, score));
  const color = pct >= 70 ? 'bg-emerald-500' : pct >= 40 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[12px] text-surface-600 font-medium">{label}</span>
        <span className="text-[13px] font-semibold text-white tabular-nums">{Math.round(score)}</span>
      </div>
      <div className="w-full bg-surface-300/50 rounded-full h-[5px] overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: [0.25, 0.1, 0.25, 1], delay: 0.3 }}
          className={`h-[5px] rounded-full ${color}`}
        />
      </div>
    </div>
  );
}

/* ── Recommendation card ── */
function RecommendationCard({ rec, index }) {
  const icons = {
    title_style: Lightbulb,
    thumbnail: Target,
    hook: Sparkles,
    general: TrendingUp,
  };
  const Icon = icons[rec.category] || Lightbulb;
  const confidenceColors = {
    high: 'text-emerald-400 bg-emerald-500/10',
    medium: 'text-amber-400 bg-amber-500/10',
    low: 'text-surface-600 bg-surface-300/30',
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.1 + index * 0.05, duration: 0.25 }}
      className="flex gap-3 p-4 rounded-[10px] bg-white/[0.02] hover:bg-white/[0.04] transition-colors duration-150"
    >
      <div className="w-8 h-8 rounded-[8px] bg-brand-500/10 flex items-center justify-center shrink-0 mt-0.5">
        <Icon size={15} className="text-brand-400" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <p className="text-[13px] font-semibold text-white">{rec.label}</p>
          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${confidenceColors[rec.confidence] || confidenceColors.low}`}>
            {rec.confidence}
          </span>
        </div>
        <p className="text-[12px] text-surface-600 leading-relaxed">{rec.detail}</p>
      </div>
    </motion.div>
  );
}

/* ── Style breakdown row ── */
function StyleRow({ stat, best }) {
  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-medium text-surface-900 capitalize">
            {stat.name.replace(/_/g, ' ')}
          </span>
          {best && (
            <span className="text-[9px] font-semibold text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded-full">
              BEST
            </span>
          )}
        </div>
        <span className="text-[11px] text-surface-500">{stat.count} video{stat.count !== 1 ? 's' : ''}</span>
      </div>
      <div className="text-right">
        <p className="text-[14px] font-semibold text-white tabular-nums">{stat.avg_engagement}</p>
        <p className="text-[10px] text-surface-500">avg score</p>
      </div>
      <div className="w-16">
        <div className="w-full bg-surface-300/30 rounded-full h-[4px] overflow-hidden">
          <div
            className={`h-[4px] rounded-full ${best ? 'bg-emerald-500' : 'bg-brand-500/60'}`}
            style={{ width: `${Math.min(100, stat.avg_engagement)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

/* ── Top video row ── */
function TopVideoRow({ video, rank }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.05 * rank, duration: 0.2 }}
      className="flex items-center gap-3 sm:gap-4 px-4 sm:px-5 py-3 hover:bg-white/[0.02] transition-colors duration-150"
    >
      <div className="w-7 h-7 rounded-[8px] bg-surface-200 flex items-center justify-center shrink-0">
        <span className="text-[12px] font-bold text-surface-700 tabular-nums">#{rank}</span>
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-medium text-surface-900 truncate">{video.title}</p>
        <div className="flex items-center gap-3 mt-0.5">
          <span className="text-[11px] text-surface-500 flex items-center gap-1">
            <Eye size={10} /> {video.views.toLocaleString()}
          </span>
          <span className="text-[11px] text-surface-500 flex items-center gap-1">
            <ThumbsUp size={10} /> {video.likes.toLocaleString()}
          </span>
          {video.ctr != null && (
            <span className="text-[11px] text-surface-500 flex items-center gap-1">
              <MousePointerClick size={10} /> {video.ctr}%
            </span>
          )}
          {video.retention != null && (
            <span className="text-[11px] text-surface-500 flex items-center gap-1">
              <Clock size={10} /> {video.retention}%
            </span>
          )}
        </div>
      </div>
      <div className="text-right shrink-0">
        <p className="text-[16px] font-bold text-white tabular-nums">{video.engagement_score}</p>
        <p className="text-[10px] text-surface-500">score</p>
      </div>
      {video.youtube_url && (
        <a href={video.youtube_url} target="_blank" rel="noopener noreferrer"
          className="p-1.5 rounded-[6px] hover:bg-white/[0.06] text-surface-500 hover:text-brand-400 transition-colors">
          <ExternalLink size={13} />
        </a>
      )}
    </motion.div>
  );
}


/* ═══════════════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════════════════════════════ */

export default function Insights() {
  const [overview, setOverview] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [topVideos, setTopVideos] = useState([]);
  const [styles, setStyles] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [dataPoints, setDataPoints] = useState(0);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [ovRes, tlRes, tvRes, stRes, recRes] = await Promise.allSettled([
        api.get(`/api/insights/overview?days=${days}`),
        api.get(`/api/insights/timeline?days=${days}`),
        api.get('/api/insights/top-videos?limit=10'),
        api.get(`/api/insights/style-analysis?days=${days}`),
        api.get('/api/insights/recommendations'),
      ]);

      if (ovRes.status === 'fulfilled') setOverview(ovRes.value.data);
      if (tlRes.status === 'fulfilled') setTimeline(tlRes.value.data.timeline || []);
      if (tvRes.status === 'fulfilled') setTopVideos(tvRes.value.data.videos || []);
      if (stRes.status === 'fulfilled') setStyles(stRes.value.data);
      if (recRes.status === 'fulfilled') {
        setRecommendations(recRes.value.data.recommendations || []);
        setDataPoints(recRes.value.data.data_points || 0);
      }
    } catch {
      // gracefully show empty state
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const viewsData = timeline.map(t => t.views);
  const likesData = timeline.map(t => t.likes);
  const engData = timeline.map(t => t.avg_engagement);

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto space-y-5">
        <div className="space-y-2"><div className="skeleton h-7 w-64" /><div className="skeleton h-3 w-48" /></div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => <div key={i} className="skeleton h-28" />)}
        </div>
        <div className="skeleton h-64" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div className="skeleton h-48" />
          <div className="skeleton h-48" />
        </div>
      </div>
    );
  }

  const hasData = overview && overview.videos_with_metrics > 0;

  return (
    <div className="max-w-6xl mx-auto space-y-6 min-w-0 overflow-hidden">
      <PageHeader
        title="Performance Insights"
        subtitle="Learn what's working"
        action={
          <div className="flex items-center gap-2">
            {/* Period selector */}
            <div className="relative">
              <select
                value={days}
                onChange={e => setDays(Number(e.target.value))}
                className="appearance-none bg-surface-200/60 text-[12px] text-surface-800 font-medium pl-3 pr-7 py-1.5 rounded-[8px] border border-white/[0.04] hover:border-white/[0.08] transition-colors cursor-pointer"
              >
                <option value={7}>7 days</option>
                <option value={14}>14 days</option>
                <option value={30}>30 days</option>
                <option value={60}>60 days</option>
                <option value={90}>90 days</option>
              </select>
              <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-surface-600 pointer-events-none" />
            </div>
            <motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
              onClick={fetchAll}
              className="p-2 rounded-[8px] text-surface-600 hover:text-surface-800 hover:bg-white/[0.04] transition-colors"
              title="Refresh">
              <RefreshCw size={16} />
            </motion.button>
          </div>
        }
      />

      {!hasData ? (
        <EmptyState
          icon={BarChart3}
          title="No analytics data yet"
          description="Once your published videos are 24–72 hours old, Tubevo automatically fetches their YouTube performance. Check back after your first video has been live for a day."
        />
      ) : (
        <>
          {/* ── Hero stats grid ── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              icon={Eye} iconColor="text-indigo-400"
              gradient="from-indigo-500/15 to-indigo-500/5"
              label="Total Views" value={overview.total_views}
              sub={`${overview.posted_videos} videos posted`}
              sparkData={viewsData} sparkColor="bg-indigo-400"
              delay={0.05}
            />
            <StatCard
              icon={ThumbsUp} iconColor="text-emerald-400"
              gradient="from-emerald-500/15 to-emerald-500/5"
              label="Total Likes" value={overview.total_likes}
              sub={overview.total_views > 0 ? `${((overview.total_likes / overview.total_views) * 100).toFixed(1)}% ratio` : ''}
              sparkData={likesData} sparkColor="bg-emerald-400"
              delay={0.1}
            />
            <StatCard
              icon={Target} iconColor="text-amber-400"
              gradient="from-amber-500/15 to-amber-500/5"
              label="Avg Engagement" value={overview.avg_engagement_score} suffix="/100"
              sub={`Best: ${overview.best_engagement_score}`}
              sparkData={engData} sparkColor="bg-amber-400"
              delay={0.15}
            />
            <StatCard
              icon={MousePointerClick} iconColor="text-rose-400"
              gradient="from-rose-500/15 to-rose-500/5"
              label="Avg CTR" value={overview.avg_ctr != null ? overview.avg_ctr : '—'} suffix={overview.avg_ctr != null ? '%' : ''}
              sub={overview.avg_retention != null ? `${overview.avg_retention}% avg retention` : 'Analytics scope needed'}
              delay={0.2}
            />
          </div>

          {/* ── Two-column layout ── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

            {/* ── Recommendations ── */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.25 }}
              className="card p-5 max-sm:p-4"
            >
              <div className="flex items-center gap-2 mb-4">
                <Lightbulb size={14} className="text-brand-400" />
                <h2 className="text-[12px] font-semibold text-surface-600 uppercase tracking-[0.08em]">
                  Recommendations
                </h2>
                <span className="text-[10px] text-surface-500 ml-auto">{dataPoints} data points</span>
              </div>
              {recommendations.length === 0 ? (
                <p className="text-[12px] text-surface-500 text-center py-6">
                  Publish more videos to unlock personalized recommendations.
                </p>
              ) : (
                <div className="space-y-2">
                  {recommendations.map((rec, i) => (
                    <RecommendationCard key={i} rec={rec} index={i} />
                  ))}
                </div>
              )}
            </motion.div>

            {/* ── Style Analysis ── */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }}
              className="card p-5 max-sm:p-4"
            >
              <div className="flex items-center gap-2 mb-4">
                <Award size={14} className="text-emerald-400" />
                <h2 className="text-[12px] font-semibold text-surface-600 uppercase tracking-[0.08em]">
                  Style Performance
                </h2>
              </div>

              {styles && styles.title_styles.length > 0 ? (
                <div className="space-y-5">
                  {/* Title styles */}
                  <div>
                    <p className="text-[11px] text-surface-500 font-medium uppercase tracking-wider mb-2">Title Styles</p>
                    <div className="divide-y divide-white/[0.04]">
                      {styles.title_styles.map((s, i) => (
                        <StyleRow key={s.name} stat={s} best={i === 0} />
                      ))}
                    </div>
                  </div>

                  {/* Thumbnail styles */}
                  {styles.thumbnail_styles.length > 0 && (
                    <div>
                      <p className="text-[11px] text-surface-500 font-medium uppercase tracking-wider mb-2">Thumbnail Concepts</p>
                      <div className="divide-y divide-white/[0.04]">
                        {styles.thumbnail_styles.map((s, i) => (
                          <StyleRow key={s.name} stat={s} best={i === 0} />
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Hook modes */}
                  {styles.hook_modes.length > 0 && (
                    <div>
                      <p className="text-[11px] text-surface-500 font-medium uppercase tracking-wider mb-2">Hook Intensity</p>
                      <div className="divide-y divide-white/[0.04]">
                        {styles.hook_modes.map((s, i) => (
                          <StyleRow key={s.name} stat={s} best={i === 0} />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-[12px] text-surface-500 text-center py-6">
                  Style data will appear after videos are analyzed.
                </p>
              )}
            </motion.div>
          </div>

          {/* ── Top Videos ── */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.35 }}
          >
            <div className="flex items-center gap-2 mb-3">
              <BarChart3 size={14} className="text-surface-600" />
              <h2 className="text-[12px] font-semibold text-surface-600 uppercase tracking-[0.08em]">
                Top Performing Videos
              </h2>
            </div>
            {topVideos.length > 0 ? (
              <div className="card overflow-hidden divide-y divide-white/[0.04]">
                {topVideos.map((video, i) => (
                  <TopVideoRow key={video.id} video={video} rank={i + 1} />
                ))}
              </div>
            ) : (
              <div className="card p-6 text-center">
                <p className="text-[12px] text-surface-500">
                  Top video rankings will appear once analytics data is collected.
                </p>
              </div>
            )}
          </motion.div>

          {/* ── Engagement overview ── */}
          {(overview.avg_ctr != null || overview.avg_retention != null) && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.4 }}
              className="card p-5 max-sm:p-4"
            >
              <h2 className="text-[12px] font-semibold text-surface-600 uppercase tracking-[0.08em] mb-4">
                Engagement Breakdown
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <EngagementGauge score={overview.avg_engagement_score} label="Avg Engagement Score" />
                {overview.avg_ctr != null && (
                  <EngagementGauge score={overview.avg_ctr * 10} label={`Click-Through Rate (${overview.avg_ctr}%)`} />
                )}
                {overview.avg_retention != null && (
                  <EngagementGauge score={overview.avg_retention} label={`Avg View Duration (${overview.avg_retention}%)`} />
                )}
                {overview.total_views > 0 && (
                  <EngagementGauge
                    score={Math.min(100, (overview.total_likes / overview.total_views) * 100 * 12.5)}
                    label={`Like Ratio (${((overview.total_likes / overview.total_views) * 100).toFixed(1)}%)`}
                  />
                )}
              </div>
            </motion.div>
          )}
        </>
      )}
    </div>
  );
}
