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
