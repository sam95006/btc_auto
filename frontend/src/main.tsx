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
import "./styles/v1827ProductSurface.css";
import "./styles/v1828ProductShell.css";
import "./styles/v1829HumanProduct.css";
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
