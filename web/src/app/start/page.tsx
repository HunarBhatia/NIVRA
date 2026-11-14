import type { Metadata } from "next";
import StartWizard from "./StartWizard";

export const metadata: Metadata = { title: "Start a case" };

export default function StartPage() {
  return <StartWizard />;
}
