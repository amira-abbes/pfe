import { useState } from "react";

import DashboardLayout from "../components/DashboardLayout";

const POWERBI_SERVICE_SOS_URL =
  import.meta.env.VITE_POWERBI_DASHBOARD_SERVICE_SOS_URL;

function isValidPowerBiUrl(url) {
  return String(url || "").startsWith("https://app.powerbi.com/reportEmbed");
}

export default function DashboardServiceSosPage() {
  const [dashboardKey] = useState(0);
  const canDisplayDashboard = isValidPowerBiUrl(POWERBI_SERVICE_SOS_URL);

  return (
    <DashboardLayout>
      <section className="powerbi-page">
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
      </section>
    </DashboardLayout>
  );
}
