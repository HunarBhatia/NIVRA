import type { Category, Platform } from "./types";
import { hostnameOf } from "./platforms";

// Notice generator (blueprint 10.8). Picks the legal grounds that apply and
// fills a template. These are templates, not legal advice.

export const CATEGORY_LABEL: Record<Category, string> = {
  intimate: "Intimate image shared without consent",
  morphed: "Morphed or AI-generated (deepfake) image",
  impersonation: "Fake profile using my photos",
};

interface NoticeInput {
  url: string;
  platform: Platform | null;
  category: Category;
  selfTaken: boolean | null;
  displayName: string;
}

export interface Notice {
  subject: string;
  body: string;
  grounds: string[];
}

function groundsFor(category: Category, selfTaken: boolean | null): string[] {
  const grounds = [
    "Rule 3(1)(b) and Rule 3(2)(b) of the Information Technology (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021, which require removal within 24 hours of a complaint about content that exposes a person's private area, shows them in full or partial nudity or a sexual act, or is in the nature of impersonation, including artificially morphed images.",
  ];
  if (category === "intimate") {
    grounds.push(
      "Section 66E of the Information Technology Act, 2000 (violation of privacy) and Sections 67 and 67A (publishing obscene or sexually explicit material).",
    );
  }
  if (category === "morphed") {
    grounds.push(
      "Sections 66E, 67 and 67A of the Information Technology Act, 2000. The image has been altered or generated to depict me without my consent.",
    );
  }
  if (category === "impersonation") {
    grounds.push(
      "Section 66C (identity theft) and Section 66D (cheating by personation using a computer resource) of the Information Technology Act, 2000.",
    );
  }
  if (selfTaken) {
    grounds.push(
      "I took this photograph myself and own its copyright. Its publication is not authorised by me.",
    );
  }
  grounds.push("Your own community guidelines and terms of service.");
  return grounds;
}

export function generateNotice(input: NoticeInput): Notice {
  const { url, platform, category, selfTaken } = input;
  const name = input.displayName.trim() || "[Your name]";
  const where = platform?.name ?? hostnameOf(url) ?? "your service";
  const grounds = groundsFor(category, selfTaken);

  const what: Record<Category, string> = {
    intimate:
      "an intimate image of me that was shared without my consent. I did not agree to it being published anywhere.",
    morphed:
      "a morphed or AI-generated image that uses my face or body to depict me in a sexual or degrading way. It is fake and was made and shared without my consent.",
    impersonation:
      "a fake profile that uses my photographs and pretends to be me. I did not create it and have not authorised it.",
  };

  const subject = `Urgent removal request: ${CATEGORY_LABEL[category].toLowerCase()} (IT Rules 2021, Rule 3(2)(b))`;

  const body = [
    `To the Grievance Officer / Trust and Safety team, ${where},`,
    "",
    `I am writing to request the immediate removal of content at the following link:`,
    url,
    "",
    `This link contains ${what[category]}`,
    "",
    "I ask you to remove this content and any copies of it on your service under:",
    ...grounds.map((g, i) => `${i + 1}. ${g}`),
    "",
    "Please remove the content within 24 hours as the IT Rules require, prevent it from being uploaded again, and confirm to me in writing once it has been removed. Please preserve the account details of the uploader in case law enforcement requests them.",
    "",
    "I confirm that I am the person shown in this content (or am acting on their behalf with their permission), and that the information in this notice is accurate.",
    "",
    "Regards,",
    name,
    `Date: ${new Date().toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}`,
  ].join("\n");

  return { subject, body, grounds };
}
