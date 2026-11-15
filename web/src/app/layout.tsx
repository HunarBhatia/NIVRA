import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Manrope, Syne } from "next/font/google";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import Backdrop from "@/components/motion/Backdrop";
import "./globals.css";

// "Midnight" design (section 22.2): Syne for display, Manrope for reading,
// JetBrains Mono for fingerprints and hashes.
const syne = Syne({ variable: "--font-syne", subsets: ["latin"], weight: ["600", "700", "800"] });
const manrope = Manrope({ variable: "--font-manrope", subsets: ["latin"], weight: ["400", "500", "600", "700"] });
const mono = JetBrains_Mono({ variable: "--font-jbmono", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: { default: "Nivra", template: "%s | Nivra" },
  description: "Find, prove and take down images shared without your consent - privately.",
  // Victims may be searched for; keep the prototype out of search engines.
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export const viewport: Viewport = { themeColor: "#05070d", colorScheme: "dark" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  // suppressHydrationWarning: browser extensions (e.g. custom-cursor ones)
  // add attributes to <html>/<body> before React loads, which would otherwise
  // trigger a false hydration error. It only affects these two tags'
  // own attributes, not anything inside them.
  return (
    <html
      lang="en"
      className={`${syne.variable} ${manrope.variable} ${mono.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-dvh flex flex-col" suppressHydrationWarning>
        <Backdrop />
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
