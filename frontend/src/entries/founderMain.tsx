import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { I18nProvider } from "../i18n";
import FounderApp from "../surfaces/FounderApp";
import "../styles/designTokens.css";
import "../styles/global.css";
import "../styles/founderOperator.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <FounderApp />
      </I18nProvider>
    </BrowserRouter>
  </StrictMode>
);
