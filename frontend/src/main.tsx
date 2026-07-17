import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { clearAssetLoadRecoveryGuard, installAssetLoadRecovery } from "./assetLoadRecovery";
import App from "./App";
import "./styles/designTokens.css";
import "./styles/phase2Tokens.css";
import "./styles/global.css";

installAssetLoadRecovery();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);

clearAssetLoadRecoveryGuard();
