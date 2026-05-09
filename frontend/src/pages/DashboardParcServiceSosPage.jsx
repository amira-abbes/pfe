import Layout from "../components/Layout";

const POWER_BI_PARC_URL = import.meta.env.VITE_POWER_BI_PARC_URL || "";

function isValidPowerBiUrl(url) {
  return String(url || "").startsWith("https://app.powerbi.com/reportEmbed");
}

export default function DashboardParcServiceSosPage() {
  const canDisplayDashboard = isValidPowerBiUrl(POWER_BI_PARC_URL);

  return (
    <Layout noPadding noScroll>
      <div className="powerbi-fullscreen">
        {canDisplayDashboard ? (
          <iframe
            title="Dashboard Parc Service SOS Power BI"
            src={POWER_BI_PARC_URL}
            allowFullScreen
          />
        ) : (
          <div className="powerbi-error">
            Dashboard Power BI non configuré.
          </div>
        )}
      </div>
    </Layout>
  );
}
