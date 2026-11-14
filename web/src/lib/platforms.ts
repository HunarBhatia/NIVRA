import type { Platform } from "./types";

// The Platform Directory (blueprint 10.6).
// PROTOTYPE DATA: every link and step here must be checked by a person
// before public launch. Platforms move their help pages often.

export const PLATFORMS: Platform[] = [
  {
    id: "instagram",
    name: "Instagram",
    owner: "Meta",
    domains: ["instagram.com", "instagr.am"],
    expectedHours: 24,
    channels: [
      { label: "Report inside the Instagram app", kind: "in-app" },
      { label: "Instagram Help Centre", kind: "form", target: "https://help.instagram.com/" },
    ],
    inAppSteps: [
      "Open the post or profile and tap the three dots.",
      "Tap Report, then choose the option about nudity or someone sharing private images.",
      "If it is a fake account, choose 'Pretending to be someone' and pick 'Me'.",
      "Paste the notice from Nivra into any free-text box you are offered.",
    ],
    notes: "Meta is a StopNCII partner: registering your image there blocks re-uploads.",
  },
  {
    id: "facebook",
    name: "Facebook",
    owner: "Meta",
    domains: ["facebook.com", "fb.com", "fb.watch", "m.facebook.com"],
    expectedHours: 24,
    channels: [
      { label: "Report inside Facebook", kind: "in-app" },
      { label: "Facebook Help Centre", kind: "form", target: "https://www.facebook.com/help/" },
    ],
    inAppSteps: [
      "Open the post, photo or profile and click the three dots.",
      "Choose Report, then the option about nudity, private images or impersonation.",
      "Follow the steps and add the notice text where you can.",
    ],
    notes: "Meta is a StopNCII partner.",
  },
  {
    id: "whatsapp",
    name: "WhatsApp",
    owner: "Meta",
    domains: ["whatsapp.com", "wa.me", "chat.whatsapp.com"],
    expectedHours: 24,
    channels: [{ label: "Report inside WhatsApp", kind: "in-app" }],
    inAppSteps: [
      "Open the chat or group, tap its name at the top.",
      "Scroll down and tap Report. Choose to keep the last messages so WhatsApp can review them.",
      "WhatsApp cannot see message content otherwise, so reporting is the main route.",
    ],
  },
  {
    id: "x",
    name: "X (Twitter)",
    domains: ["x.com", "twitter.com", "t.co"],
    expectedHours: 24,
    channels: [
      { label: "Report inside X", kind: "in-app" },
      { label: "X help forms", kind: "form", target: "https://help.x.com/en/forms" },
    ],
    inAppSteps: [
      "Open the post and tap the three dots, then Report post.",
      "Choose the option about sensitive or private media of you.",
    ],
  },
  {
    id: "reddit",
    name: "Reddit",
    domains: ["reddit.com", "redd.it", "old.reddit.com"],
    expectedHours: 24,
    channels: [
      { label: "Report inside Reddit", kind: "in-app" },
      { label: "Reddit report form", kind: "form", target: "https://www.reddit.com/report" },
    ],
    inAppSteps: [
      "Open the post, tap the three dots and choose Report.",
      "Choose 'Non-consensual intimate media' and follow the steps.",
    ],
    notes: "Reddit is a StopNCII partner.",
  },
  {
    id: "youtube",
    name: "YouTube",
    owner: "Google",
    domains: ["youtube.com", "youtu.be", "m.youtube.com"],
    expectedHours: 24,
    channels: [
      { label: "Report inside YouTube", kind: "in-app" },
      { label: "YouTube Help", kind: "form", target: "https://support.google.com/youtube/" },
    ],
    inAppSteps: [
      "Under the video, tap the three dots and choose Report.",
      "For a privacy violation, use YouTube's privacy complaint process from the Help Centre.",
    ],
  },
  {
    id: "telegram",
    name: "Telegram",
    domains: ["t.me", "telegram.me", "telegram.org"],
    expectedHours: 24,
    channels: [
      { label: "Report inside Telegram", kind: "in-app" },
      { label: "Email Telegram's abuse team", kind: "email", target: "abuse@telegram.org" },
    ],
    inAppSteps: [
      "Open the channel or message, tap the three dots and choose Report.",
      "Also email the notice with the t.me link to Telegram's abuse address.",
    ],
    notes: "Leaks spread fast on Telegram channels. Report the channel as well as single posts.",
  },
  {
    id: "snapchat",
    name: "Snapchat",
    domains: ["snapchat.com"],
    expectedHours: 24,
    channels: [
      { label: "Report inside Snapchat", kind: "in-app" },
      { label: "Snapchat Support", kind: "form", target: "https://help.snapchat.com/" },
    ],
    inAppSteps: ["Press and hold the Snap or profile, then tap Report."],
  },
  {
    id: "discord",
    name: "Discord",
    domains: ["discord.com", "discord.gg"],
    expectedHours: 24,
    channels: [
      { label: "Report inside Discord", kind: "in-app" },
      { label: "Discord Trust & Safety", kind: "form", target: "https://dis.gd/request" },
    ],
  },
  {
    id: "linkedin",
    name: "LinkedIn",
    domains: ["linkedin.com", "lnkd.in"],
    expectedHours: 24,
    channels: [
      { label: "Report inside LinkedIn", kind: "in-app" },
      { label: "LinkedIn Help", kind: "form", target: "https://www.linkedin.com/help/linkedin" },
    ],
    inAppSteps: ["Open the profile, click More, then Report / Block, and choose fake profile."],
  },
  {
    id: "tinder",
    name: "Tinder",
    domains: ["tinder.com"],
    expectedHours: 24,
    channels: [{ label: "Tinder Help", kind: "form", target: "https://www.help.tinder.com/" }],
  },
  {
    id: "pornhub",
    name: "Pornhub",
    owner: "Aylo",
    domains: ["pornhub.com"],
    expectedHours: 24,
    channels: [
      { label: "Content removal request", kind: "form", target: "https://www.pornhub.com/content-removal" },
    ],
    notes: "Adult sites often remove fastest when the notice says clearly that there was no consent.",
  },
];

