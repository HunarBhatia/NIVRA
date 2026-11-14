import type { Metadata } from "next";
import CaseView from "./CaseView";

export const metadata: Metadata = { title: "My case" };

export default function CasePage() {
  return <CaseView />;
}
