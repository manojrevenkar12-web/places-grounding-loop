import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/overpass/400.css";
import "@fontsource/overpass/600.css";
import "@fontsource/overpass/800.css";
import "./theme/global.css";
import { applyTokens } from "./theme/tokens";
import { App } from "./app/App";

applyTokens();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
