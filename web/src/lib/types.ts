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
  requiredInfo: string[];
  requiredEvidence: string[];
  /** How the platform tells you what happened (section 18.4). */
  statusTracking: "email" | "in_app" | "ticket" | "none";
  trackingNote?: string;
  /** False until a person has checked the details on the platform's site. */
  verified: boolean;
  lastVerified: string | null;
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

// ---------- Complaints, evidence, overview (phase 6) ----------

export type ComplaintStatus =
  | "draft_generated"
  | "user_approved"
  | "submitted_by_user"
  | "submission_confirmed"
  | "response_received"
  | "resolved"
  | "rejected"
  | "discarded";

export interface Complaint {
  id: string;
  case_id: string;
  link_id: string;
  status: ComplaintStatus;
  status_label: string;
  next_statuses: ComplaintStatus[];
  source: "llm" | "template" | "manual";
  platform_id: string | null;
  platform_name: string | null;
  subject: string;
  body: string;
  reference: string | null;
  channel_kind: string | null;
  channel_label: string | null;
  submitted_at: string | null;
  resolved_at: string | null;
  created_at: string;
  events: { at: string; status: ComplaintStatus; note: string | null }[];
}

export interface TimelineItem {
  at: string;
  type: "link" | "complaint" | "evidence" | "match";
  host: string | null;
  link_id: string | null;
  status: string;
  text: string;
}

export interface Overview {
  protected_images: number;
  active_monitoring: number;
  checks_running: number;
  matches_found: number;
  matches_to_review: number;
  confirmed_incidents: number;
  drafts: number;
  submitted: number;
  pending_responses: number;
  resolved: number;
  links_removed: number;
  approvals_waiting: number;
  cases: { id: string; category: Category; created_at: string; links: number; removed: number }[];
}

export type EvidenceKind = "screenshot" | "file" | "note" | "account" | "message";

export interface EvidenceItemRaw {
  id: string;
  case_id: string;
  link_id: string | null;
  kind: EvidenceKind;
  enc_meta: string;
  has_blob: boolean;
  size: number;
  created_at: string;
}

export type LockerInfo =
  | { initialized: false }
  | { initialized: true; salt: string; key_check: string; kdf: string };

// ---------- Monitoring and notifications (phase 7) ----------

export interface WatchedPage {
  id: string;
  url: string;
  host: string;
  link_id: string | null;
  interval_hours: number;
  enabled: boolean;
  last_checked_at: string | null;
  next_check_at: string;
  last_result: string | null;
}

export interface NivraNotification {
  id: string;
  kind: "match" | "deadline" | "page_gone" | "page_back" | "system";
  title: string;
  body: string;
  href: string;
  created_at: string;
  read: boolean;
}

export interface NotificationPrefs {
  monitoring_enabled: boolean;
  notify_matches: boolean;
  notify_deadlines: boolean;
  notify_page_changes: boolean;
  email_mode: "off" | "immediate" | "daily";
  has_email: boolean;
  email_backend: "console" | "smtp";
}
