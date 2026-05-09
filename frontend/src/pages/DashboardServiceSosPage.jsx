import Layout from "../components/Layout";

const POWERBI_SERVICE_SOS_URL =
  import.meta.env.VITE_POWERBI_DASHBOARD_SERVICE_SOS_URL;

function isValidPowerBiUrl(url) {
  return String(url || "").startsWith("https://app.powerbi.com/reportEmbed");
}

export default function DashboardServiceSosPage() {
  const canDisplayDashboard = isValidPowerBiUrl(POWERBI_SERVICE_SOS_URL);

  return (
    <Layout noPadding noScroll>
      <div className="powerbi-fullscreen">
        {canDisplayDashboard ? (
          <iframe
            title="Dashboard Service SOS Power BI"
            src={POWERBI_SERVICE_SOS_URL}
            allowFullScreen
          />
        ) : (
          <div className="powerbi-error">
            URL Power BI invalide ou non configurée.
          </div>
        )}
      </div>
    </Layout>
  );
}
