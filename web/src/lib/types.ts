// Shared types for the Nivra prototype.
// See PROJECT_DETAILS.txt section 10 (MVP blueprint) for the reasoning.

/** What kind of harm the case is about (decision D1). */
export type Category = "intimate" | "morphed" | "impersonation";

/** Lifecycle of a single link (blueprint 10.5). */
export type LinkStatus =
  | "found" // added, nothing sent yet
  | "reported" // user sent the notice, waiting for a reply
  | "removed" // platform took it down
  | "rejected" // platform refused
  | "escalated" // user moved to the next step on the ladder
  | "reappeared"; // was removed, came back

export interface StatusEvent {
  at: string; // ISO timestamp
  status: LinkStatus;
  note?: string;
}

export interface CaseLink {
  id: string;
  url: string;
  platformId: string | null; // null = not in our directory yet
  status: LinkStatus;
  reportedAt?: string;
  /** Prototype-only: lets testers pretend time has passed. */
  deadlineOverride?: boolean;
  events: StatusEvent[];
}

export interface NivraCase {
  id: string; // e.g. NV-7K3Q-92XD
  createdAt: string;
  category: Category;
  selfTaken: boolean | null; // did the user take the photo themselves?
  displayName: string; // optional name to sign notices with
  passHash: string; // PBKDF2 hash of the passphrase
  salt: string;
  links: CaseLink[];
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
