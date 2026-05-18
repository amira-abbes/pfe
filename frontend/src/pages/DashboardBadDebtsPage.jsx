import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  CloudUpload,
  FileDown,
  FileText,
  Gauge,
  Home,
  Loader2,
  LogOut,
  Moon,
  Printer,
  RotateCcw,
  Search,
  Settings,
  ShieldAlert,
  Sun,
  TrendingDown,
  Users,
  Zap,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Navigate, useNavigate, useParams } from "react-router-dom";

import {
  generateBadDebtsGlobalReport,
  getApiError,
  getBadDebtsAtRisk,
  getBadDebtsClients,
  getBadDebtsImportRuns,
  getBadDebtsSummary,
  runBadDebtsAgent,
  uploadBadDebtsRawImport,
} from "../api/api";
import { useAuth } from "../context/AuthContext";
import "../styles/bad-debts-dashboard.css";

const BAD_DEBTS_THEME_KEY = "badDebtsTheme";
const DEFAULT_CLIENT_FILTERS = { risk_tier: "", search: "", is_anomaly: "", cluster_name: "", action_type: "" };

const ACTION_LABELS = {
  call_center_priority: "Appel prioritaire centre de relation client",
  sms_retention_offer: "SMS personnalisé",
  monitor_only: "Suivi routine",
};

const TIER_LABELS = {
  high: "Élevé",
  medium: "Moyen",
  low: "Faible",
};

const SEGMENT_LABELS = {
  DISCONNECTED: "Déconnecté",
  SUSPENDED: "Suspendu",
  "ON-HOLD": "En attente",
  "Bon-payeur": "Bon payeur",
  Standard: "Standard",
};

const SEGMENT_OPTIONS = [
  ["", "Tous les segments"],
  ["Standard", "Standard"],
  ["Bon-payeur", "Bon payeur"],
  ["SUSPENDED", "Suspendu"],
  ["DISCONNECTED", "Déconnecté"],
  ["ON-HOLD", "En attente"],
];

const PRIORITY_LABELS = {
  1: "Très urgent",
  2: "Urgent",
  4: "Normal",
};

const IMPORT_STATUS_LABELS = {
  success: "Succès",
  failed: "Échec",
  error: "Erreur",
  EN_COURS: "En cours",
  SUCCES: "Succès",
  ECHEC: "Échec",
};

