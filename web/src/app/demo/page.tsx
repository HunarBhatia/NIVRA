import type { Metadata } from "next";
import DemoView from "./DemoView";

export const metadata: Metadata = { title: "See it work" };

export default function DemoPage() {
  return <DemoView />;
}
