import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import DashboardLayout from "../components/DashboardLayout";

const POWERBI_SERVICE_SOS_URL =
  import.meta.env.VITE_POWERBI_DASHBOARD_SERVICE_SOS_URL;

function isValidPowerBiUrl(url) {
  return String(url || "").startsWith("https://app.powerbi.com/reportEmbed");
}

export default function DashboardServiceSosPage() {
  const location = useLocation();
  const [dashboardKey, setDashboardKey] = useState(0);
  const [toast, setToast] = useState("");
  const canDisplayDashboard = isValidPowerBiUrl(POWERBI_SERVICE_SOS_URL);

  const showToast = (message) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 3500);
  };

  const reloadDashboardView = () => {
    setDashboardKey((key) => key + 1);
    showToast("Affichage du dashboard rechargé.");
  };

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("reload") === "1") {
      reloadDashboardView();
    }
  }, [location.search]);

  return (
    <DashboardLayout>
      <section className="powerbi-page">
        {canDisplayDashboard && (
          <div className="powerbi-view-toolbar">
            <button type="button" className="btn btn-secondary" onClick={reloadDashboardView}>
              <RefreshCw size={18} />
              Actualiser l’affichage
            </button>
          </div>
        )}
        {canDisplayDashboard ? (
          <iframe
            key={dashboardKey}
            title="Dashboard Service SOS Power BI"
            src={POWERBI_SERVICE_SOS_URL}
            width="100%"
            height="100%"
            frameBorder="0"
            allowFullScreen
          />
        ) : (
          <div className="powerbi-error">
            URL Power BI invalide ou non configurée.
          </div>
        )}
        {toast && <div className="powerbi-toast info">{toast}</div>}
      </section>
    </DashboardLayout>
  );
}
