import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  Brain,
  CheckCircle2,
  CloudUpload,
  Download,
  Eye,
  FileDown,
  FileText,
  Gauge,
  Home,
  Loader2,
  LogOut,
  Moon,
  MoreHorizontal,
  Play,
  Printer,
  RefreshCw,
  RotateCcw,
  Search,
  Settings,
  ShieldAlert,
  Sparkles,
  Sun,
  Target,
  TrendingDown,
  Users,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { NavLink, Navigate, useNavigate, useParams } from "react-router-dom";

import {
  getApiError,
  getBadDebtsAgentReports,
  getBadDebtsAtRisk,
  getBadDebtsClientDetail,
  getBadDebtsClients,
  getBadDebtsImportRuns,
  getBadDebtsRecentActions,
  getBadDebtsSummary,
  runBadDebtsAgent,
  runBadDebtsAgentBatch,
} from "../api/api";
import { useAuth } from "../context/AuthContext";
import "../styles/bad-debts-dashboard.css";

const BAD_DEBTS_THEME_KEY = "badDebtsTheme";

const ACTION_LABELS = {
  recovery_review: "Revue recouvrement",
  sms_reminder: "Rappel SMS",
  call_center_priority: "Appel prioritaire",
  monitor_only: "Surveillance simple",
};

const TIER_LABELS = {
  high: "Élevé",
  medium: "Moyen",
  low: "Faible",
};

const STATUS_LABELS = {
  generated: "Nouvelle",
  pending: "En attente",
  completed: "Traitee",
};

const VIEW_META = {
  overview: "Vue globale",
  clients: "Clients a risque",
  agentic: "Analyse agentic",
  actions: "Actions recommandees",
  reports: "Rapports agentic",
  imports: "Historique imports",
  settings: "Parametres",
};

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  return Number.isNaN(numeric) ? String(value) : new Intl.NumberFormat("fr-FR").format(numeric);
}

function formatScore(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  return Number.isNaN(numeric) ? String(value) : numeric.toFixed(3);
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return `${Math.round(numeric * 100)}%`;
}

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function normalizeTier(value) {
  const tier = String(value || "low").toLowerCase();
  return ["high", "medium", "low"].includes(tier) ? tier : "low";
}

function tierLabel(value) {
  return TIER_LABELS[normalizeTier(value)] || value || "-";
}

function actionLabel(value) {
  return ACTION_LABELS[String(value || "")] || value || "-";
}

function initials(value = "") {
  const text = String(value || "CL");
  return text.slice(-2).toUpperCase();
}

function toPercent(value, max = 1) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(100, (numeric / Math.max(max, 0.0001)) * 100));
}

export default function DashboardBadDebtsPage() {
  const params = useParams();
  const leaf = params["*"] || "";
  const [view, detailMsisdn] = leaf.split("/");

  if (!leaf) return <Navigate to="/dashboard/bad-debts/overview" replace />;
  if (view === "client" && detailMsisdn) return <BadDebtsClientDetailPage msisdn={detailMsisdn} />;
  if (!VIEW_META[view]) return <Navigate to="/dashboard/bad-debts/overview" replace />;

  return <BadDebtsWorkspace view={view} />;
}

function BadDebtsWorkspace({ view }) {
  const [theme, setTheme] = useState(() => localStorage.getItem(BAD_DEBTS_THEME_KEY) || "dark");
  const [summary, setSummary] = useState(null);
  const [clients, setClients] = useState({ items: [], total: 0, page: 1, page_size: 10, total_pages: 0 });
  const [actions, setActions] = useState([]);
  const [reports, setReports] = useState([]);
  const [imports, setImports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [clientsLoading, setClientsLoading] = useState(false);
  const [agentLoadingMsisdn, setAgentLoadingMsisdn] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    localStorage.setItem(BAD_DEBTS_THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    refreshDashboard();
  }, []);

  async function refreshDashboard() {
    setLoading(true);
    setError("");
    try {
      const [summaryResponse, clientsResponse, actionsResponse, reportsResponse, importsResponse] = await Promise.all([
        getBadDebtsSummary(),
        getBadDebtsAtRisk({ tier: "high", page: 1, page_size: 10 }),
        getBadDebtsRecentActions({ limit: 50 }),
        getBadDebtsAgentReports({ limit: 20 }),
        getBadDebtsImportRuns({ limit: 20 }),
      ]);
      setSummary(summaryResponse.data);
      setClients(clientsResponse.data);
      setActions(actionsResponse.data || []);
      setReports(reportsResponse.data || []);
      setImports(importsResponse.data || []);
    } catch (err) {
      setError(getApiError(err, "Impossible de charger l'espace Bad Debts."));
    } finally {
      setLoading(false);
    }
  }

  async function loadClients(params = {}) {
    setClientsLoading(true);
    setError("");
    try {
      const response = await getBadDebtsClients({ page: 1, page_size: 10, ...params });
      setClients(response.data);
    } catch (err) {
      setError(getApiError(err, "Impossible de charger les clients."));
    } finally {
      setClientsLoading(false);
    }
  }

  async function runAgent(msisdn) {
    setAgentLoadingMsisdn(msisdn);
    setError("");
    try {
      await runBadDebtsAgent(msisdn);
      const actionsResponse = await getBadDebtsRecentActions({ limit: 50 });
      setActions(actionsResponse.data || []);
    } catch (err) {
      setError(getApiError(err, "Impossible de lancer l'agent Bad Debts."));
    } finally {
      setAgentLoadingMsisdn("");
    }
  }

  const context = {
    summary,
    clients,
    actions,
    reports,
    imports,
    loading,
    clientsLoading,
    agentLoadingMsisdn,
    refreshDashboard,
    loadClients,
    runAgent,
  };
  const headerNode = <BadDebtsHeader view={view} />;

  return (
    <div className={`bdx-shell ${theme === "light" ? "is-light" : "is-dark"}`}>
      <BadDebtsSidebar theme={theme} onThemeToggle={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} />
      <main className="bdx-main">
        {view !== "overview" && headerNode}
        {error && <div className="bdx-alert"><AlertTriangle size={18} />{error}</div>}
        {loading ? (
          <div className="bdx-loading"><Loader2 className="spin" size={24} />Chargement Bad Debts...</div>
        ) : (
          <ViewRenderer view={view} context={{ ...context, headerNode }} />
        )}
      </main>
    </div>
  );
}

