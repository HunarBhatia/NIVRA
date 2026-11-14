// Shared types for the Nivra website.
// Case/link shapes mirror the backend API (backend/app/schemas.py).

/** What kind of harm the case is about (decision D1). */
export type Category = "intimate" | "morphed" | "impersonation";

/** Lifecycle of a single link (blueprint 10.5). The server enforces the rules. */
export type LinkStatus =
  | "found" // added, nothing sent yet
  | "reported" // user sent the notice, waiting for a reply
  | "removed" // platform took it down
  | "rejected" // platform refused
  | "escalated" // user moved to the next step on the ladder
  | "reappeared"; // was removed, came back

export interface StatusEvent {
  at: string; // ISO timestamp (UTC)
  status: LinkStatus;
  note: string | null;
}

export interface CaseLink {
  id: string;
  url: string;
  host: string;
  status: LinkStatus;
  reported_at: string | null;
  /** Prototype-only: lets testers pretend time has passed. */
  deadline_override: boolean;
  events: StatusEvent[];
}

export interface NivraCase {
  id: string;
  category: Category;
  self_taken: boolean | null;
  display_name: string;
  created_at: string;
  links: CaseLink[];
}

export interface CaseSummary {
  id: string;
  category: Category;
  created_at: string;
  link_count: number;
}

export interface Account {
  account_code: string; // the Nivra ID, e.g. NV-7K3Q-92XD
  has_email: boolean;
  created_at: string;
}

export interface ReportChannel {
  label: string;
  kind: "form" | "email" | "in-app";
  target?: string; // URL or email address
}

export interface Platform {
  id: string;
  name: string;
  owner?: string;
  domains: string[];
  /** Hours the platform has under India's IT Rules 2021 (24h for intimate content). */
  expectedHours: number;
  channels: ReportChannel[];
  inAppSteps?: string[];
  notes?: string;
}

// ---------- Protected images (phase 3) ----------

export interface ProtectedImage {
  id: string;
  label: string;
  status: "active" | "paused";
  consent_version: string;
  created_at: string;
  fingerprints: { kind: "sha256" | "phash" | "embedding"; algorithm: string; created_at: string }[];
}

export type MatchClass = "exact" | "high" | "possible" | "none";

export interface MatchResult {
  image_id: string;
  label: string;
  classification: MatchClass;
  sha256_equal: boolean;
  phash_distance: number | null;
  cosine: number | null;
}

export interface MatchCheck {
  results: MatchResult[];
  thresholds: Record<string, number>;
}

// ---------- Discovery (phase 4) ----------

export interface DiscoveryJob {
  id: string;
  provider: string;
  input_url: string;
  status: "queued" | "running" | "done" | "failed";
  error_message: string | null;
  page_title: string | null;
  candidates_found: number;
  candidates_checked: number;
  candidates_skipped: number;
  matches_found: number;
  created_at: string;
  finished_at: string | null;
}

export interface DiscoveredMatch {
  id: string;
  image_id: string;
  image_label: string;
  provider: string;
  source_page_url: string;
  candidate_image_url: string;
  classification: "exact" | "high" | "possible";
  sha256_equal: boolean;
  phash_distance: number | null;
  cosine: number | null;
  status: "pending" | "confirmed" | "rejected";
  case_link_id: string | null;
  discovered_at: string;
  reviewed_at: string | null;
}

// ---------- AI agents (phase 5) ----------

export interface AgentStatus {
  llm_available: boolean;
  llm_provider: string;
  model: string | null;
  runtime: string;
}

export interface DraftText {
  subject: string;
  body: string;
}

export interface AgentRun {
  id: string;
  agent: "complaint" | "verification" | "follow_up" | "discovery";
  status: "running" | "awaiting_approval" | "completed" | "rejected" | "failed";
  subject_id: string | null;
  used_llm: boolean;
  llm_provider: string;
  error_code: string | null;
  created_at: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- shape depends on the agent
  output: Record<string, any>;
  preview?: DraftText;
  previews?: (DraftText & { id: string; link_id: string; kind: string; source: string })[];
}
