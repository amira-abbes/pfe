import {
  AlertTriangle,
  BarChart3,
  Bot,
  CheckCircle2,
  Database,
  Eye,
  FileText,
  Gauge,
  Loader2,
  PieChart,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  Users,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  getApiError,
  getBadDebtsAtRisk,
  getBadDebtsClientDetail,
  getBadDebtsClients,
  getBadDebtsRecentActions,
  getBadDebtsSummary,
  runBadDebtsAgent,
} from "../api/api";
import DashboardLayout from "../components/DashboardLayout";
import "../styles/bad-debts-dashboard.css";

const ACTION_LABELS = {
  recovery_review: "Revue recouvrement",
  sms_reminder: "Rappel SMS",
  call_center_priority: "Appel prioritaire",
  monitor_only: "Suivi simple",
};

const STATUS_LABELS = {
  generated: "Générée",
  pending: "En attente",
  completed: "Terminée",
};

const TIER_LABELS = {
  high: "Élevé",
  medium: "Moyen",
  low: "Faible",
};

const CHANNEL_LABELS = {
  sms: "SMS",
  call: "Appel",
  monitoring: "Monitoring",
  internal_review: "Revue interne",
};

function labelFromMap(map, value) {
  if (value === null || value === undefined || value === "") return "-";
  return map[String(value).toLowerCase()] || value;
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  return Number.isNaN(numeric) ? String(value) : new Intl.NumberFormat("fr-FR").format(numeric);
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return `${Math.round(numeric * 100)}%`;
}

function formatScore(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  return Number.isNaN(numeric) ? String(value) : numeric.toFixed(3);
}

function clamp(value, min = 0, max = 100) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return min;
  return Math.min(max, Math.max(min, numeric));
}

function toPercent(value, max = 1) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  const normalized = max > 0 ? numeric / max : numeric;
  return clamp(normalized * 100);
}

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function tierClass(value) {
  const tier = String(value || "low").toLowerCase();
  return ["high", "medium", "low"].includes(tier) ? tier : "low";
}

function getDrivers(value) {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return [value];
  if (value) return [value];
  return [];
}

function driverLabel(driver, index) {
  if (typeof driver === "string") return driver;
  return driver?.feature || driver?.name || driver?.label || `Signal ${index + 1}`;
}

function driverImpact(driver, index, total = 1) {
  if (driver && typeof driver === "object") {
    const candidate = driver.impact ?? driver.importance ?? driver.weight ?? driver.score ?? Math.abs(Number(driver.z_score));
    if (Number.isFinite(Number(candidate))) return clamp(Number(candidate) <= 1 ? Number(candidate) * 100 : Number(candidate));
  }
  return clamp(92 - index * (58 / Math.max(total - 1, 1)), 28, 92);
}

function isGeneratedRecently(action) {
  if (!action || String(action.status || "").toLowerCase() !== "generated" || !action.created_at) return false;
  const createdAt = new Date(action.created_at).getTime();
  return Number.isFinite(createdAt) && Date.now() - createdAt < 10 * 60 * 1000;
}

function hasRecentGeneratedAction(actions = [], msisdn) {
  return actions.some((action) => String(action.msisdn) === String(msisdn) && isGeneratedRecently(action));
}

