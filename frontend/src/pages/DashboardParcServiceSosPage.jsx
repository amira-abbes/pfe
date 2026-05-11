import { Maximize2, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import DashboardLayout from "../components/DashboardLayout";

const POWER_BI_PARC_URL = import.meta.env.VITE_POWER_BI_PARC_URL || "";
const PARC_REPORT_ID = "f23cfc63-7497-4c36-a66d-995d953c7842";
const POWER_BI_TENANT_ID = "604f1a96-cbe8-43f8-abbf-f8eaf5d85730";

function isValidPowerBiUrl(url) {
  return String(url || "").startsWith("https://app.powerbi.com/reportEmbed");
}

function buildIframeSrc(url, cacheKey) {
  if (!url) return "";
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}cacheBust=${cacheKey}`;
}

export default function DashboardParcServiceSosPage() {
  const location = useLocation();
  const dashboardRef = useRef(null);
  const [iframeKey, setIframeKey] = useState(() => Date.now());
  const [showIframe, setShowIframe] = useState(true);
  const [toast, setToast] = useState("");
  const canDisplayDashboard = isValidPowerBiUrl(POWER_BI_PARC_URL);
  const iframeSrc = buildIframeSrc(POWER_BI_PARC_URL, iframeKey);

  const handleFullscreen = () => {
    if (dashboardRef.current?.requestFullscreen) {
      dashboardRef.current.requestFullscreen();
    }
  };

  const showToast = (message) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 3500);
  };

  const reloadDashboardView = () => {
    setShowIframe(false);
    const nextKey = Date.now();
    window.setTimeout(() => {
      setIframeKey(nextKey);
      setShowIframe(true);
    }, 150);
    showToast("Affichage du dashboard rechargé.");
  };

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("reload") === "1") {
      reloadDashboardView();
    }
  }, [location.search]);

  useEffect(() => {
    console.log("[POWERBI PARC] env url =", POWER_BI_PARC_URL);
    console.log("[POWERBI PARC] expected reportId =", PARC_REPORT_ID);
    console.log("[POWERBI PARC] expected ctid =", POWER_BI_TENANT_ID);
    console.log("[POWERBI PARC] iframe key =", iframeKey);
    console.log("[POWERBI PARC] iframe src =", iframeSrc);
  }, [iframeKey, iframeSrc]);

  return (
    <DashboardLayout>
      <div className="powerbi-minimal-page">
        {canDisplayDashboard && (
          <div className="powerbi-minimal-toolbar">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={reloadDashboardView}
            >
              <RefreshCw size={18} />
              Actualiser l’affichage
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleFullscreen}
            >
              <Maximize2 size={18} />
              Plein écran
            </button>
          </div>
        )}

        <div className="powerbi-minimal-frame" ref={dashboardRef}>
          {canDisplayDashboard && showIframe ? (
            <iframe
              key={iframeKey}
              title="dashboard_PARC_final"
              src={iframeSrc}
              allowFullScreen
            />
          ) : canDisplayDashboard ? (
            null
          ) : (
            <div className="powerbi-minimal-empty">
              Dashboard Power BI non configuré.
            </div>
          )}
        </div>
        {toast && <div className="powerbi-toast info">{toast}</div>}
      </div>
    </DashboardLayout>
  );
}
