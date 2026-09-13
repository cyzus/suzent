import type { ReactNode } from "react";
import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import type { Locale } from "@/lib/locales";
import { identity } from "@/lib/identity";
import "../app/global.css";
export const metadata: Metadata = {
  metadataBase: new URL("https://suzent.com"),
  title: {
    default: "Suzent — The Sovereign AI Agent",
    template: "%s · Suzent",
  },
  description: "Your agent. Your memory. Your rules.",
  icons: { icon: "/img/logo.svg" },
  openGraph: {
    type: "website",
    siteName: "Suzent",
    images: ["/img/suzent-social-card.png"],
  },
  twitter: {
    card: "summary_large_image",
    images: ["/img/suzent-social-card.png"],
  },
};
export function RootLayout({
  children,
  locale,
}: {
  children: ReactNode;
  locale: Locale;
}) {
  return (
    <html lang={locale} suppressHydrationWarning>
      <body className="flex min-h-screen flex-col">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify(identity).replace(/</g, "\\u003c"),
          }}
        />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