export default function DashboardBadDebtsPage() {
  const [summary, setSummary] = useState(null);
  const [clients, setClients] = useState({ items: [], total: 0, page: 1, page_size: 10, total_pages: 0 });
  const [actions, setActions] = useState([]);
  const [selectedTier, setSelectedTier] = useState("high");
  const [search, setSearch] = useState("");
  const [selectedClient, setSelectedClient] = useState(null);
  const [agentResult, setAgentResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [clientsLoading, setClientsLoading] = useState(false);
  const [agentLoadingMsisdn, setAgentLoadingMsisdn] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    loadDashboard();
  }, []);

  useEffect(() => {
    loadClients();
  }, [selectedTier]);

  const tierRows = useMemo(() => {
    const byTier = summary?.by_tier || {};
    const total = Math.max(summary?.total_clients || 0, 1);
    return ["low", "medium", "high"].map((tier) => ({
      tier,
      label: TIER_LABELS[tier],
      value: byTier[tier] || 0,
      percent: ((byTier[tier] || 0) / total) * 100,
    }));
  }, [summary]);

  const clusterRows = useMemo(() => {
    const entries = Object.entries(summary?.by_cluster_name || {});
    const max = Math.max(...entries.map(([, value]) => Number(value)), 1);
    return entries.map(([label, value]) => ({
      label,
      value,
      percent: (Number(value) / max) * 100,
    }));
  }, [summary]);

  const recentlyGeneratedMsisdns = useMemo(() => {
    return new Set(actions.filter(isGeneratedRecently).map((action) => String(action.msisdn)));
  }, [actions]);

  async function loadDashboard() {
    setLoading(true);
    setError("");
    try {
      const [summaryResponse, clientsResponse, actionsResponse] = await Promise.all([
        getBadDebtsSummary(),
        getBadDebtsAtRisk({ tier: selectedTier, page: 1, page_size: 10 }),
        getBadDebtsRecentActions({ limit: 20 }),
      ]);
      setSummary(summaryResponse.data);
      setClients(clientsResponse.data);
      setActions(actionsResponse.data || []);
    } catch (err) {
      setError(getApiError(err, "Impossible de charger le dashboard Bad Debts."));
    } finally {
      setLoading(false);
    }
  }

  async function loadClients(page = 1) {
    setClientsLoading(true);
    setError("");
    try {
      const params = { page, page_size: 10 };
      const response = search.trim()
        ? await getBadDebtsClients({ ...params, risk_tier: selectedTier, search: search.trim() })
        : await getBadDebtsAtRisk({ ...params, tier: selectedTier });
      setClients(response.data);
    } catch (err) {
      setError(getApiError(err, "Impossible de charger les clients à risque."));
    } finally {
      setClientsLoading(false);
    }
  }

  async function refreshAll() {
    await loadDashboard();
  }

  async function openClientDetail(msisdn) {
    setDetailLoading(true);
    setAgentResult(null);
    try {
      const response = await getBadDebtsClientDetail(msisdn);
      setSelectedClient(response.data);
    } catch (err) {
      setError(getApiError(err, "Impossible de charger le détail client."));
    } finally {
      setDetailLoading(false);
    }
  }

  async function runAgent(msisdn) {
    setAgentLoadingMsisdn(msisdn);
    setError("");
    try {
      const response = await runBadDebtsAgent(msisdn);
      setAgentResult(response.data);
      const [actionsResponse, detailResponse] = await Promise.all([
        getBadDebtsRecentActions({ limit: 20 }),
        selectedClient?.msisdn === msisdn ? getBadDebtsClientDetail(msisdn) : Promise.resolve(null),
      ]);
      setActions(actionsResponse.data || []);
      if (detailResponse?.data) setSelectedClient(detailResponse.data);
    } catch (err) {
      setError(getApiError(err, "Impossible de lancer l'agent Bad Debts."));
    } finally {
      setAgentLoadingMsisdn("");
    }
  }

  const kpis = [
    {
      label: "Total clients scores",
      value: formatNumber(summary?.total_clients),
      detail: "Population ML exploitée",
      icon: Users,
      tone: "blue",
    },
    {
      label: "Clients à risque",
      value: formatNumber(summary?.at_risk_count),
      detail: "Risque moyen et élevé",
      icon: TrendingDown,
      tone: "orange",
    },
    {
      label: "Risque élevé",
      value: formatNumber(summary?.high_risk_count),
      detail: "Priorité opérationnelle",
      icon: ShieldAlert,
      tone: "magenta",
    },
    {
      label: "Anomalies détectées",
      value: formatNumber(summary?.anomaly_count),
      detail: "Signaux atypiques",
      icon: AlertTriangle,
      tone: "violet",
    },
    {
      label: "Score moyen",
      value: formatScore(summary?.avg_final_risk_score),
      detail: `Max ${formatScore(summary?.max_final_risk_score)}`,
      icon: Zap,
      tone: "cyan",
    },
    {
      label: "Dernier import ML",
      value: summary?.latest_import?.status || "-",
      detail: formatDate(summary?.latest_import_at),
      icon: Database,
      tone: "green",
    },
  ];

  return (
    <DashboardLayout>
      <div className="bad-debts-page">
        <video className="bad-debts-bg-video" src="/bad-debts-bg.mp4" autoPlay muted loop playsInline aria-hidden="true" />
        <div className="bad-debts-bg-mesh" aria-hidden="true" />

        <section className="bad-debts-header">
          <div className="bad-debts-brand-block">
            <div className="bad-debts-logo-card">
              <img src="/tt-logo.png" alt="Tunisie Telecom" />
            </div>
            <div>
              <span className="bad-debts-eyebrow"><Sparkles size={15} /> Machine Learning Bad Debts</span>
              <h1>Dashboard Bad Debts — Service SOS Solde & Data</h1>
              <p>Segmentation ML, scoring risque et recommandations agentic.</p>
              <div className="bad-debts-header-badges" aria-label="Capacités techniques">
                <span><Database size={14} />PostgreSQL ML</span>
                <span><Bot size={14} />Agentic AI</span>
                <span><Zap size={14} />n8n ready</span>
              </div>
            </div>
          </div>
          <button className="btn btn-primary bad-debts-refresh" type="button" onClick={refreshAll} disabled={loading || clientsLoading}>
            <RefreshCw size={18} className={loading ? "spin" : ""} />
            Actualiser
          </button>
        </section>

        {error && (
          <div className="bad-debts-alert" role="alert">
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="bad-debts-loading">
            <Loader2 className="spin" size={24} />
            Chargement du dashboard Bad Debts...
          </div>
        ) : (
          <>
            <section className="bad-debts-kpi-grid">
              {kpis.map((kpi, index) => (
                <article className={`bad-debts-kpi ${kpi.tone}`} style={{ "--delay": `${index * 70}ms` }} key={kpi.label}>
                  <div className="bad-debts-kpi-icon"><kpi.icon size={21} /></div>
                  <span>{kpi.label}</span>
                  <strong>{kpi.value}</strong>
                  <small>{kpi.detail}</small>
                  <KpiSparkline index={index} />
                </article>
              ))}
            </section>

            <section className="bad-debts-analytics-grid">
              <article className="bad-debts-panel bad-debts-chart-panel">
                <PanelTitle title="Répartition du risque" meta={summary?.date || "Données ML"} icon={PieChart} />
                <RiskDonutChart rows={tierRows} total={summary?.total_clients || 0} />
              </article>

              <article className="bad-debts-panel bad-debts-chart-panel">
                <PanelTitle title="Distribution des clusters" meta={`${clusterRows.length} segments`} icon={BarChart3} />
                <ClusterBarChart rows={clusterRows} />
              </article>
            </section>

            <section className="bad-debts-panel bad-debts-table-panel">
              <div className="bad-debts-table-toolbar">
                <div>
                  <h2>Clients à risque</h2>
                  <p>{formatNumber(clients.total)} client(s) pour le filtre sélectionné</p>
                </div>
                <div className="bad-debts-filters">
                  <select className="select" value={selectedTier} onChange={(event) => setSelectedTier(event.target.value)}>
                    <option value="high">Élevé</option>
                    <option value="medium">Moyen</option>
                    <option value="low">Faible</option>
                  </select>
                  <label className="bad-debts-search">
                    <Search size={16} />
                    <input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") loadClients(1);
                      }}
                      placeholder="Recherche MSISDN"
                    />
                  </label>
                  <button className="btn btn-secondary" type="button" onClick={() => loadClients(1)} disabled={clientsLoading}>
                    <RefreshCw size={17} className={clientsLoading ? "spin" : ""} />
                    Filtrer
                  </button>
                </div>
              </div>

              <ClientsTable
                clients={clients.items}
                loading={clientsLoading}
                onDetail={openClientDetail}
                onRunAgent={runAgent}
                agentLoadingMsisdn={agentLoadingMsisdn}
                recentlyGeneratedMsisdns={recentlyGeneratedMsisdns}
              />

              <div className="bad-debts-pagination">
                <button className="btn btn-secondary" disabled={clients.page <= 1 || clientsLoading} onClick={() => loadClients(clients.page - 1)}>
                  Précédent
                </button>
                <span>Page {clients.page} / {clients.total_pages || 1}</span>
                <button className="btn btn-secondary" disabled={clients.page >= clients.total_pages || clientsLoading} onClick={() => loadClients(clients.page + 1)}>
                  Suivant
                </button>
              </div>
            </section>

            {agentResult && <AgentResultPanel result={agentResult} onClose={() => setAgentResult(null)} />}
          </>
        )}

        {(selectedClient || detailLoading) && (
          <ClientDetailModal
            client={selectedClient}
            loading={detailLoading}
            onClose={() => setSelectedClient(null)}
            onRunAgent={runAgent}
            agentLoadingMsisdn={agentLoadingMsisdn}
            agentResult={agentResult?.msisdn === selectedClient?.msisdn ? agentResult : null}
          />
        )}
      </div>
    </DashboardLayout>
  );
}

