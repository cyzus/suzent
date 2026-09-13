import Link from "next/link";
import { localePath, type Locale } from "@/lib/locales";
import { messages } from "@/lib/messages";
export function SiteFooter({ locale }: { locale: Locale }) {
  const text = messages(locale);
  return (
    <footer className="site-footer">
      <span>© {new Date().getFullYear()} SUZENT</span>
      <Link href={localePath("/browser-privacy", locale)}>{text.privacy}</Link>
      <a href="https://github.com/cyzus/suzent">GitHub ↗</a>
    </footer>
  );
}
