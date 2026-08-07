import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { clearAssetLoadRecoveryGuard, installAssetLoadRecovery } from "./assetLoadRecovery";
import App from "./App";
import { I18nProvider } from "./i18n";
import "./styles/designTokens.css";
import "./styles/phase2Tokens.css";
import "./styles/wave4ProductTokens.css";
import "./styles/global.css";
import "./styles/memberPlatform.css";
/* V18.2.10: legacy v1827/v1828/v1829 layout CSS intentionally NOT loaded */
import "./styles/v18210ProductSystem.css";
import "./styles/a11yPerf.css";
import "./styles/founderOperator.css";

installAssetLoadRecovery();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <App />
      </I18nProvider>
    </BrowserRouter>
  </StrictMode>
);

clearAssetLoadRecoveryGuard();