function PanelTitle({ title, meta, icon: Icon }) {
  return (
    <div className="bad-debts-panel-title">
      <div className="bad-debts-panel-title-main">
        {Icon && <span className="bad-debts-panel-icon"><Icon size={18} /></span>}
        <h2>{title}</h2>
      </div>
      <span>{meta}</span>
    </div>
  );
}

function KpiSparkline({ index }) {
  const variants = [
    "M4 28 C 18 15, 28 36, 42 20 S 68 18, 82 9",
    "M4 23 C 17 31, 28 8, 42 17 S 68 35, 82 12",
    "M4 30 C 20 26, 27 11, 40 14 S 61 16, 82 7",
    "M4 18 C 21 7, 25 35, 42 25 S 66 10, 82 22",
    "M4 27 C 18 12, 31 15, 43 27 S 64 29, 82 10",
    "M4 25 C 17 23, 27 20, 39 13 S 63 15, 82 8",
  ];
  return (
    <svg className="bad-debts-kpi-sparkline" viewBox="0 0 86 40" aria-hidden="true">
      <path d={variants[index % variants.length]} />
    </svg>
  );
}

function RiskDonutChart({ rows, total }) {
  const safeTotal = rows.reduce((sum, row) => sum + Number(row.value || 0), 0) || total || 1;
  let offset = 25;
  const segments = rows.map((row) => {
    const length = (Number(row.value || 0) / safeTotal) * 100;
    const segment = { ...row, length, offset };
    offset -= length;
    return segment;
  });

  return (
    <div className="bad-debts-donut-layout">
      <div className="bad-debts-donut">
        <svg viewBox="0 0 42 42" role="img" aria-label="Répartition du risque">
          <circle className="bad-debts-donut-base" cx="21" cy="21" r="15.9155" />
          {segments.map((row) => (
            <circle
              key={row.tier}
              className={`bad-debts-donut-segment ${row.tier}`}
              cx="21"
              cy="21"
              r="15.9155"
              strokeDasharray={`${row.length} ${100 - row.length}`}
              strokeDashoffset={row.offset}
            />
          ))}
        </svg>
        <div>
          <strong>{formatNumber(total)}</strong>
          <span>clients scorés</span>
        </div>
      </div>
      <div className="bad-debts-donut-legend">
        {rows.map((row) => (
          <div key={row.tier}>
            <span className={`bad-debts-legend-dot ${row.tier}`} />
            <strong>{row.label}</strong>
            <small>{formatNumber(row.value)} · {row.percent.toFixed(1)}%</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function ClusterBarChart({ rows }) {
  if (!rows.length) return <p className="bad-debts-empty">Aucun cluster disponible.</p>;

  return (
    <div className="bad-debts-cluster-chart">
      {rows.map((row, index) => (
        <div className="bad-debts-cluster-bar" key={row.label}>
          <div className="bad-debts-cluster-bar-head">
            <strong>{row.label}</strong>
            <span>{formatNumber(row.value)}</span>
          </div>
          <div className="bad-debts-cluster-bar-track">
            <span style={{ width: `${row.percent}%`, "--delay": `${index * 80}ms` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function ClientsTable({ clients, loading, onDetail, onRunAgent, agentLoadingMsisdn, recentlyGeneratedMsisdns }) {
  if (loading) {
    return <div className="bad-debts-inline-loading"><Loader2 className="spin" size={20} />Chargement des clients...</div>;
  }

  return (
    <div className="bad-debts-table-wrap">
      <table className="bad-debts-table">
        <thead>
          <tr>
            <th>MSISDN</th>
            <th>Cluster</th>
            <th>Risque</th>
            <th>Label risque</th>
            <th>Score</th>
            <th>Anomalie</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {clients.length ? clients.map((client) => {
            const alreadyGenerated = recentlyGeneratedMsisdns.has(String(client.msisdn));
            const running = agentLoadingMsisdn === client.msisdn;
            return (
              <tr key={client.msisdn}>
                <td><strong>{client.msisdn}</strong></td>
                <td>{client.cluster_name || "-"}</td>
                <td><span className={`bad-debts-badge ${tierClass(client.risk_tier)}`}>{labelFromMap(TIER_LABELS, client.risk_tier)}</span></td>
                <td>{client.risk_label || "-"}</td>
                <td>
                  <ScorePill score={client.final_risk_score} tier={client.risk_tier} />
                </td>
                <td>{client.is_anomaly ? <span className="bad-debts-badge anomaly">Oui</span> : <span className="bad-debts-badge neutral">Non</span>}</td>
                <td>
                  <div className="bad-debts-row-actions">
                    <button className="btn btn-secondary" type="button" onClick={() => onDetail(client.msisdn)}>
                      <Eye size={16} />
                      Voir détail
                    </button>
                    <RunAgentButton
                      msisdn={client.msisdn}
                      running={running}
                      alreadyGenerated={alreadyGenerated}
                      onRunAgent={onRunAgent}
                    />
                  </div>
                </td>
              </tr>
            );
          }) : (
            <tr><td colSpan={7} className="bad-debts-empty">Aucun client trouvé.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function RunAgentButton({ msisdn, running, alreadyGenerated, onRunAgent }) {
  return (
    <button
      className={`btn ${alreadyGenerated ? "btn-soft" : "btn-primary"}`}
      type="button"
      onClick={() => onRunAgent(msisdn)}
      disabled={running || alreadyGenerated}
      title={alreadyGenerated ? "Une action generated existe déjà pour ce client sur les 10 dernières minutes." : "Lancer l'agent Bad Debts"}
    >
      {running ? <Loader2 className="spin" size={16} /> : alreadyGenerated ? <CheckCircle2 size={16} /> : <Bot size={16} />}
      {alreadyGenerated ? "Déjà traité récemment" : "Lancer agent"}
    </button>
  );
}

function ScorePill({ score, tier }) {
  const width = toPercent(score, 1);
  return (
    <div className="bad-debts-score-pill">
      <strong>{formatScore(score)}</strong>
      <span>
        <i className={tierClass(tier)} style={{ width: `${width}%` }} />
      </span>
    </div>
  );
}

function ClientAnalytics({ client }) {
  const maxOutstanding = Math.max(Number(client?.total_outstanding_amount) || 0, 1_000);
  const maxSos = Math.max(Number(client?.nb_sos) || 0, 20);
  const metrics = [
    { label: "Score risque", value: formatScore(client?.final_risk_score), percent: toPercent(client?.final_risk_score, 1), tone: tierClass(client?.risk_tier) },
    { label: "Remboursement", value: formatPercent(client?.avg_reimburse_ratio), percent: toPercent(client?.avg_reimburse_ratio, 1), tone: "low" },
    { label: "Debt / credit", value: formatScore(client?.debt_to_credit), percent: toPercent(client?.debt_to_credit, 2), tone: "medium" },
    { label: "Encours", value: formatNumber(client?.total_outstanding_amount), percent: toPercent(client?.total_outstanding_amount, maxOutstanding), tone: "high" },
    { label: "NB SOS", value: formatNumber(client?.nb_sos), percent: toPercent(client?.nb_sos, maxSos), tone: "violet" },
  ];

  return (
    <div className="bad-debts-client-analytics">
      <div className="bad-debts-risk-gauge">
        <Gauge size={18} />
        <div className="bad-debts-risk-gauge-ring" style={{ "--score": `${toPercent(client?.final_risk_score, 1) * 3.6}deg` }}>
          <strong>{formatScore(client?.final_risk_score)}</strong>
          <span>score risque</span>
        </div>
      </div>
      <div className="bad-debts-metric-bars">
        {metrics.map((metric) => (
          <div className="bad-debts-metric-bar" key={metric.label}>
            <div>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
            <i><b className={metric.tone} style={{ width: `${metric.percent}%` }} /></i>
          </div>
        ))}
      </div>
    </div>
  );
}

function DriverImpactChart({ drivers }) {
  return (
    <div className="bad-debts-driver-impact">
      {drivers.slice(0, 8).map((driver, index) => {
        const impact = driverImpact(driver, index, drivers.length);
        return (
          <div className="bad-debts-driver-impact-row" key={`${driverLabel(driver, index)}-${index}`}>
            <div>
              <strong>{driverLabel(driver, index)}</strong>
              {driver?.z_score !== undefined && <span>z={formatScore(driver.z_score)}</span>}
            </div>
            <i><b style={{ width: `${impact}%` }} /></i>
          </div>
        );
      })}
    </div>
  );
}

function ClientDetailModal({ client, loading, onClose, onRunAgent, agentLoadingMsisdn, agentResult }) {
  const drivers = getDrivers(client?.top_drivers);
  const alreadyGenerated = hasRecentGeneratedAction(client?.actions || [], client?.msisdn);

  return (
    <div className="bad-debts-modal-backdrop" role="presentation" onClick={(event) => event.target === event.currentTarget && onClose()}>
      <section className="bad-debts-modal" role="dialog" aria-modal="true">
        <button className="bad-debts-modal-close" type="button" onClick={onClose} aria-label="Fermer">
          <X size={20} />
        </button>
        {loading ? (
          <div className="bad-debts-inline-loading"><Loader2 className="spin" size={22} />Chargement du détail...</div>
        ) : (
          <>
            <div className="bad-debts-modal-header">
              <div>
                <span>Détail client</span>
                <h2>{client?.msisdn}</h2>
              </div>
              <RunAgentButton
                msisdn={client.msisdn}
                running={agentLoadingMsisdn === client?.msisdn}
                alreadyGenerated={alreadyGenerated}
                onRunAgent={onRunAgent}
              />
            </div>

            <div className="bad-debts-detail-grid">
              <Info label="État" value={client?.state} />
              <Info label="Cluster" value={client?.cluster_name} />
              <Info label="Risk label" value={client?.risk_label} />
              <Info label="Risk tier" value={labelFromMap(TIER_LABELS, client?.risk_tier)} />
              <Info label="Score final" value={formatScore(client?.final_risk_score)} />
              <Info label="Anomalie" value={client?.is_anomaly ? "Oui" : "Non"} />
              <Info label="Ratio remboursement" value={formatPercent(client?.avg_reimburse_ratio)} />
              <Info label="Encours" value={formatNumber(client?.total_outstanding_amount)} />
              <Info label="NB SOS" value={formatNumber(client?.nb_sos)} />
              <Info label="Debt to credit" value={formatScore(client?.debt_to_credit)} />
              <Info label="Crédit moyen" value={formatNumber(client?.avg_credit_amount)} />
              <Info label="Ancienneté" value={formatNumber(client?.tenure_days)} />
            </div>

            <ClientAnalytics client={client} />

            {(agentResult || (client?.actions || []).length > 0) && (
              <AgenticReport result={agentResult} client={client} />
            )}

            <div className="bad-debts-detail-section">
              <h3>Top drivers</h3>
              {drivers.length ? (
                <DriverImpactChart drivers={drivers} />
              ) : (
                <p>Aucun driver structuré disponible.</p>
              )}
            </div>

            <div className="bad-debts-detail-section">
              <h3>Actions liées</h3>
              <RecentActionsTable actions={client?.actions || []} compact />
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function AgentResultPanel({ result, onClose }) {
  return (
    <section className="bad-debts-panel bad-debts-agent-panel">
      <div className="bad-debts-panel-title">
        <div>
          <h2>Résultat agentic</h2>
          <span>Run {result.run_id}</span>
        </div>
        <button className="bad-debts-icon-button" type="button" onClick={onClose} aria-label="Fermer le résultat agent">
          <X size={18} />
        </button>
      </div>
      <AgenticReport result={result} />
    </section>
  );
}

function AgenticReport({ result, client }) {
  const latestAction = result?.decision?.reused_action || client?.actions?.[0] || null;
  const profile = result?.profile || client || {};
  const decision = result?.decision || latestAction || {};
  const message = result?.message || {};
  const explanations = result?.explanations || {};
  const drivers = getDrivers(explanations.primary_factors || client?.top_drivers);
  const actionType = decision.action_type || decision.recommended_action || latestAction?.action_type;
  const actionStatus = latestAction?.status || (decision.stored_action_id ? "generated" : null);
  const storedActionId = decision.stored_action_id || latestAction?.id;
  const generatedAt = latestAction?.created_at;
  const reused = Boolean(decision.action_reused);

  return (
    <section className="bad-debts-report">
      <div className="bad-debts-report-title">
        <div className="bad-debts-report-icon"><FileText size={20} /></div>
        <div>
          <h3>Rapport agentic client</h3>
          <p>Lecture métier de la décision, sans JSON brut.</p>
        </div>
      </div>

      <div className="bad-debts-report-grid">
        <article className="bad-debts-report-card wide">
          <h4>Profil client</h4>
          <div className="bad-debts-report-kpis">
            <Info label="MSISDN" value={profile.msisdn} />
            <Info label="État" value={profile.state} />
            <Info label="Cluster" value={profile.cluster_name} />
            <Info label="Risk tier" value={labelFromMap(TIER_LABELS, profile.risk_tier)} />
            <Info label="Risk label" value={profile.risk_label} />
            <Info label="Score final" value={formatScore(profile.final_risk_score)} />
            <Info label="Anomalie" value={profile.is_anomaly ? "Oui" : "Non"} />
            <Info label="Encours" value={formatNumber(profile.total_outstanding_amount)} />
            <Info label="NB SOS" value={formatNumber(profile.nb_sos)} />
            <Info label="Ratio remb." value={formatPercent(profile.avg_reimburse_ratio)} />
            <Info label="Debt/credit" value={formatScore(profile.debt_to_credit)} />
          </div>
        </article>

        <article className="bad-debts-report-card">
          <h4>Facteurs explicatifs</h4>
          {drivers.length ? (
            <DriverImpactChart drivers={drivers} />
          ) : (
            <p>Aucun facteur dominant disponible.</p>
          )}
          {explanations.business_rules?.length ? (
            <ul className="bad-debts-rule-list">
              {explanations.business_rules.slice(0, 4).map((rule) => <li key={rule}>{rule}</li>)}
            </ul>
          ) : null}
        </article>

        <article className="bad-debts-report-card">
          <h4>Décision recommandée</h4>
          <div className="bad-debts-decision-line">
            <span className={`bad-debts-badge ${tierClass(decision.effective_tier || profile.risk_tier)}`}>
              {labelFromMap(ACTION_LABELS, actionType)}
            </span>
            <strong>Priorité {decision.priority || latestAction?.priority || "-"}</strong>
          </div>
          <p>{decision.next_best_action || latestAction?.recommendation || "Décision agentic déjà enregistrée pour ce client."}</p>
          <small>{decision.reason || explanations.explanation_text || "Synthèse basée sur le scoring ML et les actions existantes."}</small>
        </article>

        <article className="bad-debts-report-card">
          <h4>Message proposé</h4>
          <div className="bad-debts-decision-line">
            <span className="bad-debts-badge neutral">{labelFromMap(CHANNEL_LABELS, message.channel)}</span>
            <span className={`bad-debts-badge ${message.safe_to_send ? "low" : "neutral"}`}>
              {message.safe_to_send ? "Envoi autorisé" : "Envoi non recommandé"}
            </span>
          </div>
          <p>{message.message_text || "Aucun message proposé dans l'action enregistrée."}</p>
        </article>

        <article className="bad-debts-report-card">
          <h4>Action enregistrée</h4>
          <Info label="ID action" value={storedActionId} />
          <Info label="Statut" value={labelFromMap(STATUS_LABELS, actionStatus)} />
          <Info label="Génération" value={formatDate(generatedAt)} />
          {reused && <div className="bad-debts-reuse-note"><CheckCircle2 size={16} />Action existante réutilisée, aucune ligne dupliquée.</div>}
        </article>
      </div>
    </section>
  );
}

function Info({ label, value }) {
  return (
    <div className="bad-debts-info">
      <span>{label}</span>
      <strong>{value ?? "-"}</strong>
    </div>
  );
}

function RecentActionsTable({ actions, compact = false }) {
  return (
    <div className="bad-debts-table-wrap">
      <table className={`bad-debts-table ${compact ? "compact" : ""}`}>
        <thead>
          <tr>
            <th>Date</th>
            <th>MSISDN</th>
            <th>Action</th>
            <th>Priorité</th>
            <th>Recommandation</th>
            <th>Statut</th>
          </tr>
        </thead>
        <tbody>
          {actions.length ? actions.map((action) => (
            <tr key={`${action.id}-${action.msisdn}`}>
              <td>{formatDate(action.created_at)}</td>
              <td><strong>{action.msisdn}</strong></td>
              <td>{labelFromMap(ACTION_LABELS, action.action_type)}</td>
              <td><strong>{action.priority}</strong></td>
              <td>{action.recommendation || "-"}</td>
              <td><span className="bad-debts-badge neutral">{labelFromMap(STATUS_LABELS, action.status)}</span></td>
            </tr>
          )) : (
            <tr><td colSpan={6} className="bad-debts-empty">Aucune action récente.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
