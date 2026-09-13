import Link from "next/link";
import "./global.css";
export const metadata = {
  title: "404 · Suzent",
  robots: { index: false, follow: true },
  alternates: { canonical: "https://suzent.com/404/" },
};
export default function NotFound() {
  return (
    <html lang="en">
      <body>
        <main className="editorial">
          <h1>404</h1>
          <p>This page could not be found. / 找不到此页面。</p>
          <Link href="/">Home / 首页 →</Link>
        </main>
      </body>
    </html>
  );
}
