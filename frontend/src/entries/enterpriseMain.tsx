import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { I18nProvider } from "../i18n";
import EnterpriseApp from "../surfaces/EnterpriseApp";
import "../styles/designTokens.css";
import "../styles/global.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <EnterpriseApp />
      </I18nProvider>
    </BrowserRouter>
  </StrictMode>
);
