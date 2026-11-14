import type { Metadata } from "next";
import { Hanken_Grotesk, Newsreader, Vollkorn } from "next/font/google";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";
import "./globals.css";

// Fonts for the "Garden" look: Vollkorn headings, Hanken Grotesk body,
// Newsreader for small captions. See PROJECT_DETAILS.txt section 9.
const vollkorn = Vollkorn({ variable: "--font-vollkorn", subsets: ["latin"], weight: "600" });
const hanken = Hanken_Grotesk({
  variable: "--font-hanken",
  subsets: ["latin"],
  weight: ["400", "500"],
});
const newsreader = Newsreader({ variable: "--font-newsreader", subsets: ["latin"], weight: "400" });

export const metadata: Metadata = {
  title: { default: "Nivra", template: "%s | Nivra" },
  description: "Get images that were shared without your consent taken down, privately.",
  // Victims may be searched for; keep the prototype out of search engines.
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  // suppressHydrationWarning: browser extensions (e.g. custom-cursor ones)
  // add attributes to <html>/<body> before React loads, which would otherwise
  // trigger a false hydration error. It only affects these two tags'
  // own attributes, not anything inside them.
  return (
    <html
      lang="en"
      className={`${vollkorn.variable} ${hanken.variable} ${newsreader.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-dvh flex flex-col" suppressHydrationWarning>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <SiteHeader />
        <main id="main" className="flex-1">
          {children}
        </main>
        <SiteFooter />
      </body>
    </html>
  );
}