const VIEW_META = {
  overview: "Vue globale",
  clients: "Clients à risque",
  imports: "Historique imports",
  settings: "Paramètres",
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

function formatRatioPercent(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  const percent = numeric > 1 ? numeric : numeric * 100;
  return `${Math.round(percent)} %`;
}

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function normalizeTier(value) {
  const tier = String(value || "").toLowerCase();
  return ["high", "medium", "low"].includes(tier) ? tier : "";
}

function tierLabel(value) {
  return TIER_LABELS[normalizeTier(value)] || "Non classé";
}

function actionLabel(value) {
  return ACTION_LABELS[String(value || "")] || "Suivi routine";
}

function importStatusLabel(value) {
  return IMPORT_STATUS_LABELS[String(value || "")] || displayValue(value);
}

function segmentLabel(value) {
  return SEGMENT_LABELS[String(value || "")] || (value ? String(value) : "Segment non défini");
}

function priorityLabel(value) {
  return PRIORITY_LABELS[Number(value)] || "Normal";
}

function normalizeSummary(raw = {}) {
  const byTier = raw.by_tier || {};
  const high = raw.high_risk_count ?? byTier.high ?? 0;
  const medium = raw.medium_risk_count ?? byTier.medium ?? 0;
  const low = raw.low_risk_count ?? byTier.low ?? 0;
  return {
    ...raw,
    total_clients: raw.total_clients ?? raw.total_clients_scored ?? 0,
    high_risk_count: high,
    medium_risk_count: medium,
    low_risk_count: low,
    at_risk_count: raw.at_risk_count ?? Number(high || 0) + Number(medium || 0),
    anomaly_count: raw.anomaly_count ?? 0,
    by_tier: { low, medium, high, ...byTier },
    by_cluster_name: raw.by_cluster_name || {},
  };
}

function cleanBusinessText(value, fallback = "-") {
  if (!value) return fallback;
  return String(value)
    .replace(/LangGraph/gi, "analyse automatique")
    .replace(/local_llm/gi, "système")
    .replace(/deterministic_fallback/gi, "système")
    .replace(/fallback/gi, "système")
    .replace(/repaired/gi, "contrôlé")
    .replace(/Qwen/gi, "modèle métier")
    .replace(/Ollama/gi, "système")
    .replace(/DISCONNECTED/g, "Déconnecté")
    .replace(/SUSPENDED/g, "Suspendu")
    .replace(/ON-HOLD/g, "En attente")
    .replace(/\bterminee\b/gi, "terminée")
    .replace(/\beleve\b/gi, "élevé")
    .replace(/\belevee\b/gi, "élevée")
    .replace(/\bgenerees\b/gi, "générées")
    .replace(/\bgeneree\b/gi, "générée")
    .replace(/\breutilisees\b/gi, "réutilisées")
    .replace(/\breutilisee\b/gi, "réutilisée")
    .replace(/\banalyses\b/gi, "analysés")
    .replace(/\ba risque\b/gi, "à risque")
    .replace(/\bdeja\b/gi, "déjà")
    .replace(/\bclasses\b/gi, "classés")
    .replace(/\bdetectee\b/gi, "détectée")
    .replace(/\bdetectees\b/gi, "détectées")
    .replace(/\boperationnelle\b/gi, "opérationnelle")
    .replace(/\boperationnel\b/gi, "opérationnel")
    .replace(/\boperationnels\b/gi, "opérationnels")
    .replace(/\bpriorite\b/gi, "priorité")
    .replace(/\bverification\b/gi, "vérification")
    .replace(/\bechec\b/gi, "échec")
    .replace(/\beviter\b/gi, "éviter")
    .replace(/\bdoublons operationnels\b/gi, "doublons opérationnels")
    .replace(/\b1 actions générées\b/gi, "1 action générée")
    .replace(/\b1 actions réutilisées\b/gi, "1 action réutilisée")
    .replace(/\b1 clients analysés\b/gi, "1 client analysé");
}

function usefulClientFactors(values = []) {
  const blocked = new Set(["", "Signal ML disponible", "Signal client à vérifier"]);
  return [...new Set((Array.isArray(values) ? values : [])
    .map((item) => cleanBusinessText(item, ""))
    .filter((item) => item && !blocked.has(item) && !item.toLowerCase().includes("historique de remboursement") && !item.toLowerCase().includes("facteur explicatif")))]
    .slice(0, 5);
}

function displayValue(value, fallback = "Non disponible") {
  return value === null || value === undefined || value === "" ? fallback : value;
}

function boolLabel(value, fallback = "Non disponible") {
  if (value === null || value === undefined || value === "") return fallback;
  return value ? "Oui" : "Non";
}

function clientsTitle(filters) {
  const activeFilters = Object.entries(filters).filter(([, value]) => value !== "");
  if (activeFilters.length > 1) return "Clients filtrés du Service SOS Solde & Data";
  if (filters.search) return "Résultat de recherche client";
  if (filters.cluster_name) return `Clients du segment : ${segmentLabel(filters.cluster_name)}`;
  if (filters.is_anomaly === "true" || filters.is_anomaly === true) return "Clients avec anomalie détectée";
  if (filters.is_anomaly === "false" || filters.is_anomaly === false) return "Clients sans anomalie détectée";
  if (filters.risk_tier === "high") return "Clients à risque élevé";
  if (filters.risk_tier === "medium") return "Clients à risque moyen";
  if (filters.risk_tier === "low") return "Clients à risque faible";
  return "Clients du Service SOS Solde & Data";
}

function recommendedActionForClient(client = {}) {
  if (client.recommended_action || client.action_type) return client.recommended_action || client.action_type;
  const rawTier = normalizeTier(client.risk_tier) || "low";
  const effectiveTier = client.is_anomaly && rawTier === "medium" ? "high" : client.is_anomaly && rawTier === "low" ? "medium" : rawTier;
  if (effectiveTier === "high") return "call_center_priority";
  if (effectiveTier === "medium") return "sms_retention_offer";
  return "monitor_only";
}

function priorityForClient(client = {}) {
  if (client.priority) return client.priority;
  if (recommendedActionForClient(client) === "call_center_priority") return 1;
  if (recommendedActionForClient(client) === "sms_retention_offer") return 2;
  return 4;
}

function getClientsTableTitle(filters = {}) {
  if (filters.search) return "Résultats de recherche";
  const parts = [];
  if (filters.risk_tier) parts.push(`Clients à risque ${tierLabel(filters.risk_tier).toLowerCase()}`);
  if (filters.cluster_name) parts.push(`Segment ${segmentLabel(filters.cluster_name)}`);
  if (filters.action_type) parts.push(`Clients avec ${actionLabel(filters.action_type)}`);
  if (filters.is_anomaly === "true") parts.push("Clients avec anomalie");
  if (filters.is_anomaly === "false") parts.push("Clients sans anomalie");
  if (!parts.length) return "Clients du Service SOS Solde & Data";
  if (parts.length === 1) return parts[0];
  return "Clients filtrés";
}

function activeClientsFilterText(filters = {}) {
  const parts = [];
  if (filters.risk_tier) parts.push(`Risque ${tierLabel(filters.risk_tier).toLowerCase()}`);
  if (filters.cluster_name) parts.push(`Segment ${segmentLabel(filters.cluster_name)}`);
  if (filters.is_anomaly === "true") parts.push("Avec anomalie");
  if (filters.is_anomaly === "false") parts.push("Sans anomalie");
  if (filters.action_type) parts.push(`Action : ${actionLabel(filters.action_type)}`);
  if (filters.search) parts.push(`MSISDN : ${filters.search}`);
  return parts.length ? `Filtres actifs : ${parts.join(" · ")}` : "";
}

function clientActionOptions(rows = []) {
  const values = Array.from(new Set(rows.map((client) => recommendedActionForClient(client)).filter(Boolean)));
  const fallback = ["call_center_priority", "sms_retention_offer", "monitor_only"];
  return (values.length ? values : fallback).map((value) => [value, actionLabel(value)]);
}

function clientActionFilterOptions(clients = {}) {
  const options = clients.filter_options.recommended_actions;
  if (Array.isArray(options) && options.length) {
    return options.map((option) => ({
      value: option.value,
      label: actionLabel(option.value) || option.label,
    }));
  }
  return clientActionOptions(clients.items || []).map(([value, label]) => ({ value, label }));
}

function clientsTotalText(total = 0) {
  return `${formatNumber(total || 0)} clients`;
}

function clientsSummaryValue(clients = {}) {
  return clients.summary || {
    total_clients: clients.total || 0,
    high_risk_count: 0,
    average_score: null,
    average_reimburse_ratio: null,
    priority_actions_count: 0,
  };
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
  if (view === "client" && detailMsisdn) return <Navigate to="/dashboard/bad-debts/clients" replace />;
  if (!VIEW_META[view]) return <Navigate to="/dashboard/bad-debts/overview" replace />;

  return <BadDebtsWorkspace view={view} />;
}

function BadDebtsWorkspace({ view }) {
  const [theme, setTheme] = useState(() => localStorage.getItem(BAD_DEBTS_THEME_KEY) || "dark");
  const [summary, setSummary] = useState(null);
  const [clients, setClients] = useState({ items: [], total: 0, page: 1, page_size: 10, total_pages: 0 });
  const [imports, setImports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [clientsLoading, setClientsLoading] = useState(false);
  const [agentLoadingMsisdn, setAgentLoadingMsisdn] = useState("");
  const [agentFeedback, setAgentFeedback] = useState(null);
  const [globalReport, setGlobalReport] = useState(null);
  const [globalReportLoading, setGlobalReportLoading] = useState(false);
  const [globalReportLoadingStage, setGlobalReportLoadingStage] = useState("");
  const [globalReportError, setGlobalReportError] = useState("");
  const globalReportCacheRef = useRef(new Map());
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
      const [summaryResponse, clientsResponse, importsResponse] = await Promise.all([
        getBadDebtsSummary(),
        getBadDebtsAtRisk({ tier: "high", page: 1, page_size: 10 }),
        getBadDebtsImportRuns({ limit: 20 }),
      ]);
      setSummary(normalizeSummary(summaryResponse.data));
      setClients(clientsResponse.data || { items: [], total: 0, page: 1, page_size: 10, total_pages: 0 });
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
      setClients(response.data || { items: [], total: 0, page: 1, page_size: 10, total_pages: 0 });
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
      const response = await runBadDebtsAgent(msisdn);
      const decision = response.data.decision || {};
      const analysis = response.data.ai_analysis || {};
      const profile = response.data.profile || {};
      const contactMessage = response.data.message || {};
      setAgentFeedback({
        msisdn,
        action: decision.recommended_action_label || actionLabel(decision.action_type || decision.recommended_action),
        priority: decision.priority_label || priorityLabel(decision.priority),
        risk: profile.risk_tier || decision.effective_tier,
        effectiveTier: decision.effective_tier,
        rawRiskTier: decision.raw_risk_tier || profile.risk_tier,
        anomalyEscalated: Boolean(decision.anomaly_escalated),
        score: profile.final_risk_score,
        segment: profile.cluster_name || profile.state,
        debt: profile.total_outstanding_amount,
        reimbursement: profile.avg_reimburse_ratio,
        anomaly: Boolean(profile.is_anomaly),
        factors: usefulClientFactors(analysis.key_risk_factors),
        contact: {
          type: contactMessage.contact_type,
          title: contactMessage.title,
          text: contactMessage.message_text || contactMessage.content,
          notice: contactMessage.internal_notice,
          safeToSend: Boolean(contactMessage.safe_to_send),
        },
        reused: Boolean(response.data.reused_existing_analysis),
      });
    } catch (err) {
      setError("L’analyse métier assistée n'a pas pu être lancée. Veuillez réessayer.");
    } finally {
      setAgentLoadingMsisdn("");
    }
  }

  function buildGlobalReportPayload(activeFilters = {}) {
    const payload = {};
    if (activeFilters.risk_tier) payload.risk_tier = activeFilters.risk_tier;
    if (activeFilters.cluster_name) payload.cluster_name = activeFilters.cluster_name;
    if (activeFilters.is_anomaly !== "" && activeFilters.is_anomaly !== undefined && activeFilters.is_anomaly !== null) {
      payload.is_anomaly = activeFilters.is_anomaly === "true" || activeFilters.is_anomaly === true;
    }
    if (activeFilters.recommended_action || activeFilters.action_type) {
      payload.recommended_action = activeFilters.recommended_action || activeFilters.action_type;
    }
    if (activeFilters.search) payload.search = activeFilters.search;
    return payload;
  }

  function globalReportCacheKey(payload = {}) {
    return JSON.stringify(Object.keys(payload).sort().reduce((acc, key) => {
      acc[key] = payload[key];
      return acc;
    }, {}));
  }

  async function generateGlobalReport(activeFilters = {}) {
    if (globalReportLoading) return;
    const payload = buildGlobalReportPayload(activeFilters);
    const cacheKey = globalReportCacheKey(payload);
    if (globalReportCacheRef.current.has(cacheKey)) {
      setGlobalReportError("");
      setGlobalReport(globalReportCacheRef.current.get(cacheKey));
      return;
    }
    setGlobalReportLoading(true);
    setGlobalReportLoadingStage("Analyse des indicateurs...");
    setGlobalReportError("");
    setGlobalReport(null);
    const stages = [
      "Analyse des indicateurs...",
      "Rédaction de la synthèse métier...",
      "Contrôle de cohérence du rapport...",
    ];
    let stageIndex = 0;
    const stageTimer = window.setInterval(() => {
      setGlobalReportLoadingStage(stages[Math.min(stageIndex, stages.length - 1)]);
      stageIndex += 1;
    }, 18000);
    try {
      const response = await generateBadDebtsGlobalReport(payload);
      globalReportCacheRef.current.set(cacheKey, response.data);
      setGlobalReport(response.data || null);
    } catch (err) {
      setGlobalReportError("Le rapport global n'a pas pu être généré. Vérifiez la connexion et réessayez.");
    } finally {
      window.clearInterval(stageTimer);
      setGlobalReportLoadingStage("");
      setGlobalReportLoading(false);
    }
  }

  const context = {
    summary,
    clients,
    imports,
    loading,
    clientsLoading,
    agentLoadingMsisdn,
    agentFeedback,
    globalReport,
    globalReportLoading,
    globalReportLoadingStage,
    globalReportError,
    refreshDashboard,
    loadClients,
    runAgent,
    generateGlobalReport,
  };
  const headerNode = <BadDebtsHeader view={view} />;

  return (
    <div className={`bdx-shell ${theme === "light" ? "is-light" : "is-dark"}`}>
      <BadDebtsSidebar theme={theme} onThemeToggle={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} />
      <main className="bdx-main">
        {view !== "overview" && view !== "clients" && headerNode}
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
    ["clients", "Clients à risque", Users],
    ["imports", "Historique des imports", CloudUpload],
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
  if (view === "imports") return <ImportHistoryPage imports={context.imports} refreshDashboard={context.refreshDashboard} />;
  return <SettingsPage />;
}

function OverviewPage({ summary, clients, headerNode }) {
  const navigate = useNavigate();
  const [activeRisk, setActiveRisk] = useState(null);
  const [activeSegment, setActiveSegment] = useState(null);
  const [activeScoreSegment, setActiveScoreSegment] = useState(null);
  const [activeDebtRisk, setActiveDebtRisk] = useState(null);
  const tierRows = buildTierRows(summary);
  const segmentRows = buildSegmentRows(summary);
  const scoreValue = summary.avg_final_risk_score ?? 0;
  const scoreRows = buildScoreRows();
  const highRiskCount = summary.high_risk_count ?? 0;
  const kpis = [
    ["Total clients scorés", summary.total_clients ?? 0, Users, "blue"],
    ["Clients à risque", summary.at_risk_count ?? 0, TrendingDown, "violet", 0, "/dashboard/bad-debts/clients"],
    ["Risque élevé", highRiskCount, ShieldAlert, "pink", 0, "/dashboard/bad-debts/clients"],
    ["Anomalies détectées", summary.anomaly_count ?? 0, AlertTriangle, "orange"],
    ["Score moyen", scoreValue, Gauge, "green", 3],
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
            <DonutChart rows={tierRows} total={summary.total_clients || 0} active={activeRisk} onActiveChange={setActiveRisk} />
          </Panel>
          <Panel title="Risque par segment client" meta="Nombre de clients">
            <VerticalBars rows={segmentRows} active={activeSegment} onActiveChange={setActiveSegment} onSelect={(row) => navigate(`/dashboard/bad-debts/clientssegment=${encodeURIComponent(row.label)}`)} />
          </Panel>
          <Panel title="Score moyen par segment">
            <HorizontalBars rows={scoreRows} active={activeScoreSegment} onActiveChange={setActiveScoreSegment} />
          </Panel>
          <Panel title="Dette moyenne par niveau de risque">
            <RadialDebt active={activeDebtRisk} onActiveChange={setActiveDebtRisk} />
          </Panel>
        </section>
      </div>

    </div>
  );
}

function RiskClientsPage({
  clients,
  clientsLoading,
  loadClients,
  runAgent,
  agentLoadingMsisdn,
  agentFeedback,
  globalReport,
  globalReportLoading,
  globalReportLoadingStage,
  globalReportError,
  generateGlobalReport,
}) {
  const [filters, setFilters] = useState(DEFAULT_CLIENT_FILTERS);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [showGlobalReport, setShowGlobalReport] = useState(false);
  const globalReportRef = useRef(null);
  const searchDebounceRef = useRef(null);
  const rows = clients.items || [];
  const visibleRows = rows;
  const page = Math.max(Number(clients.page || 1), 1);
  const pageSize = Math.max(Number(clients.page_size || 10), 1);
  const totalPages = Math.max(Number(clients.total_pages || Math.ceil(Number(clients.total || 0) / pageSize)), 1);
  const tableTitle = getClientsTableTitle(filters);
  const activeFilters = activeClientsFilterText(filters);

  useEffect(() => {
    if (agentFeedback) setIsDrawerOpen(true);
  }, [agentFeedback]);

  useEffect(() => () => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
  }, []);

  function apply(next = filters, nextPage = 1) {
    const entries = Object.entries(next).map(([key, value]) => [key === "action_type" ? "recommended_action" : key, value]);
    const params = Object.fromEntries(entries.filter(([, value]) => value !== ""));
    loadClients({ ...params, page: nextPage, page_size: pageSize });
  }

  function clearSearchDebounce() {
    if (searchDebounceRef.current) {
      clearTimeout(searchDebounceRef.current);
      searchDebounceRef.current = null;
    }
  }

  function updateFilter(key, value) {
    const next = { ...filters, [key]: value };
    setFilters(next);
    if (key === "search") {
      clearSearchDebounce();
      searchDebounceRef.current = setTimeout(() => {
        apply(next, 1);
        searchDebounceRef.current = null;
      }, 400);
      return;
    }
    clearSearchDebounce();
    apply(next, 1);
  }

  function goToPage(nextPage) {
    apply(filters, nextPage);
  }

  function resetFilters() {
    const reset = DEFAULT_CLIENT_FILTERS;
    clearSearchDebounce();
    setFilters(reset);
    apply(reset, 1);
  }

  async function launchAgent(msisdn) {
    await runAgent(msisdn);
  }

  async function handleGenerateGlobalReport() {
    setShowGlobalReport(true);
    await generateGlobalReport(filters);
    setTimeout(() => {
      globalReportRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
  }

  function handlePrintGlobalReport() {
    window.print();
  }

  function handleDownloadGlobalReportPdf() {
    window.print();
  }

  return (
    <div className="bdx-view bad-debts-page">
      <h2 className="bad-debts-page-title">Clients à risque</h2>
      <BadDebtsFiltersCard filters={filters} actionOptions={clientActionFilterOptions(clients)} onChange={updateFilter} onReset={resetFilters} />
      <div className="bad-debts-global-report-bar no-print">
        <button
          className="bad-debts-btn primary global-report-btn"
          type="button"
          onClick={handleGenerateGlobalReport}
          disabled={globalReportLoading}
        >
          {globalReportLoading ? <Loader2 className="spin" size={16} /> : <FileText size={16} />}
          {globalReportLoading ? "Génération en cours..." : "Générer rapport global"}
        </button>
        {activeFilters && <span className="bad-debts-filter-scope-hint">{activeFilters}</span>}
      </div>
      <BadDebtsClientsKpis summary={clientsSummaryValue(clients)} />
      <BadDebtsClientsTable
        rows={visibleRows}
        loading={clientsLoading}
        title={tableTitle}
        meta={clientsTotalText(clients.total)}
        activeFilters={activeFilters}
        page={page}
        totalPages={totalPages}
        onPrev={() => goToPage(page - 1)}
        onNext={() => goToPage(page + 1)}
        onReset={resetFilters}
        onRunAgent={launchAgent}
        loadingMsisdn={agentLoadingMsisdn}
      />
      {showGlobalReport && (
        <div ref={globalReportRef} className="bad-debts-global-report-section">
          {globalReportError && (
            <div className="bdx-alert no-print"><AlertTriangle size={18} />{globalReportError}</div>
          )}
          {globalReportLoading && (
            <div className="bad-debts-global-report-loading">
              <Loader2 className="spin" size={24} />
              <div>
                <strong>Génération du rapport métier en cours</strong>
                <span>Le système analyse les indicateurs calculés et rédige une synthèse opérationnelle. Les priorités et recommandations sont validées avant affichage.</span>
                <ol className="global-report-loading-steps">
                  <li className={globalReportLoadingStage ? "active" : ""}>Analyse des indicateurs</li>
                  <li>Rédaction de la synthèse métier</li>
                  <li>Contrôle de cohérence</li>
                </ol>
              </div>
            </div>
          )}
          {!globalReportLoading && globalReport && (
            <GlobalReportPanel
              data={globalReport}
              onPrint={handlePrintGlobalReport}
              onDownloadPdf={handleDownloadGlobalReportPdf}
              onClose={() => setShowGlobalReport(false)}
            />
          )}
        </div>
      )}
      <BadDebtsAgentDrawer
        feedback={agentFeedback}
        open={isDrawerOpen && Boolean(agentFeedback)}
        onClose={() => setIsDrawerOpen(false)}
      />
    </div>
  );
}

function BadDebtsFiltersCard({ filters, actionOptions, onChange, onReset }) {
  return (
    <section className="bad-debts-filters-card">
      <div className="bad-debts-card-head">
        <div><h3>Filtres avancés</h3></div>
      </div>
      <div className="bad-debts-filter-grid">
        <label>Niveau de risque<select value={filters.risk_tier} onChange={(event) => onChange("risk_tier", event.target.value)}><option value="">Tous les niveaux</option><option value="low">Faible</option><option value="medium">Moyen</option><option value="high">Élevé</option></select></label>
        <label>Segment client<select value={filters.cluster_name} onChange={(event) => onChange("cluster_name", event.target.value)}>{SEGMENT_OPTIONS.map(([value, label]) => <option key={value || "all"} value={value}>{label}</option>)}</select></label>
        <label>Situation<select value={filters.is_anomaly} onChange={(event) => onChange("is_anomaly", event.target.value)}><option value="">Toutes les situations</option><option value="true">Avec anomalie</option><option value="false">Sans anomalie</option></select></label>
        <label>Action recommandée<select value={filters.action_type} onChange={(event) => onChange("action_type", event.target.value)}><option value="">Toutes les actions</option>{actionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        <label>Recherche MSISDN<span className="bad-debts-search"><Search size={16} /><input value={filters.search} onChange={(event) => onChange("search", event.target.value)} placeholder="2169..." /></span></label>
      </div>
      <div className="bad-debts-filter-actions">
        <button className="bad-debts-btn secondary" type="button" onClick={onReset}><RotateCcw size={16} />Réinitialiser</button>
      </div>
    </section>
  );
}

function BadDebtsClientsKpis({ summary }) {
  const cards = [
    ["Clients", formatNumber(summary.total_clients), Users, "clients", "Résultats filtrés"],
    ["Risque élevé", formatNumber(summary.high_risk_count), ShieldAlert, "high", "Niveau effectif élevé"],
    ["Score moyen", formatScore(summary.average_score), Gauge, "score", "Score ML filtré"],
    ["Remboursement moyen", formatRatioPercent(summary.average_reimburse_ratio), TrendingDown, "repay", "Ratio moyen"],
    ["Actions prioritaires", formatNumber(summary.priority_actions_count), Zap, "priority", "Appels prioritaires"],
  ];
  return (
    <section className="bad-debts-stats">
      {cards.map(([label, value, Icon, tone, hint]) => (
        <article className={`bad-debts-stat-card ${tone}`} key={label}>
          <span className="bad-debts-stat-icon"><Icon size={19} /></span>
          <div><p>{label}</p><strong>{value}</strong><small>{hint}</small></div>
        </article>
      ))}
    </section>
  );
}

function BadDebtsClientsTable({ rows, loading, title, meta, activeFilters, page, totalPages, onPrev, onNext, onReset, onRunAgent, loadingMsisdn }) {
  return (
    <section className="bad-debts-table-card">
      <div className="bad-debts-card-head table-head">
        <div><h3>{title}</h3><p>{meta}</p>{activeFilters && <small>{activeFilters}</small>}</div>
      </div>
      {loading ? <InlineLoading /> : (
        rows.length ? (
          <>
            <div className="bad-debts-table-wrap">
              <table className="bad-debts-table">
                <thead><tr><th>Client</th><th>Segment client</th><th>Risque</th><th>Score</th><th>Dette (TND)</th><th>Remboursement</th><th>Anomalie</th><th>Action recommandée</th><th>Priorité</th><th>Actions</th></tr></thead>
                <tbody>{rows.map((client) => {
                  const actionType = recommendedActionForClient(client);
                  const priority = priorityForClient(client);
                  const isLoading = loadingMsisdn === client.msisdn;
                  return (
                    <tr key={client.msisdn}>
                      <td><ClientCell value={client.msisdn} /></td>
                      <td>{segmentLabel(client.cluster_name)}</td>
                      <td><RiskBadge tier={client.effective_tier || client.risk_tier} /></td>
                      <td><ScoreBar score={client.final_risk_score} tone={client.effective_tier || client.risk_tier} /></td>
                      <td>{formatNumber(client.total_outstanding_amount)}</td>
                      <td>{formatPercent(client.avg_reimburse_ratio)}</td>
                      <td><AnomalyBadge value={client.is_anomaly} /></td>
                      <td>{client.recommended_action_label || actionLabel(actionType)}</td>
                      <td><PriorityBadge priority={priority} label={client.priority_label} /></td>
                      <td><div className="bad-debts-row-actions"><button className="bad-debts-btn primary small" type="button" onClick={() => onRunAgent(client.msisdn)} disabled={isLoading}>{isLoading ? <Loader2 className="spin" size={15} /> : <Bot size={15} />}{isLoading ? "Analyse en cours..." : "Analyser"}</button></div></td>
                    </tr>
                  );
                })}</tbody>
              </table>
            </div>
            <div className="bad-debts-pagination"><button className="bad-debts-btn secondary" type="button" onClick={onPrev} disabled={page <= 1}>Précédent</button><span>Page {formatNumber(page)} / {formatNumber(totalPages)}</span><button className="bad-debts-btn secondary" type="button" onClick={onNext} disabled={page >= totalPages}>Suivant</button></div>
          </>
        ) : <div className="bad-debts-empty-state"><h3>Aucun client ne correspond aux filtres sélectionnés.</h3><button className="bad-debts-btn secondary" type="button" onClick={onReset}>Réinitialiser les filtres</button></div>
      )}
    </section>
  );
}

function BadDebtsAgentDrawer({ feedback, open, onClose }) {
  if (!open || !feedback) return null;
  const contact = feedback.contact || {};
  return (
    <div className="bad-debts-agent-overlay" role="presentation" onMouseDown={onClose}>
      <aside className="bad-debts-agent-drawer" role="dialog" aria-modal="true" aria-label="Analyse métier assistée client" onMouseDown={(event) => event.stopPropagation()}>
        <div className="bad-debts-drawer-head">
          <div>
            <span className={`bad-debts-soft-badge ${feedback.reused ? "reused" : "new"}`}>{feedback.reused ? "Analyse réutilisée" : "Nouvelle analyse"}</span>
            <h3>Analyse métier assistée client</h3>
            <p>{feedback.msisdn}</p>
          </div>
          <button className="bad-debts-icon-btn" type="button" onClick={onClose} aria-label="Fermer">×</button>
        </div>
        <div className="bad-debts-drawer-body">
          {feedback.reused && <div className="bad-debts-drawer-note"><CheckCircle2 size={17} />Analyse récente réutilisée car les données ML n'ont pas changé.</div>}
          <div className="bad-debts-drawer-grid">
            <div><span>Client / MSISDN</span><strong>{feedback.msisdn}</strong></div>
            <div><span>Segment</span><strong>{cleanBusinessText(feedback.segment || "-")}</strong></div>
            <div><span>Niveau de risque</span><strong>{feedback.effectiveTier ? tierLabel(feedback.effectiveTier) : feedback.risk ? tierLabel(feedback.risk) : "Non classé"}</strong></div>
            <div><span>Score ML</span><strong>{formatScore(feedback.score)}</strong></div>
            <div><span>Dette</span><strong>{feedback.debt != null ? `${formatNumber(feedback.debt)} TND` : "-"}</strong></div>
            <div><span>Remboursement</span><strong>{formatRatioPercent(feedback.reimbursement)}</strong></div>
            <div><span>Anomalie</span><strong>{feedback.anomaly ? "Oui" : "Non"}</strong></div>
            <div><span>Priorité</span><strong>{feedback.priority}</strong></div>
          </div>
          {feedback.anomalyEscalated && <div className="bad-debts-drawer-note"><AlertTriangle size={17} />Le niveau de risque a été renforcé car une anomalie ML a été détectée.</div>}
          <section><h4>Recommandation principale</h4><p>{feedback.action}</p></section>
          {!!feedback.factors.length && <section><h4>Facteurs principaux</h4><ul>{feedback.factors.map((item, index) => <li key={`${item}-${index}`}>{cleanBusinessText(item)}</li>)}</ul></section>}
          {contact.type === "call_script" && (
            <section>
              <h4>Décision</h4>
              <p>Contacter le client via le centre de relation client afin de qualifier la situation.</p>
            </section>
          )}
          {(contact.type === "preventive_sms" || contact.type === "preventive_sms_ai") && contact.text && (
            <section>
              <h4>Exemple de message</h4>
              <p>{contact.text}</p>
            </section>
          )}
          {contact.type === "monitoring_note" && (
            <section>
              <h4>Décision</h4>
              <p>Aucune action client immédiate. Suivi automatique recommandé.</p>
            </section>
          )}
        </div>
        <div className="bad-debts-drawer-actions">
          <button className="bad-debts-btn secondary" type="button" onClick={onClose}>Fermer</button>
        </div>
      </aside>
    </div>
  );
}

function formatFiltersDisplay(filters = {}) {
  const TIER = { high: "Élevé", medium: "Moyen", low: "Faible" };
  const SEG = {
    DISCONNECTED: "Déconnecté", SUSPENDED: "Suspendu", "ON-HOLD": "En attente",
    "Bon-payeur": "Bon payeur", Standard: "Standard",
  };
  const ACT = {
    call_center_priority: "Appel prioritaire centre de relation client",
    sms_retention_offer: "SMS personnalisé",
    monitor_only: "Suivi routine",
  };
  const parts = [];
  if (filters.risk_tier) parts.push(`Risque : ${TIER[filters.risk_tier] || filters.risk_tier}`);
  if (filters.cluster_name) parts.push(`Segment : ${SEG[filters.cluster_name] || filters.cluster_name}`);
  if (filters.is_anomaly === true || filters.is_anomaly === "true") parts.push("Anomalie : Oui");
  if (filters.is_anomaly === false || filters.is_anomaly === "false") parts.push("Anomalie : Non");
  if (filters.recommended_action) parts.push(`Action : ${ACT[filters.recommended_action] || filters.recommended_action}`);
  if (filters.search) parts.push("Recherche MSISDN");
  return parts.length ? `Filtres actifs : ${parts.join(", ")}` : "";
}

function GlobalReportPanel({ data, onPrint, onDownloadPdf, onClose }) {
  const report = data.report || {};
  const kpis = data.kpis || {};
  const filters = data.filters || {};
  const scope = data.scope === "filtered" ? "Clients filtrés" : "Tous les clients";
  const filterDisplay = formatFiltersDisplay(filters);
  const reportTitle = report.report_title === "Rapport sur le portefeuille Bad Debts"
    ? "Rapport de pilotage Bad Debts — Portefeuille global"
    : report.report_title || "Rapport global Bad Debts";
  const generatedAt = data.generated_at
    ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeStyle: "short" }).format(new Date(data.generated_at))
    : "-";

  const total = kpis.total_clients ?? 0;
  const high = kpis.clients_high ?? 0;
  const medium = kpis.clients_medium ?? 0;
  const low = kpis.clients_low ?? 0;
  const anomalies = kpis.clients_with_anomaly ?? 0;
  const noAnomalies = total - anomalies;

  const kpiItems = Array.isArray(report.key_kpis) && report.key_kpis.length
    ? report.key_kpis
    : [
      { label: "Clients scorés", value: formatNumber(total), comment: kpis.filter_summary || "" },
      { label: "Anomalies détectées", value: formatNumber(anomalies), comment: "" },
      { label: "Score de risque moyen", value: kpis.average_risk_score != null ? String(Math.round(kpis.average_risk_score * 1000) / 1000) : "-", comment: "Score agrégé" },
      { label: "Dette moyenne", value: kpis.average_debt != null ? `${formatNumber(Math.round(kpis.average_debt))} TND` : "-", comment: "Encours moyen" },
      { label: "Taux de remboursement moyen", value: kpis.average_reimbursement_ratio != null ? `${Math.round(kpis.average_reimbursement_ratio * 100)} %` : "-", comment: "" },
    ];
  const businessRecommendations = Array.isArray(report.business_recommendations)
    ? report.business_recommendations.slice(0, 4).map((item) => {
      if (typeof item === "string") {
        return {
          title: cleanBusinessText(item),
          why: "",
          example: "",
          expected_impact: "",
          legacy: true,
        };
      }
      return {
        title: cleanBusinessText(item.title),
        why: cleanBusinessText(item.why),
        example: cleanBusinessText(item.example),
        expected_impact: cleanBusinessText(item.expected_impact),
        legacy: false,
      };
    }).filter((item) => item.title || item.why || item.example || item.expected_impact)
    : [];

  // Helper arrays for simple graphs
  const riskRows = [
    { label: "Élevé", value: high, tone: "high", percent: total ? (high / total) * 100 : 0 },
    { label: "Moyen", value: medium, tone: "medium", percent: total ? (medium / total) * 100 : 0 },
    { label: "Faible", value: low, tone: "low", percent: total ? (low / total) * 100 : 0 },
  ];

  const anomalyRows = [
    { label: "Avec anomalie", value: anomalies, percent: total ? (anomalies / total) * 100 : 0 },
    { label: "Sans anomalie", value: noAnomalies, percent: total ? (noAnomalies / total) * 100 : 0 },
  ];

  const actionMap = {
    call_center_priority: "Appel prioritaire",
    sms_retention_offer: "SMS personnalisé",
    monitor_only: "Suivi routine"
  };
  const actionDistribution = kpis.distribution_by_action || {};
  const actionRows = Object.entries(actionDistribution)
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => ({
      label: actionMap[key] || key,
      value,
      percent: total ? (value / total) * 100 : 0
    }));

  const segmentDistribution = kpis.distribution_by_segment || {};
  const segmentRows = Object.entries(segmentDistribution)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([key, value]) => ({
      label: segmentLabel(key),
      value,
      percent: total ? (value / total) * 100 : 0
    }));

  return (
    <div className="global-report-panel print-zone">
      <div className="global-report-header no-print">
        <h3>{reportTitle}</h3>
        <div className="global-report-header-actions">
          <button className="bad-debts-btn secondary small" type="button" onClick={onPrint}><Printer size={15} />Imprimer</button>
          <button className="bad-debts-btn secondary small" type="button" onClick={onDownloadPdf}><FileDown size={15} />Télécharger PDF</button>
          <button className="bad-debts-btn secondary small" type="button" onClick={onClose}>Fermer</button>
        </div>
      </div>

      <div className="global-report-print-header print-only">
        <h2>{reportTitle}</h2>
      </div>

      <div className="global-report-meta">
        <span><strong>Date de génération :</strong> {generatedAt}</span>
        <span><strong>Périmètre :</strong> {scope}</span>
        {filterDisplay && <span><strong>Filtre :</strong> {filterDisplay}</span>}
      </div>

      {report.executive_summary && (
        <section className="global-report-section global-report-summary">
          <h4>Résumé décisionnel</h4>
          <p>{cleanBusinessText(report.executive_summary)}</p>
        </section>
      )}

      <section className="global-report-kpis">
        <div className="global-report-kpi-grid">
          {kpiItems.map((item, index) => (
            <div className="global-report-kpi-card" key={`kpi-${index}`}>
              <strong>{item.value}</strong>
              <span>{item.label}</span>
              {item.comment && <small>{item.comment}</small>}
            </div>
          ))}
        </div>
      </section>

      {/* Visual Graphs Section */}
      <section className="global-report-section global-report-graphs">
        <h4>Graphes de pilotage</h4>
        {total <= 0 ? (
          <p className="bdx-empty">Aucune donnée disponible pour les graphiques.</p>
        ) : (
          <div className="bdx-mini-charts-grid">
            <div className="bdx-mini-chart-card">
              <h5>Répartition du risque</h5>
              <div className="bdx-mini-bars">
                {riskRows.map(row => (
                  <div key={row.label} className="bdx-mini-bar-row">
                    <div className="bdx-mini-bar-header">
                      <span>{row.label}</span>
                      <strong>{formatNumber(row.value)} ({Math.round(row.percent)}%)</strong>
                    </div>
                    <div className="bdx-mini-bar-track">
                      <div className={`bdx-mini-bar-fill ${row.tone}`} style={{ width: `${row.percent}%` }}></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="bdx-mini-chart-card">
              <h5>Anomalies détectées</h5>
              <div className="bdx-mini-bars">
                {anomalyRows.map(row => (
                  <div key={row.label} className="bdx-mini-bar-row">
                    <div className="bdx-mini-bar-header">
                      <span>{row.label}</span>
                      <strong>{formatNumber(row.value)} ({Math.round(row.percent)}%)</strong>
                    </div>
                    <div className="bdx-mini-bar-track">
                      <div className="bdx-mini-bar-fill neutral" style={{ width: `${row.percent}%` }}></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {actionRows.length > 0 && (
              <div className="bdx-mini-chart-card">
                <h5>Actions recommandées</h5>
                <div className="bdx-mini-bars">
                  {actionRows.map(row => (
                    <div key={row.label} className="bdx-mini-bar-row">
                      <div className="bdx-mini-bar-header">
                        <span>{row.label}</span>
                        <strong>{formatNumber(row.value)} ({Math.round(row.percent)}%)</strong>
                      </div>
                      <div className="bdx-mini-bar-track">
                        <div className="bdx-mini-bar-fill blue" style={{ width: `${row.percent}%` }}></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {segmentRows.length > 0 && (
              <div className="bdx-mini-chart-card">
                <h5>Top Segments</h5>
                <div className="bdx-mini-bars">
                  {segmentRows.map(row => (
                    <div key={row.label} className="bdx-mini-bar-row">
                      <div className="bdx-mini-bar-header">
                        <span>{row.label}</span>
                        <strong>{formatNumber(row.value)} ({Math.round(row.percent)}%)</strong>
                      </div>
                      <div className="bdx-mini-bar-track">
                        <div className="bdx-mini-bar-fill cyan" style={{ width: `${row.percent}%` }}></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {Array.isArray(report.decision_support) && report.decision_support.length > 0 && (
        <section className="global-report-section">
          <h4>Aide à la décision</h4>
          <div className="global-report-decision-grid new-layout">
            {report.decision_support.map((item, index) => (
              <div className="global-report-decision-card" key={`ds-${index}`}>
                <div className="global-report-decision-priority">{item.priority}</div>
                <div className="global-report-decision-body">
                  <h5>{cleanBusinessText(item.target)}</h5>
                  <p className="global-report-decision-goal">
                    <strong>Objectif métier :</strong> {cleanBusinessText(item.business_goal)}
                  </p>
                  <p className="global-report-decision-focus">
                    <strong>Orientation métier :</strong> {cleanBusinessText(item.recommended_focus)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {Array.isArray(report.profile_recommendations) && report.profile_recommendations.length > 0 && (
        <section className="global-report-section">
          <h4>Recommandations par profil</h4>
          <ul>{report.profile_recommendations.map((item, index) => {
            const parts = cleanBusinessText(item).split(" : ");
            if (parts.length > 1) {
              return <li key={`profile-${index}`}><strong>{parts[0]} : </strong>{parts.slice(1).join(" : ")}</li>;
            }
            return <li key={`profile-${index}`}>{cleanBusinessText(item)}</li>;
          })}</ul>
        </section>
      )}

      {businessRecommendations.length > 0 && (
        <section className="global-report-section">
          <h4>Recommandations opérationnelles</h4>
          <div className="global-report-recommendation-grid">
            {businessRecommendations.map((item, index) => (
              <div className={`global-report-rec-card${item.legacy ? " legacy" : ""}`} key={`rec-card-${index}`}>
                <div className="global-report-rec-header">
                  <span className="global-report-rec-number">{index + 1}</span>
                  <h5>{item.title || "Recommandation"}</h5>
                </div>
                <div className="global-report-rec-body">
                  {item.why && (
                    <p className="global-report-rec-why">
                      <strong>Pourquoi :</strong> {item.why}
                    </p>
                  )}
                  {item.example && (
                    <p className="global-report-rec-example">
                      <strong>Exemple métier :</strong> {item.example}
                    </p>
                  )}
                  {item.expected_impact && (
                    <p className="global-report-rec-impact">
                      <strong>Impact attendu :</strong> {item.expected_impact}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="global-report-footer no-print">
        <button className="bad-debts-btn secondary" type="button" onClick={onPrint}><Printer size={15} />Imprimer</button>
        <button className="bad-debts-btn secondary" type="button" onClick={onDownloadPdf}><FileDown size={15} />Télécharger PDF</button>
        <button className="bad-debts-btn secondary" type="button" onClick={onClose}>Fermer le rapport</button>
      </div>
    </div>
  );
}

function RiskBadge({ tier }) {
  const normalized = normalizeTier(tier);
  return <span className={`bad-debts-badge risk-${normalized || "unknown"}`}>{tierLabel(tier)}</span>;
}

function PriorityBadge({ priority, label }) {
  const numeric = Number(priority);
  const tone = numeric === 1 ? "critical" : numeric === 2 ? "warning" : "normal";
  return <span className={`bad-debts-badge priority-${tone}`}>{label || priorityLabel(priority)}</span>;
}

function AnomalyBadge({ value }) {
  return <span className={`bad-debts-badge anomaly-${value ? "yes" : "no"}`}>{value ? "Oui" : "Non"}</span>;
}

function ImportHistoryPage({ imports, refreshDashboard }) {
  const rows = imports || [];
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");
  const latest = rows[0] || null;

  async function submitImport(event) {
    event.preventDefault();
    if (!selectedFile || uploading) return;
    setUploading(true);
    setUploadMessage("");
    setUploadError("");
    try {
      const response = await uploadBadDebtsRawImport(selectedFile);
      if (response.data?.status === "SUCCES") {
        const pipelineType = response.data?.pipeline_type;
        if (pipelineType === "raw_sos") {
          setUploadMessage("Fichier brut détecté : fusion, segmentation ML et import PostgreSQL exécutés.");
        } else if (pipelineType === "segmented") {
          setUploadMessage("Fichier segmenté détecté : contrôle qualité et import PostgreSQL exécutés.");
        } else {
          setUploadMessage("Import terminé avec succès. Les données Bad Debts ont été mises à jour.");
        }
        setSelectedFile(null);
        event.target.reset();
        await refreshDashboard?.();
      } else {
        setUploadError("Import échoué. Les données précédentes ont été conservées.");
        await refreshDashboard?.();
      }
    } catch (err) {
      setUploadError(getApiError(err, "Import échoué. Les données précédentes ont été conservées."));
      await refreshDashboard?.();
    } finally {
      setUploading(false);
    }
  }

  function statusTone(status) {
    const normalized = String(status || "");
    if (normalized === "SUCCES" || normalized === "success") return "low";
    if (normalized === "EN_COURS") return "medium";
    return "high";
  }

  return (
    <div className="bdx-view">
      <Panel title="Importer un fichier brut" meta="Nouveau cycle ML Bad Debts">
        <form className="bdx-import-form" onSubmit={submitImport}>
          <label className="bdx-file-picker">
            <CloudUpload size={20} />
            <span>{selectedFile ? selectedFile.name : "Choisir un fichier CSV ou XLSX"}</span>
            <input type="file" accept=".csv,.xlsx,.xls" onChange={(event) => setSelectedFile(event.target.files?.[0] || null)} />
          </label>
          <button className="bdx-button primary" type="submit" disabled={!selectedFile || uploading}>
            {uploading ? <Loader2 className="spin" size={18} /> : <CloudUpload size={18} />}
            Importer un fichier brut
          </button>
        </form>
        {uploadMessage && <div className="bdx-alert success"><CheckCircle2 size={18} />{uploadMessage}</div>}
        {uploadError && <div className="bdx-alert"><AlertTriangle size={18} />{uploadError}</div>}
        {latest && (
          <div className="bdx-import-latest">
            <strong>Dernier import</strong>
            <span>{displayValue(latest.file_name)}</span>
            <Badge tone={statusTone(latest.status)}>{importStatusLabel(latest.status)}</Badge>
          </div>
        )}
      </Panel>
      <Panel title="Historique des imports" meta={`${rows.length} derniers imports`}>
        <div className="bdx-table-wrap"><table className="bdx-table"><thead><tr><th>Date d'import</th><th>Date fin</th><th>Fichier source</th><th>Clients importés</th><th>Statut</th><th>Erreur</th></tr></thead><tbody>{rows.length ? rows.map((item) => <tr key={item.id}><td>{formatDate(item.imported_at)}</td><td>{formatDate(item.finished_at)}</td><td>{displayValue(item.file_name)}</td><td>{formatNumber(item.rows_imported)}</td><td><Badge tone={statusTone(item.status)}>{importStatusLabel(item.status)}</Badge></td><td>{item.error_message || "-"}</td></tr>) : <tr><td colSpan={6}><p className="bdx-empty">Aucun import disponible pour le moment.</p></td></tr>}</tbody></table></div>
      </Panel>
    </div>
  );
}

function SettingsPage() {
  return (
    <div className="bdx-view"><Panel title="Paramètres Bad Debts" meta="Préférences locales"><p className="bdx-empty">Module en cours de préparation.</p></Panel></div>
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

function ClientCell({ value }) {
  return <div className="bdx-client-cell"><strong>{value}</strong><small>MSISDN</small></div>;
}

function Badge({ tone = "neutral", children }) {
  return <span className={`bdx-badge ${tone}`}>{children}</span>;
}

function ScoreBar({ score, tone = "" }) {
  const normalizedTone = normalizeTier(tone) || "low";
  return <div className={`bdx-score score-${normalizedTone}`}><strong>{formatScore(score)}</strong><i><b style={{ width: `${toPercent(score)}%` }} /></i></div>;
}

function InlineLoading() {
  return <div className="bdx-loading"><Loader2 className="spin" size={22} />Chargement...</div>;
}

function buildTierRows(summary) {
  const byTier = summary.by_tier || {};
  const fallback = { low: 0, medium: 0, high: 0 };
  const total = Math.max(summary.total_clients || 0, 1);
  return ["low", "medium", "high"].map((tier) => {
    const value = byTier[tier] ?? fallback[tier];
    return { tier, label: TIER_LABELS[tier], value, percent: (Number(value) / total) * 100 };
  });
}

function buildSegmentRows(summary) {
  const source = Object.keys(summary.by_cluster_name || {}).length
    ? summary.by_cluster_name
    : {};
  const entries = Object.entries(source).slice(0, 5);
  const max = Math.max(...entries.map(([, value]) => Number(value)), 1);
  return entries.map(([label, value]) => ({ label: segmentLabel(label), value, percent: (Number(value) / max) * 100 }));
}

function buildScoreRows() {
  const rows = [
    ["Déconnecté", 0.812],
    ["Suspendu", 0.674],
    ["En attente", 0.523],
    ["Standard", 0.312],
    ["Bon payeur", 0.156],
  ];
  return rows.map(([label, value]) => ({ label, value, percent: value * 100 }));
}
