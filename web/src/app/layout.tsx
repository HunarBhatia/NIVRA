import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Nivra",
  description:
    "Get images that were shared without your consent taken down, privately.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  // suppressHydrationWarning: browser extensions (e.g. custom-cursor ones)
  // add attributes to <html>/<body> before React loads, which would otherwise
  // trigger a false hydration error. It only affects these two tags'
  // own attributes, not anything inside them.
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
