import type { Metadata } from "next";
import ProtectView from "./ProtectView";

export const metadata: Metadata = { title: "Protect images" };

export default function ProtectPage() {
  return <ProtectView />;
}
