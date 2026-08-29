import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { I18nProvider } from "../i18n";
import CorporateApp from "../surfaces/CorporateApp";
import "../styles/designTokens.css";
import "../styles/global.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <CorporateApp />
      </I18nProvider>
    </BrowserRouter>
  </StrictMode>
);
