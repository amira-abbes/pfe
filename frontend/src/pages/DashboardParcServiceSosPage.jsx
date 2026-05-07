import { Maximize2 } from "lucide-react";
import { useRef } from "react";

import DashboardLayout from "../components/DashboardLayout";

const POWER_BI_PARC_URL = import.meta.env.VITE_POWER_BI_PARC_URL || "";

function isValidPowerBiUrl(url) {
  return String(url || "").startsWith("https://app.powerbi.com/reportEmbed");
}

export default function DashboardParcServiceSosPage() {
  const dashboardRef = useRef(null);
  const canDisplayDashboard = isValidPowerBiUrl(POWER_BI_PARC_URL);

  const handleFullscreen = () => {
    if (dashboardRef.current?.requestFullscreen) {
      dashboardRef.current.requestFullscreen();
    }
  };

  return (
    <DashboardLayout>
      <div className="powerbi-minimal-page">
        {canDisplayDashboard && (
          <div className="powerbi-minimal-toolbar">
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
          {canDisplayDashboard ? (
            <iframe
              title="dashboard_PARC_final"
              src={POWER_BI_PARC_URL}
              allowFullScreen
            />
          ) : (
            <div className="powerbi-minimal-empty">
              Dashboard Power BI non configuré.
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
