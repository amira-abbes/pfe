import { Maximize2, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import Layout from "../components/Layout";

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
    <Layout noPadding noScroll>
      <div className="powerbi-fullscreen" ref={dashboardRef}>
        {canDisplayDashboard && (
          <div className="powerbi-minimal-toolbar" style={{ position: "absolute", top: 16, right: 16, zIndex: 10, display: "flex", gap: 8 }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={reloadDashboardView}
              style={{ background: "rgba(15, 23, 42, 0.75)", color: "#fff", backdropFilter: "blur(8px)", border: "1px solid rgba(255,255,255,0.2)" }}
            >
              <RefreshCw size={16} />
              Actualiser l’affichage
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleFullscreen}
              style={{ background: "rgba(15, 23, 42, 0.75)", color: "#fff", backdropFilter: "blur(8px)", border: "1px solid rgba(255,255,255,0.2)" }}
            >
              <Maximize2 size={16} />
              Plein écran
            </button>
          </div>
        )}

        {canDisplayDashboard && showIframe ? (
          <iframe
            key={iframeKey}
            title="Dashboard Parc Service SOS Power BI"
            src={iframeSrc}
            allowFullScreen
            style={{ width: "100%", height: "100%", border: 0 }}
          />
        ) : canDisplayDashboard ? null : (
          <div className="powerbi-error">
            Dashboard Power BI non configuré.
          </div>
        )}

        {toast && <div className="powerbi-toast info" style={{ position: "absolute", bottom: 24, right: 24, zIndex: 10, background: "rgba(15, 23, 42, 0.9)", color: "#fff", padding: "10px 20px", borderRadius: 12, backdropFilter: "blur(10px)" }}>{toast}</div>}
      </div>
    </Layout>
  );
}

