import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import CorporateApp from "../surfaces/CorporateApp";
import "../styles/designTokens.css";
import "../styles/global.css";

// The Corporate surface uses its own theme + locale providers (inside
// CorporateApp) supporting zh-TW / en-US / ja-JP / ko-KR.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <CorporateApp />
    </BrowserRouter>
  </StrictMode>
);
