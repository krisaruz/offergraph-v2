import type { FeedSearchResponse, SearchProfile } from "./types";

const PROFILE_KEY = "offergraph_profile";
const SEARCH_RESULT_KEY = "offergraph_search_result";
const SESSION_ID_KEY = "offergraph_session_id";

export function saveProfile(profile: SearchProfile): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
}

export function getProfile(): SearchProfile | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(PROFILE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SearchProfile;
  } catch {
    return null;
  }
}

export function saveSearchResult(result: FeedSearchResponse): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(SEARCH_RESULT_KEY, JSON.stringify(result));
  sessionStorage.setItem(SESSION_ID_KEY, result.sessionId);
}

export function getSearchResult(): FeedSearchResponse | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(SEARCH_RESULT_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as FeedSearchResponse;
  } catch {
    return null;
  }
}

export function getSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(SESSION_ID_KEY);
}

export function getFeedItemId(item: {
  id?: string;
  source_document_id?: string;
}): string | null {
  return item.id ?? item.source_document_id ?? null;
}
