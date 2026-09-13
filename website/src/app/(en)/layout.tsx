import type { ReactNode } from "react";
import { RootLayout } from "@/components/root-layout";
export { metadata } from "@/components/root-layout";
export default function Layout({ children }: { children: ReactNode }) {
  return <RootLayout locale="en">{children}</RootLayout>;
}