/** Google Search de-indexing: useful for every link, even when a site refuses. */
export const GOOGLE_DEINDEX_URL = "https://support.google.com/websearch/answer/6302812";
export const STOPNCII_URL = "https://stopncii.org/";
export const TAKE_IT_DOWN_URL = "https://takeitdown.ncmec.org/";
export const CYBERCRIME_URL = "https://cybercrime.gov.in/";
export const CLOUDFLARE_ABUSE_URL = "https://abuse.cloudflare.com/";

export function getPlatform(id: string | null | undefined): Platform | undefined {
  return PLATFORMS.find((p) => p.id === id);
}

/** Returns the bare hostname without "www.", or null if the text isn't a URL. */
export function hostnameOf(raw: string): string | null {
  const text = raw.trim();
  if (!text) return null;
  try {
    const url = new URL(/^https?:\/\//i.test(text) ? text : `https://${text}`);
    if (!url.hostname.includes(".")) return null;
    return url.hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return null;
  }
}

/** Normalises a pasted link so it always starts with https:// */
export function normaliseUrl(raw: string): string | null {
  const text = raw.trim();
  if (!hostnameOf(text)) return null;
  return /^https?:\/\//i.test(text) ? text : `https://${text}`;
}

/**
 * Splits pasted text into link candidates: one per line (or comma). A line is
 * only split on spaces when every piece looks like a link, so "not a link"
 * stays one entry instead of three.
 */
export function splitLinks(text: string): string[] {
  return text
    .split(/[\n,]+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .flatMap((line) => {
      const parts = line.split(/\s+/);
      return parts.length > 1 && parts.every((p) => hostnameOf(p)) ? parts : [line];
    });
}

/** Finds the platform for a URL, matching subdomains too (m.facebook.com -> facebook). */
export function resolvePlatform(raw: string): Platform | null {
  const host = hostnameOf(raw);
  if (!host) return null;
  return (
    PLATFORMS.find((p) => p.domains.some((d) => host === d || host.endsWith(`.${d}`))) ?? null
  );
}
