import React from "react";
import { createRoot } from "react-dom/client";
import { I18nProvider } from "../../frontend/src/i18n";
import { BrowserTab } from "../../frontend/src/components/settings/BrowserTab";
import { SuzentLogo } from "../../frontend/src/components/SuzentLogo";
import "../../frontend/src/styles.css";
createRoot(document.getElementById("root")!).render(
  <I18nProvider>
    <div
      style={{
        minHeight: "100vh",
        background: "#ffffff",
        padding: "30px 60px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 20,
          fontWeight: 900,
          fontSize: 20,
        }}
      >
        <SuzentLogo className="h-9 w-9" />
        SUZENT
      </div>
      <main style={{ maxWidth: 960, margin: "0 auto" }}>
        <BrowserTab />
      </main>
    </div>
  </I18nProvider>,
);
