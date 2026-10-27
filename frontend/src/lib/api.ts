// Default "/api" routes through Vercel proxy functions (no CORS issues).
// For local dev, use the Settings panel to set e.g. http://127.0.0.1:8000
export const DEFAULT_API_BASE = "/api";

export function getApiBase(): string {
  if (typeof localStorage !== "undefined") {
    return localStorage.getItem("tt_api_base") ?? DEFAULT_API_BASE;
  }
  return DEFAULT_API_BASE;
}

export function setApiBase(url: string): void {
  localStorage.setItem("tt_api_base", url);
}

// ─── Response types ────────────────────────────────────────────────────────────

export type PageContent = { url: string; title: string; description: string };

export type AnalyzeResp = {
  page_contents: PageContent[];
  keywords: string[];
};

export type VideoStats = {
  likes: number;
  comments: number;
  shares: number;
  plays: number;
  favorites: number;
};

export type Video = {
  id: string;
  tiktok_url: string;
  desc: string;
  cover: string;
  author_name: string;
  author_uniqueId: string;
  author_avatar: string;
  author_followers: number;
  author_total_likes: number;
  stats: VideoStats;
  hashtags?: string[];
  createTime?: number | null; // Unix seconds
  ai_reason?: string | null;
};

export type Author = {
  author_name: string;
  author_uniqueId: string;
  author_avatar: string;
  followers: number;
  total_likes: number;
  top_likes: number;
  ai_reason?: string | null;
};

export type SearchResp = {
  keywords: string[];
  ai_summary?: string | null;
  ai_warning?: string;
  videos_count: number;
  videos: Video[];
  top_authors_count: number;
  top_authors: Author[];
  from_cache?: boolean;
};

export type ChannelProfile = {
  unique_id: string;
  nickname: string;
  signature: string;
  verified: boolean;
  avatar: string;
  bio_link: string | null;
  followers: number;
  following: number;
  total_likes: number;
  video_count: number;
};

export type ChannelMetrics = {
  videos_analyzed: number;
  avg_plays?: number;
  median_plays?: number;
  max_plays?: number;
  avg_likes?: number;
  avg_engagement_rate_percent?: number | null;
  posts_per_week?: number | null;
  latest_post_date?: string | null;
  days_since_last_post?: number | null;
  top_hashtags?: { tag: string; count: number }[];
};

export type ChannelAiAnalysis = {
  summary: string;
  content_themes: string[];
  posting_behavior: string;
  performance: string;
  audience: string;
  strengths: string[];
  concerns: string[];
  brand_fit: string;
  brand_fit_score: number;
  collaboration_ideas: string[];
};

export type ChannelResp = {
  unique_id: string;
  profile_url: string;
  profile: ChannelProfile;
  metrics: ChannelMetrics;
  ai_analysis: ChannelAiAnalysis | null;
  ai_warning?: string;
  videos: Video[];
  from_cache?: boolean;
};

// ─── API functions ─────────────────────────────────────────────────────────────

export async function analyzeUrls(
  urls: string[],
  numKeywords = 5,
  apiBase = getApiBase(),
): Promise<AnalyzeResp> {
  const qs = urls.map((u) => `url=${encodeURIComponent(u)}`).join("&");
  const r = await fetch(`${apiBase}/analyze?${qs}&num_keywords=${numKeywords}`);
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${r.status}`);
  }
  return r.json() as Promise<AnalyzeResp>;
}

export async function searchTikTok(
  keywords: string[],
  topN = 10,
  apiBase = getApiBase(),
): Promise<SearchResp> {
  const qs = keywords.map((k) => `keyword=${encodeURIComponent(k)}`).join("&");
  const r = await fetch(`${apiBase}/search?${qs}&top_n=${topN}`);
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${r.status}`);
  }
  return r.json() as Promise<SearchResp>;
}

export async function analyzeChannel(
  uniqueId: string,
  context?: string,
  maxVideos = 20,
  apiBase = getApiBase(),
): Promise<ChannelResp> {
  const params = new URLSearchParams({ unique_id: uniqueId, max_videos: String(maxVideos) });
  if (context) params.set("context", context);
  const r = await fetch(`${apiBase}/channel?${params}`);
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${r.status}`);
  }
  return r.json() as Promise<ChannelResp>;
}
