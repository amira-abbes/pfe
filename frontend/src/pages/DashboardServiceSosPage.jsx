import { Maximize2, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import Layout from "../components/Layout";

const POWERBI_SERVICE_SOS_URL = import.meta.env.VITE_POWERBI_DASHBOARD_SERVICE_SOS_URL || "";

function isValidPowerBiUrl(url) {
  return String(url || "").startsWith("https://app.powerbi.com/reportEmbed");
}

function buildIframeSrc(url, cacheKey) {
  if (!url) return "";
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}cacheBust=${cacheKey}`;
}

export default function DashboardServiceSosPage() {
  const location = useLocation();
  const dashboardRef = useRef(null);
  const [iframeKey, setIframeKey] = useState(() => Date.now());
  const [showIframe, setShowIframe] = useState(true);
  const [toast, setToast] = useState("");

  const canDisplayDashboard = isValidPowerBiUrl(POWERBI_SERVICE_SOS_URL);
  const iframeSrc = buildIframeSrc(POWERBI_SERVICE_SOS_URL, iframeKey);

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

  return (
    <Layout noScroll className="app-shell--service-sos">
      <div className="service-sos-dashboard-page">
        <div className="service-sos-toolbar">
          <div className="service-sos-toolbar-title">
            <strong>Service SOS</strong>
            <span>Power BI</span>
          </div>
          {canDisplayDashboard && (
            <div className="service-sos-toolbar-actions">
              <button type="button" onClick={reloadDashboardView} title="Actualiser le dashboard">
                <RefreshCw size={15} /> <span>Actualiser</span>
              </button>
              <button type="button" onClick={handleFullscreen} title="Afficher en plein écran">
                <Maximize2 size={15} /> <span>Plein écran</span>
              </button>
            </div>
          )}
        </div>
        <div className="service-sos-dashboard-frame" ref={dashboardRef}>
          {canDisplayDashboard && showIframe ? (
            <iframe
              key={iframeKey}
              title="Dashboard Service SOS Power BI"
              src={iframeSrc}
              allowFullScreen
            />
          ) : canDisplayDashboard ? null : (
            <div className="powerbi-error">
              URL Power BI invalide ou non configurée.
            </div>
          )}

          {toast && <div className="service-sos-toast">{toast}</div>}
        </div>
      </div>
    </Layout>
  );
}