function BadDebtsSidebar({ theme, onThemeToggle }) {
  const { logout } = useAuth();
  const items = [
    ["overview", "Vue globale", Home],
    ["clients", "Clients a risque", Users],
    ["agentic", "Analyse agentic", Brain],
    ["actions", "Actions recommandees", Target],
    ["reports", "Rapports agentic", FileText],
    ["imports", "Historique imports", CloudUpload],
    ["settings", "Paramètres", Settings],
  ];

  return (
    <aside className="bdx-sidebar">
      <div className="bdx-side-brand">
        <img src="/tt-logo.png" alt="Tunisie Telecom" />
      </div>
      <nav className="bdx-side-nav">
        {items.map(([key, label, Icon]) => (
          <NavLink key={key} to={`/dashboard/bad-debts/${key}`} title={label}>
            <Icon size={18} />
            <span className="bdx-side-label">{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="bdx-side-bottom">
        <button type="button" onClick={onThemeToggle} title="Mode clair/sombre">
          {theme === "dark" ? <Moon size={18} /> : <Sun size={18} />}
          <span className="bdx-side-label">Mode clair/sombre</span>
        </button>
        <NavLink to="/dashboard" title="Accueil">
          <Home size={18} />
          <span className="bdx-side-label">Accueil</span>
        </NavLink>
        <button type="button" onClick={logout} title="Déconnexion">
          <LogOut size={18} />
          <span className="bdx-side-label">Déconnexion</span>
        </button>
      </div>
    </aside>
  );
}

function BadDebtsHeader({ view }) {
  const title = view === "overview" ? "Tableau de bord de pilotage des créances à risque" : (VIEW_META[view] || VIEW_META.overview);
  return (
    <header className="bdx-header">
      <h1>{title}</h1>
    </header>
  );
}

function ViewRenderer({ view, context }) {
  if (view === "overview") return <OverviewPage {...context} />;
  if (view === "clients") return <RiskClientsPage {...context} />;
  if (view === "agentic") return <AgenticAnalysisPage {...context} />;
  if (view === "actions") return <RecommendedActionsPage {...context} />;
  if (view === "reports") return <AgenticReportsPage reports={context.reports} />;
  if (view === "imports") return <ImportHistoryPage imports={context.imports} />;
  return <SettingsPage />;
}

function OverviewPage({ summary, clients, actions, reports, headerNode }) {
  const navigate = useNavigate();
  const [activeRisk, setActiveRisk] = useState(null);
  const [activeCluster, setActiveCluster] = useState(null);
  const [activeScoreCluster, setActiveScoreCluster] = useState(null);
  const [activeDebtRisk, setActiveDebtRisk] = useState(null);
  const tierRows = buildTierRows(summary);
  const clusterRows = buildClusterRows(summary);
  const scoreValue = summary?.avg_final_risk_score ?? 0.242;
  const scoreRows = buildScoreRows();
  const highRiskCount = summary?.high_risk_count ?? 1233;
  const kpis = [
    ["Total clients scorés", summary?.total_clients ?? 9748, Users, "blue"],
    ["Clients à risque", summary?.at_risk_count ?? 3430, TrendingDown, "violet", 0, "/dashboard/bad-debts/clients"],
    ["Risque élevé", highRiskCount, ShieldAlert, "pink", 0, "/dashboard/bad-debts/clients"],
    ["Anomalies détectées", summary?.anomaly_count ?? 277, AlertTriangle, "orange"],
    ["Score moyen", scoreValue, Gauge, "green", 3],
    ["Actions agentic générées", actions?.length || 50, Zap, "sunset", 0, "/dashboard/bad-debts/actions"],
  ];

  return (
    <div className="bdx-view bdx-overview">
      <section className="bdx-overview-kpi-grid" aria-label="Indicateurs Bad Debts">
        {kpis.map(([label, value, Icon, tone, decimals, to], index) => <KpiCard key={label} label={label} value={value} icon={Icon} tone={tone} index={index} decimals={decimals} onClick={to ? () => navigate(to) : undefined} />)}
      </section>

      <div className="bdx-overview-main">
        {headerNode}
        <section className="bdx-chart-grid">
          <Panel title="Répartition du risque" meta="Population ML">
            <DonutChart rows={tierRows} total={summary?.total_clients || 9748} active={activeRisk} onActiveChange={setActiveRisk} />
          </Panel>
          <Panel title="Risque par cluster" meta="Nombre de clients">
            <VerticalBars rows={clusterRows} active={activeCluster} onActiveChange={setActiveCluster} onSelect={(row) => navigate(`/dashboard/bad-debts/clients?cluster=${encodeURIComponent(row.label)}`)} />
          </Panel>
          <Panel title="Score moyen par cluster">
            <HorizontalBars rows={scoreRows} active={activeScoreCluster} onActiveChange={setActiveScoreCluster} />
          </Panel>
          <Panel title="Dette moyenne par niveau de risque">
            <RadialDebt active={activeDebtRisk} onActiveChange={setActiveDebtRisk} />
          </Panel>
        </section>
      </div>

    </div>
  );
}

function RiskClientsPage({ clients, clientsLoading, loadClients, runAgent, agentLoadingMsisdn }) {
  const navigate = useNavigate();
  const [filters, setFilters] = useState({ risk_tier: "high", search: "", is_anomaly: "", cluster_name: "" });
  const rows = clients.items || [];

  function apply(next = filters) {
    const params = Object.fromEntries(Object.entries(next).filter(([, value]) => value !== ""));
    loadClients(params);
  }

  return (
    <div className="bdx-view">
      <Panel title="Filtres rapides" meta="Segments operationnels">
        <div className="bdx-pill-row">
          {[
            ["Priorite du jour", { risk_tier: "high" }],
            ["High risk", { risk_tier: "high" }],
            ["Avec anomalie", { is_anomaly: true }],
            ["Blacklist / Disconnected", { search: "DISCONNECTED" }],
            ["Sans action", {}],
            ["Deja traites recemment", {}],
          ].map(([label, next]) => <button key={label} className="bdx-pill" type="button" onClick={() => apply({ ...filters, ...next })}>{label}</button>)}
        </div>
      </Panel>

      <Panel title="Filtres avances" meta="Recherche et scoring">
        <div className="bdx-filter-grid">
          <select value={filters.risk_tier} onChange={(event) => setFilters({ ...filters, risk_tier: event.target.value })}>
            <option value="">Tous niveaux</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
          </select>
          <input value={filters.cluster_name} onChange={(event) => setFilters({ ...filters, cluster_name: event.target.value })} placeholder="Cluster" />
          <select value={filters.is_anomaly} onChange={(event) => setFilters({ ...filters, is_anomaly: event.target.value })}>
            <option value="">Anomalie</option><option value="true">Oui</option><option value="false">Non</option>
          </select>
          <input placeholder="Score minimum" />
          <input placeholder="Dette minimum (TND)" />
          <label className="bdx-search"><Search size={16} /><input value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} placeholder="Recherche MSISDN" /></label>
          <button className="bdx-button ghost" type="button" onClick={() => { const reset = { risk_tier: "high", search: "", is_anomaly: "", cluster_name: "" }; setFilters(reset); apply(reset); }}><RotateCcw size={16} />Reinitialiser</button>
          <button className="bdx-button primary" type="button" onClick={() => apply()}><RefreshCw size={16} />Filtrer</button>
        </div>
      </Panel>

      <Panel title="Clients a risque" meta={`${formatNumber(clients.total)} clients`}>
        {clientsLoading ? <InlineLoading /> : (
          <div className="bdx-table-wrap">
            <table className="bdx-table wide">
              <thead><tr><th>Client</th><th>Cluster</th><th>Risque</th><th>Score</th><th>Dette (TND)</th><th>Remboursement</th><th>Anomalie</th><th>Action recommandee</th><th>Priorite</th><th>Statut</th><th>Derniere action</th><th>Actions</th></tr></thead>
              <tbody>{rows.map((client) => (
                <tr key={client.msisdn}>
                  <td><ClientCell value={client.msisdn} /></td>
                  <td>{client.cluster_name || "-"}</td>
                  <td><Badge tone={normalizeTier(client.risk_tier)}>{tierLabel(client.risk_tier)}</Badge></td>
                  <td><ScoreBar score={client.final_risk_score} /></td>
                  <td>{formatNumber(client.total_outstanding_amount)}</td>
                  <td>{formatPercent(client.avg_reimburse_ratio)}</td>
                  <td>{client.is_anomaly ? <Badge tone="orange">Oui</Badge> : <Badge>Non</Badge>}</td>
                  <td>{client.risk_tier === "high" ? "Revue recouvrement" : "Rappel paiement"}</td>
                  <td><Badge tone={client.risk_tier === "high" ? "high" : "medium"}>{client.risk_tier === "high" ? "Priorite 1" : "Priorite 2"}</Badge></td>
                  <td><Badge tone="blue">A suivre</Badge></td>
                  <td>-</td>
                  <td><div className="bdx-row-actions"><button onClick={() => navigate(`/dashboard/bad-debts/client/${client.msisdn}`)}><Eye size={15} />Voir detail</button><button onClick={() => runAgent(client.msisdn)} disabled={agentLoadingMsisdn === client.msisdn}>{agentLoadingMsisdn === client.msisdn ? <Loader2 className="spin" size={15} /> : <Bot size={15} />}Lancer agent</button></div></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

function AgenticAnalysisPage({ actions, refreshDashboard }) {
  const [tier, setTier] = useState("high");
  const [limit, setLimit] = useState(5);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function runBatch() {
    setLoading(true);
    setError("");
    try {
      const response = await runBadDebtsAgentBatch({ tier, limit });
      setResult(response.data);
      await refreshDashboard();
    } catch (err) {
      setError(getApiError(err, "Impossible de lancer l'analyse agentic globale."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bdx-view">
      {error && <div className="bdx-alert"><AlertTriangle size={18} />{error}</div>}
      <Panel title="Analyse agentic globale" meta="Traitement batch avec rapport PostgreSQL">
        <div className="bdx-agentic-hero">
          <div><Sparkles size={32} /><h2>Lancer une analyse des clients les plus a risque</h2><p>Le moteur agentic genere les actions recommandees, reutilise les actions recentes et cree un rapport metier.</p></div>
          <div className="bdx-agentic-controls">
            <label>Niveau de risque<select value={tier} onChange={(event) => setTier(event.target.value)}><option value="high">Eleve</option><option value="medium">Moyen</option></select></label>
            <label>Nombre de clients<select value={limit} onChange={(event) => setLimit(Number(event.target.value))}><option value={5}>5</option><option value={10}>10</option><option value={50}>50</option></select></label>
            <button className="bdx-button primary big" type="button" onClick={runBatch} disabled={loading}>{loading ? <Loader2 className="spin" size={18} /> : <Play size={18} />}Lancer l'analyse</button>
          </div>
        </div>
      </Panel>

      {result && <BatchBusinessResult result={result} />}
      {!result && <PreviewList title="Dernieres actions recommandees" items={actions.slice(0, 5).map((action) => ({ title: actionLabel(action.action_type), meta: `${action.msisdn} - ${formatDate(action.created_at)}` }))} />}
    </div>
  );
}

function BatchBusinessResult({ result }) {
  const stats = [["Clients analyses", result.clients_analyzed], ["Actions creees", result.actions_created], ["Actions reutilisees", result.actions_reused], ["Erreurs", result.errors_count], ["Rapport genere", result.report_id ? "Oui" : "Non"]];
  return (
    <Panel title="Resultats de l'analyse" meta={result.status}>
      <div className="bdx-result-cards">{stats.map(([label, value]) => <div className="bdx-result-card" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      {result.report_id && <div className="bdx-report-success"><CheckCircle2 size={18} /><div><strong>Rapport agentic genere avec succes</strong><p>{result.report_summary}</p></div></div>}
      <div className="bdx-table-wrap">
        <table className="bdx-table">
          <thead><tr><th>Client</th><th>Priorite</th><th>Decision recommandee</th><th>Traitement</th><th>Commentaire</th></tr></thead>
          <tbody>{(result.items || []).map((item, index) => <tr key={`${item.msisdn}-${index}`}><td><ClientCell value={item.client_label || item.msisdn} /></td><td>{item.priority_label || "Priorite standard"}</td><td>{item.action_label || actionLabel(item.action_type)}</td><td><Badge tone={item.status === "failed" ? "high" : item.status === "reused" ? "medium" : "low"}>{item.processing_label || item.status}</Badge></td><td>{item.business_comment || "-"}{item.error && <small className="bdx-error-note">{item.error}</small>}</td></tr>)}</tbody>
        </table>
      </div>
    </Panel>
  );
}

function RecommendedActionsPage({ actions }) {
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const rows = actions.filter((action) => String(action.msisdn || "").includes(search));
  return (
    <div className="bdx-view">
      <Panel title="Filtres actions" meta="Traitement operationnel">
        <div className="bdx-filter-grid compact"><select><option>Type d'action</option></select><select><option>Priorite</option></select><select><option>Statut</option></select><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Recherche client" /><input type="date" /><button className="bdx-button ghost"><Download size={16} />Exporter CSV</button></div>
      </Panel>
      <Panel title="Actions recommandees" meta={`${rows.length} actions recentes`}>
        <div className="bdx-table-wrap"><table className="bdx-table"><thead><tr><th>Client</th><th>Action recommandee</th><th>Priorite</th><th>Statut</th><th>Date creation</th><th>Commentaire</th><th>Actions</th></tr></thead><tbody>{rows.map((action) => <tr key={`${action.id}-${action.msisdn}`}><td><ClientCell value={action.msisdn} /></td><td>{actionLabel(action.action_type)}</td><td><Badge tone={Number(action.priority) === 1 ? "high" : "medium"}>Priorite {action.priority}</Badge></td><td><Badge tone="blue">{STATUS_LABELS[action.status] || action.status}</Badge></td><td>{formatDate(action.created_at)}</td><td>{action.recommendation || "Action agentic recommandee."}</td><td><div className="bdx-row-actions"><button onClick={() => navigate(`/dashboard/bad-debts/client/${action.msisdn}`)}>Voir client</button><button>Traitee</button><button>Ignorer</button></div></td></tr>)}</tbody></table></div>
      </Panel>
    </div>
  );
}

function AgenticReportsPage({ reports }) {
  const [selected, setSelected] = useState(reports[0] || null);
  useEffect(() => { if (!selected && reports[0]) setSelected(reports[0]); }, [reports, selected]);
  return (
    <div className="bdx-view bdx-reports-layout">
      <Panel title="Rapports agentic" meta={`${reports.length} rapports`}>
        <div className="bdx-report-list">{reports.map((report) => <button className={`bdx-report-item ${selected?.id === report.id ? "active" : ""}`} key={report.id} type="button" onClick={() => setSelected(report)}><FileText size={18} /><div><strong>{report.summary || "Rapport Bad Debts"}</strong><span>{formatDate(report.generated_at)}</span></div><MoreHorizontal size={16} /></button>)}</div>
      </Panel>
      <Panel title="Detail rapport" meta={selected ? formatDate(selected.generated_at) : "Selection"}>
        {selected ? <ReportDetail report={selected} /> : <p className="bdx-empty">Aucun rapport disponible.</p>}
      </Panel>
    </div>
  );
}

function ReportDetail({ report }) {
  const kpis = report.kpis_json || {};
  return (
    <div className="bdx-report-detail">
      <InfoGrid rows={[["Type", report.report_type], ["Date", formatDate(report.generated_at)], ["Clients analyses", kpis.clients_analyzed], ["Actions creees", kpis.actions_created], ["Statut", kpis.status]]} />
      <div className="bdx-text-block"><h3>Resume</h3><p>{report.summary || "-"}</p></div>
      <div className="bdx-text-block"><h3>Recommandations</h3><p>{report.recommendations || "-"}</p></div>
      <div className="bdx-row-actions"><button><Eye size={15} />Voir detail</button><button><FileDown size={15} />PDF</button><button><Download size={15} />CSV</button><button><Printer size={15} />Imprimer</button></div>
    </div>
  );
}

function ImportHistoryPage({ imports }) {
  return (
    <div className="bdx-view">
      <Panel title="Historique imports ML" meta={`${imports.length} derniers imports`}>
        <div className="bdx-table-wrap"><table className="bdx-table"><thead><tr><th>Fichier importe</th><th>Lignes importees</th><th>Statut</th><th>Date</th><th>Message</th></tr></thead><tbody>{imports.map((item) => <tr key={item.id}><td>{item.file_name}</td><td>{formatNumber(item.rows_imported)}</td><td><Badge tone={item.status === "success" ? "low" : "medium"}>{item.status}</Badge></td><td>{formatDate(item.imported_at)}</td><td>{item.error_message || "-"}</td></tr>)}</tbody></table></div>
      </Panel>
    </div>
  );
}

function BadDebtsClientDetailPage({ msisdn }) {
  const navigate = useNavigate();
  const [theme, setTheme] = useState(() => localStorage.getItem(BAD_DEBTS_THEME_KEY) || "dark");
  const [client, setClient] = useState(null);
  const [agentResult, setAgentResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [agentLoading, setAgentLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { localStorage.setItem(BAD_DEBTS_THEME_KEY, theme); }, [theme]);
  useEffect(() => { loadDetail(); }, [msisdn]);

  async function loadDetail() {
    setLoading(true);
    try {
      const response = await getBadDebtsClientDetail(msisdn);
      setClient(response.data);
    } catch (err) {
      setError(getApiError(err, "Impossible de charger le detail client."));
    } finally {
      setLoading(false);
    }
  }

  async function runAgentForClient() {
    setAgentLoading(true);
    try {
      const response = await runBadDebtsAgent(msisdn);
      setAgentResult(response.data);
      await loadDetail();
    } catch (err) {
      setError(getApiError(err, "Impossible de lancer l'agent."));
    } finally {
      setAgentLoading(false);
    }
  }

  return (
    <div className={`bdx-shell ${theme === "light" ? "is-light" : "is-dark"}`}>
      <BadDebtsSidebar theme={theme} onThemeToggle={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} />
      <main className="bdx-main">
        <BadDebtsHeader view="clients" />
        {error && <div className="bdx-alert"><AlertTriangle size={18} />{error}</div>}
        {loading ? <InlineLoading /> : <ClientDetailContent client={client} agentResult={agentResult} onBack={() => navigate("/dashboard/bad-debts/clients")} onRunAgent={runAgentForClient} agentLoading={agentLoading} />}
      </main>
    </div>
  );
}

function ClientDetailContent({ client, agentResult, onBack, onRunAgent, agentLoading }) {
  if (!client) return <p className="bdx-empty">Client introuvable.</p>;
  const drivers = Array.isArray(client.top_drivers) ? client.top_drivers : client.top_drivers ? [client.top_drivers] : [];
  const latestAction = agentResult?.decision || client.actions?.[0] || {};
  return (
    <div className="bdx-view">
      <div className="bdx-detail-actions"><button className="bdx-button ghost" onClick={onBack}><ArrowLeft size={16} />Retour</button><button className="bdx-button primary" onClick={onRunAgent} disabled={agentLoading}>{agentLoading ? <Loader2 className="spin" size={16} /> : <Bot size={16} />}Lancer agent</button><button className="bdx-button ghost"><Printer size={16} />Imprimer</button><button className="bdx-button ghost"><FileDown size={16} />PDF</button></div>
      <section className="bdx-detail-grid">
        <Panel title="Profil client" meta={client.msisdn}><InfoGrid rows={[["MSISDN", client.msisdn], ["Etat", client.state], ["Cluster", client.cluster_name], ["Risque", tierLabel(client.risk_tier)], ["Score", formatScore(client.final_risk_score)], ["Label", client.risk_label], ["Anomalie", client.is_anomaly ? "Oui" : "Non"]]} /></Panel>
        <Panel title="Indicateurs comportementaux" meta="Usage SOS"><InfoGrid rows={[["Nombre SOS", client.nb_sos], ["Credit moyen", formatNumber(client.avg_credit_amount)], ["Encours restant", formatNumber(client.total_outstanding_amount)], ["Ratio remboursement", formatPercent(client.avg_reimburse_ratio)], ["Dette / credit", formatScore(client.debt_to_credit)], ["Anciennete", formatNumber(client.tenure_days)], ["Jamais rembourse", client.never_repaid ? "Oui" : "Non"], ["Bon rembourseur", client.full_repayer ? "Oui" : "Non"], ["Dormant", client.is_dormant_like ? "Oui" : "Non"]]} /></Panel>
      </section>
      <Panel title="Facteurs explicatifs" meta="Top drivers">{drivers.length ? <div className="bdx-driver-list">{drivers.slice(0, 8).map((driver, index) => <div className="bdx-driver-row" key={`${driver?.feature || driver}-${index}`}><div><strong>{driver?.feature || driver?.name || String(driver)}</strong><span>{driver?.z_score !== undefined ? `z=${formatScore(driver.z_score)}` : "Signal ML"}</span></div><i><b style={{ width: `${Math.max(22, 92 - index * 9)}%` }} /></i></div>)}</div> : <p className="bdx-empty">Aucun facteur structure disponible.</p>}</Panel>
      <section className="bdx-detail-grid"><Panel title="Recommandation agentic" meta="Decision"><InfoGrid rows={[["Decision", actionLabel(latestAction.action_type || latestAction.recommended_action)], ["Priorite", latestAction.priority ? `Priorite ${latestAction.priority}` : "-"], ["Commentaire", latestAction.reason || latestAction.recommendation || "Lancer l'agent pour generer une recommandation actualisee."]]} /></Panel><Panel title="Historique client" meta="Dernieres actions"><RecentActionMini actions={client.actions || []} /></Panel></section>
    </div>
  );
}

function SettingsPage() {
  return (
    <div className="bdx-view"><Panel title="Parametres Bad Debts" meta="Preferences locales"><p className="bdx-empty">Le mode clair / sombre est sauvegarde dans localStorage. Les autres parametres operationnels seront branches plus tard.</p></Panel></div>
  );
}

function KpiCard({ label, value, icon: Icon, tone, index, decimals = 0, onClick }) {
  const Tag = onClick ? "button" : "article";
  return <Tag className={`bdx-kpi ${tone} ${onClick ? "is-clickable" : ""}`} type={onClick ? "button" : undefined} onClick={onClick} style={{ "--delay": `${index * 65}ms` }}><div className="bdx-kpi-icon"><Icon size={28} /></div><span>{label}</span><strong><CountUp value={value} decimals={decimals} /></strong></Tag>;
}

function CountUp({ value, decimals = 0 }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) { setDisplay(value); return; }
    let rafId;
    const duration = 1000;
    const start = performance.now();
    const tick = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const next = numeric * eased;
      setDisplay(decimals > 0 ? Number(next.toFixed(decimals)) : Math.round(next));
      if (progress < 1) rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [value, decimals]);
  if (typeof display === "string") return display;
  if (decimals > 0) return Number(display).toFixed(decimals);
  return formatNumber(display);
}

function Panel({ title, meta, children }) {
  return <section className="bdx-panel"><div className="bdx-panel-head"><div><h2>{title}</h2>{meta && <p>{meta}</p>}</div></div>{children}</section>;
}

function ChartInfo({ children }) {
  return <div className="bdx-chart-note">{children}</div>;
}

function DonutChart({ rows, total, active, onActiveChange }) {
  const safeTotal = rows.reduce((sum, row) => sum + Number(row.value || 0), 0) || total || 1;
  let offset = 25;
  const segments = rows.map((row) => { const length = (Number(row.value || 0) / safeTotal) * 100; const segment = { ...row, length, offset }; offset -= length; return segment; });
  const activeRow = active ? segments.find((row) => row.tier === active) : null;
  const centerValue = activeRow?.value ?? total;
  const centerLabel = activeRow?.label ?? "Total";
  const tooltipStyle = activeRow ? getDonutTooltipPosition(activeRow.tier) : undefined;
  return (
    <div className="bdx-donut-wrap" onMouseLeave={() => onActiveChange(null)}>
      <svg viewBox="0 0 42 42">
        {segments.map((row) => (
          <circle
            key={row.tier}
            className={`bdx-donut-segment ${row.tier} ${active === row.tier ? "is-active" : ""}`}
            cx="21"
            cy="21"
            r="15.9"
            strokeDasharray={`${row.length} ${100 - row.length}`}
            strokeDashoffset={row.offset}
            onMouseEnter={() => onActiveChange(row.tier)}
          />
        ))}
      </svg>
      <div className="bdx-donut-center"><strong>{formatNumber(centerValue)}</strong><span>{centerLabel}</span></div>
      {activeRow && (
        <div className={`bdx-donut-tooltip ${activeRow.tier}`} style={tooltipStyle}>
          <strong>{activeRow.label}</strong>
          <span>{formatNumber(activeRow.value)} clients</span>
          <span>{activeRow.length.toFixed(1)}%</span>
        </div>
      )}
      <div className="bdx-legend">{segments.map((row) => <span className={active === row.tier ? "is-active" : ""} key={row.tier} onMouseEnter={() => onActiveChange(row.tier)}><i className={row.tier} /><em>{row.label}</em><strong>{formatNumber(row.value)}</strong><small>{row.length.toFixed(1)} %</small></span>)}</div>
    </div>
  );
}

function getDonutTooltipPosition(tier) {
  const positions = {
    low: { "--tip-left": "78px", "--tip-top": "20px" },
    medium: { "--tip-left": "122px", "--tip-top": "112px" },
    high: { "--tip-left": "30px", "--tip-top": "112px" },
  };
  return positions[tier] || positions.low;
}

function VerticalBars({ rows, active, onActiveChange, onSelect }) {
  const total = rows.reduce((sum, row) => sum + Number(row.value || 0), 0) || 1;
  return (
    <div className="bdx-vbars cluster-chart" onMouseLeave={() => onActiveChange(null)}>
      <div className="bdx-vbars-plot cluster-bars">
        {rows.map((row, index) => {
          const height = Math.max(Number(row.percent || 0), Number(row.value) > 0 ? 3 : 0);
          const share = (Number(row.value || 0) / total) * 100;
          return (
            <button className={`cluster-bar-item ${active === row.label ? "is-active" : ""}`} key={row.label} type="button" onMouseEnter={() => onActiveChange(row.label)} onClick={() => onSelect?.(row)}>
              <span className="cluster-bar-value">{formatNumber(row.value)}</span>
              <span className="bdx-vbar-track cluster-bar">
                <i className="cluster-bar-fill" style={{ height: `${height}%`, "--delay": `${index * 70}ms` }} />
              </span>
              <strong className="cluster-bar-label">{row.label}</strong>
              <span className="cluster-tooltip" role="presentation">
                <b>{row.label}</b>
                <small>Clients : {formatNumber(row.value)}</small>
                <small>Part : {share.toFixed(1)} %</small>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function HorizontalBars({ rows, active, onActiveChange }) {
  return (
    <div className="bdx-hbars score-cluster-list" onMouseLeave={() => onActiveChange(null)}>
      {rows.map((row, index) => (
        <button className={`score-cluster-row ${active === row.label ? "is-active" : ""}`} type="button" key={row.label} onMouseEnter={() => onActiveChange(row.label)}>
          <span className="score-cluster-label">{row.label}</span>
          <span className="score-cluster-track"><i className="score-cluster-fill" style={{ width: `${row.percent}%`, "--delay": `${index * 60}ms` }} /></span>
          <strong className="score-cluster-value">{Number(row.value).toFixed(3)}</strong>
          <span className="score-cluster-tooltip" role="presentation">
            <b>{row.label}</b>
            <small>Score moyen : {Number(row.value).toFixed(3)}</small>
          </span>
        </button>
      ))}
    </div>
  );
}

function RadialDebt({ active, onActiveChange }) {
  const rows = [
    { label: "Faible", value: 24.6, tone: "low", radius: 64, color: "#17D5E8" },
    { label: "Moyen", value: 53.8, tone: "medium", radius: 52, color: "#8B3FF2" },
    { label: "Élevé", value: 112.7, tone: "high", radius: 40, color: "#F72585" },
  ];
  const maxValue = Math.max(...rows.map((row) => row.value), 1);
  const activeRow = active ? rows.find((row) => row.label === active) : null;
  const mainRow = rows[rows.length - 1];
  const centerRow = activeRow || mainRow;
  const centerLabel = activeRow ? activeRow.label : "Risque élevé";
  return (
    <div className="debt-radial-card" onMouseLeave={() => onActiveChange(null)}>
      <div className="debt-radial-chart">
        <svg viewBox="0 0 160 160" aria-label="Dette moyenne par niveau de risque">
          {rows.map((row, index) => {
            const circumference = 2 * Math.PI * row.radius;
            const dashOffset = circumference * (1 - row.value / maxValue);
            return (
              <g className={`debt-ring ${row.tone} ${active === row.label ? "is-active" : ""}`} key={row.label}>
                <circle className="debt-ring-track" cx="80" cy="80" r={row.radius} />
                <circle
                  className="debt-ring-value"
                  cx="80"
                  cy="80"
                  r={row.radius}
                  strokeDasharray={circumference}
                  strokeDashoffset={dashOffset}
                  style={{ "--ring-color": row.color, "--ring-delay": `${index * 110}ms` }}
                  onMouseEnter={() => onActiveChange(row.label)}
                />
              </g>
            );
          })}
        </svg>
        <div className="debt-radial-center">
          <strong>{centerRow.value.toFixed(1)}</strong>
          <span>TND</span>
          <small>{centerLabel}</small>
        </div>
      </div>
      <div className="debt-risk-cards">
        {rows.map((row, index) => (
          <button className={`debt-risk-mini-card ${row.tone}`} type="button" key={row.label} onMouseEnter={() => onActiveChange(row.label)}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div>
              <strong>{row.label}</strong>
              <small>{row.value.toFixed(1)} TND</small>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function PreviewList({ title, items = [], to }) {
  const content = <div className="bdx-preview-list"><h3>{title}</h3>{items.length ? items.map((item, index) => <div className="bdx-preview-row" key={`${item.title}-${index}`}><span>{index + 1}</span><div><strong>{item.title}</strong><small>{item.meta}</small></div></div>) : <p className="bdx-empty">Aucune donnee disponible.</p>}{to && <span className="bdx-linkish">Voir tout</span>}</div>;
  return to ? <NavLink className="bdx-preview-link" to={to}>{content}</NavLink> : content;
}

function ClientCell({ value }) {
  return <div className="bdx-client-cell"><span>{initials(value)}</span><strong>{value}</strong></div>;
}

function Badge({ tone = "neutral", children }) {
  return <span className={`bdx-badge ${tone}`}>{children}</span>;
}

function ScoreBar({ score }) {
  return <div className="bdx-score"><strong>{formatScore(score)}</strong><i><b style={{ width: `${toPercent(score)}%` }} /></i></div>;
}

function InfoGrid({ rows }) {
  return <div className="bdx-info-grid">{rows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value ?? "-"}</strong></div>)}</div>;
}

function RecentActionMini({ actions }) {
  return actions.length ? <div className="bdx-action-mini">{actions.map((action) => <div key={`${action.id}-${action.created_at}`}><strong>{actionLabel(action.action_type)}</strong><span>{formatDate(action.created_at)} - {STATUS_LABELS[action.status] || action.status}</span></div>)}</div> : <p className="bdx-empty">Aucune action recente.</p>;
}

function InlineLoading() {
  return <div className="bdx-loading"><Loader2 className="spin" size={22} />Chargement...</div>;
}

function buildTierRows(summary) {
  const byTier = summary?.by_tier || {};
  const fallback = { low: 6318, medium: 2197, high: 1233 };
  const total = Math.max(summary?.total_clients || 9748, 1);
  return ["low", "medium", "high"].map((tier) => {
    const value = byTier[tier] ?? fallback[tier];
    return { tier, label: TIER_LABELS[tier], value, percent: (Number(value) / total) * 100 };
  });
}

function buildClusterRows(summary) {
  const source = Object.keys(summary?.by_cluster_name || {}).length
    ? summary.by_cluster_name
    : { Standard: 6602, "Bon-payeur": 2606, SUSPENDED: 497, DISCONNECTED: 28, "ON-HOLD": 15 };
  const entries = Object.entries(source).slice(0, 5);
  const max = Math.max(...entries.map(([, value]) => Number(value)), 1);
  return entries.map(([label, value]) => ({ label, value, percent: (Number(value) / max) * 100 }));
}

function buildScoreRows() {
  const rows = [
    ["DISCONNECTED", 0.812],
    ["SUSPENDED", 0.674],
    ["ON-HOLD", 0.523],
    ["Standard", 0.312],
    ["Bon-payeur", 0.156],
  ];
  return rows.map(([label, value]) => ({ label, value, percent: value * 100 }));
}
