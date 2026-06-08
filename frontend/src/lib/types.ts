export type Identity = "working_switch" | "fresh_grad" | "intern";

export interface SearchProfile {
  identity: Identity;
  directions: string[];
  target_companies: string[];
  regions: string[];
  custom_needs?: string;
}

export interface FeedItem {
  id?: string;
  source_document_id?: string;
  source: string;
  source_url: string;
  title?: string | null;
  snippet?: string | null;
  company?: string | null;
  position?: string | null;
  published_at?: string | null;
  relevance_score?: number | null;
  final_score?: number | null;
  trust_label?: string | null;
  has_full_text?: boolean;
  tags?: string[];
  question_count?: number;
  evidence_coverage?: number;
  fetch_policy?: string;
}

export interface QualityReport {
  filteredCount?: number;
  duplicateCount?: number;
  hookWarnings?: string[];
  evidenceCoverageAvg?: number | null;
  fetchedCount?: number;
}

export interface FeedSearchResponse {
  sessionId: string;
  status: string;
  items: FeedItem[];
  total: number;
  sourcesStatus: Record<string, string>;
  cachedCount?: number;
  freshCount?: number;
  searchDuration: number;
  qualityReport?: QualityReport | null;
  error?: string | null;
}

// ── SSE Stream Types ──

export type AgentPhase = "planning" | "searching" | "fetching" | "extracting" | "ranking";

export type AgentStatus = "idle" | "running" | "done" | "error" | "timeout" | "blocked";

export interface AgentState {
  id: string;
  displayName: string;
  phase: AgentPhase;
  status: AgentStatus;
  query?: string;
  progress?: string;
  resultCount?: number;
  durationMs?: number;
  errorMessage?: string;
}

export type ActivityLogLevel = "info" | "success" | "warning" | "error";

export interface ActivityLogEntry {
  id: string;
  message: string;
  level: ActivityLogLevel;
  timestamp: number;
  durationMs?: number;
}

export interface StreamEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface StreamCallbacks {
  onSessionCreated?: (sessionId: string) => void;
  onPhaseStart?: (phase: AgentPhase, data: Record<string, unknown>) => void;
  onPhaseCompleted?: (phase: AgentPhase, data: Record<string, unknown>) => void;
  onQueryPlanReady?: (data: Record<string, unknown>) => void;
  onSearchStarted?: (source: string, data: Record<string, unknown>) => void;
  onSourceResults?: (source: string, items: FeedItem[]) => void;
  onSourceCompleted?: (source: string, data: Record<string, unknown>) => void;
  onSourceError?: (source: string, error: string) => void;
  onSourceTimeout?: (source: string, timeoutS: number) => void;
  onRankingCompleted?: (data: Record<string, unknown>) => void;
  onFetchCompleted?: (data: Record<string, unknown>) => void;
  onExtractCompleted?: (data: Record<string, unknown>) => void;
  onSearchCompleted?: (data: Record<string, unknown>) => void;
  onFetchStarted?: (data: Record<string, unknown>) => void;
  onSearchError?: (error: string) => void;
  onSearchBlocked?: (reason: string) => void;
  onActivityLog?: (entry: ActivityLogEntry) => void;
  onEnhanceStart?: (data: Record<string, unknown>) => void;
  onEnhanceProgress?: (data: Record<string, unknown>) => void;
  onEnhanceCompleted?: (data: Record<string, unknown>) => void;
  onLlmStart?: (docId: string, docTitle: string) => void;
  onLlmChunk?: (docId: string, token: string) => void;
  onLlmSummary?: (docId: string, summary: string, questionCount: number) => void;
  onStreamEnd?: () => void;
}

// ── Other types ──

export interface SearchSessionResponse {
  id: string;
  status: string;
  profileSnapshot?: SearchProfile | null;
  queryPlan?: unknown;
  sourceStatus?: Record<string, string> | null;
  toolRuns?: Array<Record<string, unknown>>;
  qualityReport?: QualityReport | null;
  createdAt?: string | null;
}

export interface QuestionEvidence {
  quote: string;
  confidence?: number;
  sourceUrl?: string;
}

export interface InterviewQuestion {
  id: string;
  text: string;
  category?: string | null;
  difficulty?: number | null;
  sourceType?: string | null;
  confidence?: number | null;
  evidence?: QuestionEvidence | null;
  followUps?: string[];
  tags?: string[];
}

export interface InterviewEvent {
  id: string;
  company?: string | null;
  position?: string | null;
  candidateType?: string | null;
  round?: string | null;
  region?: string | null;
  summary?: string | null;
  difficulty?: number | null;
  evidenceCoverage?: number | null;
  tags?: string[];
  questions: InterviewQuestion[];
}

export interface FeedDetailResponse {
  id: string;
  source: string;
  sourceUrl: string;
  title?: string | null;
  snippet?: string | null;
  extractionStatus?: string | null;
  extractionConfidence?: number | null;
  fetchedAt?: string | null;
  structured: {
    events: InterviewEvent[];
  };
}

export interface HighFreqQuestion {
  text: string;
  category?: string | null;
  frequency: number;
  avgDifficulty?: number | null;
  tags?: string[];
  sourceType?: string;
}

export interface CompanyProfile {
  company: string;
  position?: string | null;
  candidateType?: string | null;
  sufficient_data?: boolean;
  eventCount?: number;
  questionCount?: number;
  sampleCount?: number;
  avgDifficulty?: number | null;
  difficultyAvg?: number | null;
  categoryDistribution?: Record<string, number>;
  highFreqQuestions?: HighFreqQuestion[];
  topQuestions?: Array<{ text: string; frequency: number }>;
  topTags?: string[];
  sourcesDistribution?: Record<string, number>;
  styleSummary?: string | null;
  evidenceCoverageAvg?: number | null;
  message?: string;
}

export interface ApiError {
  message: string;
  status?: number;
}
