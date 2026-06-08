import type {
  ApiError,
  CompanyProfile,
  FeedDetailResponse,
  FeedItem,
  FeedSearchResponse,
  SearchProfile,
  SearchSessionResponse,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

class ApiClientError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail ?? body.message ?? message;
      if (typeof message !== "string") {
        message = JSON.stringify(message);
      }
    } catch {
      // ignore parse errors
    }
    throw new ApiClientError(message, response.status);
  }

  return response.json() as Promise<T>;
}

function normalizeFeedItem(raw: Record<string, unknown>): FeedItem {
  return {
    id: (raw.id ?? raw.source_document_id) as string | undefined,
    source_document_id: raw.source_document_id as string | undefined,
    source: String(raw.source ?? ""),
    source_url: String(raw.source_url ?? raw.sourceUrl ?? ""),
    title: (raw.title as string) ?? null,
    snippet: (raw.snippet as string) ?? null,
    company: (raw.company as string) ?? null,
    position: (raw.position as string) ?? null,
    published_at: (raw.published_at ?? raw.publishedAt) as string | null,
    relevance_score: (raw.relevance_score ?? raw.relevanceScore) as
      | number
      | null,
    final_score: (raw.final_score ?? raw.finalScore) as number | null,
    trust_label: (raw.trust_label ?? raw.trustLabel) as string | null,
    has_full_text: Boolean(raw.has_full_text ?? raw.hasFullText),
    tags: (raw.tags as string[]) ?? [],
  };
}

function normalizeSearchResponse(
  raw: Record<string, unknown>
): FeedSearchResponse {
  const items = Array.isArray(raw.items)
    ? raw.items.map((item) =>
        normalizeFeedItem(item as Record<string, unknown>)
      )
    : [];

  return {
    sessionId: String(raw.sessionId ?? raw.session_id ?? ""),
    status: String(raw.status ?? "unknown"),
    items,
    total: Number(raw.total ?? items.length),
    sourcesStatus: (raw.sourcesStatus ??
      raw.sources_status ??
      {}) as Record<string, string>,
    cachedCount: Number(raw.cachedCount ?? raw.cached_count ?? 0),
    freshCount: Number(raw.freshCount ?? raw.fresh_count ?? 0),
    searchDuration: Number(raw.searchDuration ?? raw.search_duration ?? 0),
    qualityReport: (raw.qualityReport ?? raw.quality_report ?? null) as
      | FeedSearchResponse["qualityReport"]
      | null,
    error: (raw.error as string) ?? null,
  };
}

export async function checkHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/health");
}

export async function searchFeed(
  profile: SearchProfile
): Promise<FeedSearchResponse> {
  const body = {
    identity: profile.identity,
    directions: profile.directions,
    target_companies: profile.target_companies,
    regions: profile.regions,
    custom_needs: profile.custom_needs ?? "",
  };

  const raw = await request<Record<string, unknown>>("/api/feed/search", {
    method: "POST",
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(120000),
  });

  return normalizeSearchResponse(raw);
}

export async function getCachedFeed(
  company?: string
): Promise<FeedSearchResponse> {
  const params = new URLSearchParams();
  if (company) params.set("company", company);
  const query = params.toString();

  const raw = await request<Record<string, unknown>>(
    `/api/feed/cached${query ? `?${query}` : ""}`,
    { signal: AbortSignal.timeout(30000) }
  );

  const items = Array.isArray((raw as Record<string, unknown>).items)
    ? ((raw as Record<string, unknown>).items as Record<string, unknown>[]).map(
        normalizeFeedItem
      )
    : [];

  const cachedCount = Number((raw as Record<string, unknown>).cachedCount ?? items.length);
  const totalQuestions = Number((raw as Record<string, unknown>).totalQuestions ?? 0);
  const avgConfidence = (raw as Record<string, unknown>).avgConfidence as number | null;

  return {
    sessionId: "",
    status: "success",
    items,
    total: Number((raw as Record<string, unknown>).total ?? items.length),
    sourcesStatus: { database: "cached" },
    cachedCount,
    freshCount: 0,
    searchDuration: 0,
    qualityReport: {
      filteredCount: 0,
      duplicateCount: 0,
      hookWarnings: [],
      evidenceCoverageAvg: avgConfidence,
      fetchedCount: cachedCount,
    },
    error: null,
  };
}

export async function getFeedDetail(
  sourceDocumentId: string
): Promise<FeedDetailResponse> {
  return request<FeedDetailResponse>(
    `/api/feed/detail/${encodeURIComponent(sourceDocumentId)}`
  );
}

export async function getSearchSession(
  sessionId: string
): Promise<SearchSessionResponse> {
  return request<SearchSessionResponse>(
    `/api/feed/search-sessions/${encodeURIComponent(sessionId)}`
  );
}

export async function getCompanyProfile(
  company: string,
  params?: { position?: string; candidateType?: string }
): Promise<CompanyProfile> {
  const searchParams = new URLSearchParams();
  if (params?.position) searchParams.set("position", params.position);
  if (params?.candidateType)
    searchParams.set("candidateType", params.candidateType);

  const query = searchParams.toString();
  const path = `/api/company-profile/${encodeURIComponent(company)}${
    query ? `?${query}` : ""
  }`;

  return request<CompanyProfile>(path);
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiClientError) {
    return { message: error.message, status: error.status };
  }
  if (error instanceof Error) {
    return { message: error.message };
  }
  return { message: "未知错误" };
}

export { API_BASE };
