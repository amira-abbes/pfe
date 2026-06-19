import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock3,
  CloudUpload,
  Database,
  Download,
  Eye,
  FileText,
  Info as InfoIcon,
  Loader2,
  PlayCircle,
  Power,
  RefreshCw,
  Search,
  ShieldAlert,
  Square,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, getApiError } from "../api/api";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import "../styles/admin-elt.css";

const BI_REFRESH_SLOTS = ["08:00", "09:00", "10:00", "11:00", "14:00", "15:00", "16:00", "17:00"];
const REPORT_DISPLAY_NAME = "Service SOS Solde & Data";

const FINAL_STATUSES = new Set(["COMPLETED", "NO_DATA", "FAILED", "PARTIAL_FAILURE", "STOPPED"]);
const ACTIVE_RUN_STATUSES = new Set(["RUNNING", "INITIALIZING", "PROCESSING"]);

const FINAL_TOASTS = {
  COMPLETED: ["success", "Traitement ELT terminé avec succès."],
  NO_DATA: ["info", "Aucune donnée à traiter."],
  FAILED: ["error", "Traitement ELT échoué."],
  PARTIAL_FAILURE: ["warning", "Traitement partiellement réussi."],
  STOPPED: ["warning", "Traitement ELT arrêté."],
};

const SCENARIO_LABELS = {
  FTP_DIRECT: "Traitement direct depuis FTP",
  FTP_TO_LOCAL: "Récupération FTP puis traitement local",
  LOCAL_ONLY: "Traitement local manuel",
  LOCAL_FALLBACK: "Traitement local",
  STOP: "Traitement arrêté",
};

const STATUS_LABELS = {
  COMPLETED: "Traitement terminé avec succès",
  NO_DATA: "Aucune donnée à traiter",
  FAILED: "Traitement échoué",
  PARTIAL_FAILURE: "Traitement partiellement réussi",
  STOPPED: "Traitement arrêté",
  RUNNING: "Traitement en cours",
  INITIALIZING: "Initialisation",
  SUCCESS: "Succès",
  PENDING: "En attente",
  READY: "Prêt",
};

const TECHNICAL_COLUMNS = [
  "task_name",
  "task_label",
  "table_label",
  "branch",
  "status",
  "start_time",
  "end_time",
  "duration_sec",
  "retry_count",
  "fallback_used",
  "fallback_script",
  "error_message",
];

const ADV_FILE_COLUMNS = [
  ["fichier", "Fichier"],
  ["date_fichier", "Date fichier"],
  ["date_traitement", "Date traitement"],
  ["lignes_fichier", "Lignes fichier"],
  ["lignes_inserees", "Lignes insérées"],
  ["lignes_rejetees", "Lignes rejetées"],
  ["chargement", "Chargement"],
  ["detail", "Détail"],
  ["aggregation", "Agrégation"],
  ["service", "Service"],
  ["parc", "Parc"],
  ["archivage", "Archivage"],
];

const REV_FILE_COLUMNS = [
  ["fichier", "Fichier"],
  ["date_fichier", "Date fichier"],
  ["date_traitement", "Date traitement"],
  ["lignes_fichier", "Lignes fichier"],
  ["lignes_inserees", "Lignes insérées"],
  ["lignes_rejetees", "Lignes rejetées"],
  ["chargement", "Chargement"],
  ["detail", "Détail"],
  ["aggregation", "Agrégation"],
  ["service", "Service"],
  ["archivage", "Archivage"],
];

function scenarioLabel(value) {
  const key = String(value || "").toUpperCase();
  return SCENARIO_LABELS[key] || value || "-";
}

function statusLabel(value) {
  const key = String(value || "").toUpperCase();
  return STATUS_LABELS[key] || value || "Non renseigné";
}

function eltSyncLabel(value) {
  const key = String(value || "").toUpperCase();
  if (key === "COMPLETED") return "Terminé avec succès";
  if (key === "NO_DATA") return "Aucune donnée à traiter";
  if (key === "FAILED") return "Échec";
  if (key === "PARTIAL_FAILURE") return "Partiellement réussi";
  if (key === "STOPPED") return "Traitement arrêté";
  return "Aucun traitement récent";
}

function oracleSyncState(value) {
  const key = String(value || "").toUpperCase();
  if (key === "COMPLETED") return { label: "Données Oracle mises à jour", className: "elt-badge success" };
  if (key === "NO_DATA") return { label: "Aucune nouvelle donnée", className: "elt-badge neutral" };
  if (["FAILED", "PARTIAL_FAILURE", "STOPPED"].includes(key)) {
    return {
      label: "Oracle non validé pour Power BI",
      className: key === "PARTIAL_FAILURE" ? "elt-badge warning" : "elt-badge danger",
    };
  }
  return { label: "Oracle en attente de validation", className: "elt-badge neutral" };
}

function getNextPowerBiRefresh(now = new Date()) {
  const currentMinutes = now.getHours() * 60 + now.getMinutes();
  const slotDetails = BI_REFRESH_SLOTS.map((slot) => {
    const [hours, minutes] = slot.split(":").map(Number);
    return { slot, minutesOfDay: hours * 60 + minutes };
  });
  const next = slotDetails.find((item) => item.minutesOfDay > currentMinutes);
  const target = next || slotDetails[0];
  const isTomorrow = !next;
  const minutesRemaining = isTomorrow
    ? 24 * 60 - currentMinutes + target.minutesOfDay
    : target.minutesOfDay - currentMinutes;

  let countdownLabel = `dans ${minutesRemaining} min`;
  if (isTomorrow) {
    countdownLabel = `demain à ${target.slot}`;
  } else if (minutesRemaining >= 60) {
    const hours = Math.floor(minutesRemaining / 60);
    const minutes = minutesRemaining % 60;
    countdownLabel = `dans ${hours}h${minutes ? ` ${minutes}min` : ""}`;
  }

  return {
    label: target.slot,
    isTomorrow,
    minutesRemaining,
    countdownLabel,
  };
}

function badgeClass(value) {
  const key = String(value || "").toUpperCase();
  if (["COMPLETED", "SUCCESS", "SUCCÈS", "OK"].includes(key)) return "elt-badge success";
  if (["FAILED", "FAILED_INSERT", "FAILED_CONTROL", "ÉCHEC", "ECHEC"].includes(key)) return "elt-badge danger";
  if (["PARTIAL_FAILURE", "WATCHER_ACTIVE", "EN ATTENTE", "FICHIER RÉCENT - CONSERVATION 7 JOURS"].includes(key)) return "elt-badge warning";
  if (["RUNNING", "INITIALIZING", "READY"].includes(key)) return "elt-badge info";
  if (["STOPPED", "NON CONCERNÉ", "NON CONCERNE"].includes(key)) return "elt-badge dark";
  return "elt-badge neutral";
}

function formatArchiveDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).split(/[T\s]/)[0] || "-";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  }).format(date);
}

function isWatcherActive(watchStatus) {
  const raw = watchStatus || {};
  const state = String(raw.state || raw.status || raw.etat || "").toUpperCase();
  if (["STOPPED", "ARRÊTÉE", "ARRETEE"].includes(state)) return false;
  return (
    raw.watching === true ||
    raw.active === true ||
    ["WAITING_FOR_FILE", "FILE_STABLE", "PROCESSING", "ORACLE_KO"].includes(state)
  );
}

function technicalCsvPath(report) {
  return report?.technical_tasks_csv_path || report?.csv_path || report?.csv_report_path || "";
}

function txtPath(report) {
  return report?.txt_report_path || report?.txt_path || "";
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function AdminEltPage() {
  const { hasRight } = useAuth();
  const navigate = useNavigate();
  const canRunElt = hasRight("lancer_elt");

  const [loading, setLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isStartingRun, setIsStartingRun] = useState(false);
  const [isStartingWatcher, setIsStartingWatcher] = useState(false);
  const [isStoppingWatcher, setIsStoppingWatcher] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [toast, setToast] = useState(null);
  const [connections, setConnections] = useState(null);
  const [connectionChecking, setConnectionChecking] = useState(false);
  const [runStatus, setRunStatus] = useState(null);
  const [watchStatus, setWatchStatus] = useState(null);
  const [report, setReport] = useState(null);
  const [txtReport, setTxtReport] = useState("");
  const [archiveFilesAdv, setArchiveFilesAdv] = useState([]);
  const [archiveFilesRev, setArchiveFilesRev] = useState([]);
  const [archiveSearch, setArchiveSearch] = useState("");
  const [showModeChoice, setShowModeChoice] = useState(false);
  const [hasStartedEltFlow, setHasStartedEltFlow] = useState(false);
  const [hasRunStartedFromPage, setHasRunStartedFromPage] = useState(false);
  const [hasRunReachedFinalStatus, setHasRunReachedFinalStatus] = useState(false);
  const [technicalData, setTechnicalData] = useState({ columns: [], rows: [] });
  const [showTechnical, setShowTechnical] = useState(false);

  const runPollRef = useRef(null);
  const watchPollRef = useRef(null);
  const toastTimerRef = useRef(null);
  const lastToastRef = useRef({ key: "", at: 0 });
  const lastFinalToastRef = useRef("");
  const manualRunStartedRef = useRef(false);
  const runPollStartedAtRef = useRef(0);
  const hasSeenActiveRunRef = useRef(false);
  const runStartLockRef = useRef(false);

  const activeRun = isRunning || ACTIVE_RUN_STATUSES.has(String(runStatus?.status || "").toUpperCase()) || runStatus?.active === true;
  const watcherActive = isWatcherActive(watchStatus);
  const runButtonDisabled = !canRunElt || isStartingRun || activeRun || watcherActive || isStartingWatcher || connectionChecking;
  const startWatcherDisabled = isStartingWatcher || activeRun || isStartingRun || watcherActive || connectionChecking;
  const stopWatcherDisabled = isStoppingWatcher;
  const refreshDisabled = isRefreshing;
  const shouldShowReport = hasRunStartedFromPage && hasRunReachedFinalStatus && !activeRun && Boolean(report);
  const shouldShowFreshnessPanel = hasRunStartedFromPage && hasRunReachedFinalStatus && !activeRun && Boolean(report);

  function showToast(typeOrConfig, text) {
    const nextToast =
      typeof typeOrConfig === "object"
        ? typeOrConfig
        : { type: typeOrConfig, text, message: text };
    const toastKey = nextToast.key || `${nextToast.type || ""}:${nextToast.title || ""}:${nextToast.message || nextToast.text || ""}`;
    const now = Date.now();
    if (lastToastRef.current.key === toastKey && now - lastToastRef.current.at < 5000) {
      return;
    }
    lastToastRef.current = { key: toastKey, at: now };
    window.clearTimeout(toastTimerRef.current);
    setToast(nextToast);
    toastTimerRef.current = window.setTimeout(() => setToast(null), nextToast.actionLabel ? 7200 : 4200);
  }

  function releaseRunStartLock() {
    runStartLockRef.current = false;
    setIsStartingRun(false);
  }

  useEffect(() => {
    initialLoad();
    return () => {
      window.clearInterval(runPollRef.current);
      window.clearInterval(watchPollRef.current);
      window.clearTimeout(toastTimerRef.current);
    };
  }, []);

  useEffect(() => {
    window.clearInterval(watchPollRef.current);
    if (watcherActive) {
      console.log("[ELT UI] watcher polling started");
      watchPollRef.current = window.setInterval(async () => {
        const nextWatchStatus = await loadWatchStatus({ silent: true });
        const state = String(nextWatchStatus?.state || nextWatchStatus?.status || "").toUpperCase();
        if (state === "PROCESSING") {
          await loadRunStatus({ suppressErrors: true });
        }
      }, 2000);
    }
    return () => {
      if (watchPollRef.current) console.log("[ELT UI] watcher polling stopped cleanup");
      window.clearInterval(watchPollRef.current);
    };
  }, [watcherActive]);

  const filteredAdvFiles = useMemo(() => {
    const term = archiveSearch.trim().toLowerCase();
    if (!term) return archiveFilesAdv;
    return archiveFilesAdv.filter((item) =>
      [item.flux, item.fichier].some((value) => String(value || "").toLowerCase().includes(term)),
    );
  }, [archiveFilesAdv, archiveSearch]);

  const filteredRevFiles = useMemo(() => {
    const term = archiveSearch.trim().toLowerCase();
    if (!term) return archiveFilesRev;
    return archiveFilesRev.filter((item) =>
      [item.flux, item.fichier].some((value) => String(value || "").toLowerCase().includes(term)),
    );
  }, [archiveFilesRev, archiveSearch]);

  async function initialLoad() {
    console.log("[ELT UI] initial load");
    setLoading(true);
    try {
      await Promise.all([loadArchiveFiles(), loadWatchStatus({ silent: true }), loadRunStatus({ silent: true })]);
    } finally {
      setLoading(false);
    }
  }

  async function refreshPage() {
    console.log("[ELT UI] refresh visible data");
    setIsRefreshing(true);
    setShowModeChoice(false);
    try {
      const [, status] = await Promise.all([
        loadWatchStatus({ silent: true }),
        loadRunStatus({ silent: true }),
        loadArchiveFiles(),
      ]);
      if (ACTIVE_RUN_STATUSES.has(String(status?.status || "").toUpperCase()) || status?.active) {
        setIsRunning(true);
        setHasRunReachedFinalStatus(false);
        startRunPolling();
        return;
      }
      setIsRunning(false);
      if (hasRunStartedFromPage && hasRunReachedFinalStatus) {
        await loadLatestReportWithRetry(3, { preserveExisting: true });
      }
    } catch {
      showToast({ type: "error", key: "refresh-error", message: "Erreur backend lors de l’action demandée." });
    } finally {
      setIsRefreshing(false);
    }
  }

  async function loadLatestReportWithRetry(maxAttempts = 6, options = {}) {
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const latest = await loadLatestReport(options);
      if (latest?.run_id || latest?.status) return latest;
      await new Promise((resolve) => window.setTimeout(resolve, 800));
    }
    return null;
  }

  async function handleFinalRunStatus(data, { silent = false } = {}) {
    const status = String(data?.status || "").toUpperCase();
    window.clearInterval(runPollRef.current);
    console.log("[ELT UI] polling stopped final status=", status);
    setIsRunning(false);
    releaseRunStartLock();

    if (manualRunStartedRef.current) {
      setHasRunReachedFinalStatus(true);
      const latest = await loadLatestReportWithRetry();
      await Promise.all([loadArchiveFiles(), loadWatchStatus({ silent: true })]);
      const finalToastKey = `${data?.run_id || latest?.run_id || ""}-${status}`;
      if (!silent && lastFinalToastRef.current !== finalToastKey) {
        const [type, text] = FINAL_TOASTS[status] || ["info", "Traitement ELT terminé."];
        showToast({
          type,
          title: text,
          message: latest?.run_id || latest?.status ? "Le rapport métier est disponible." : "Le traitement est terminé.",
          actionLabel: technicalCsvPath(latest) ? "Voir tableau technique" : "",
          onAction: technicalCsvPath(latest) ? () => openTechnicalTasks(latest) : null,
          secondaryActionLabel: technicalCsvPath(latest) ? "Télécharger CSV" : "",
          onSecondaryAction: technicalCsvPath(latest)
            ? () => download(technicalCsvPath(latest), "/elt/download/csv", "suivi-technique.csv")
            : null,
        });
        lastFinalToastRef.current = finalToastKey;
      }
      manualRunStartedRef.current = false;
    } else {
      await Promise.all([loadArchiveFiles(), loadWatchStatus({ silent: true })]);
    }
  }

  function startRunPolling() {
    window.clearInterval(runPollRef.current);
    runPollStartedAtRef.current = Date.now();
    hasSeenActiveRunRef.current = false;
    console.log("[ELT UI] polling started");
    runPollRef.current = window.setInterval(() => {
      loadRunStatus({ suppressErrors: true }).catch(() => {});
    }, 2000);
    window.setTimeout(() => loadRunStatus({ suppressErrors: true }).catch(() => {}), 900);
  }

  async function loadConnections({ silent = false } = {}) {
    try {
      const response = await api.get("/elt/check-connections");
      console.log("[ELT UI] check connections", response.data);
      setConnections(response.data);
      return response.data;
    } catch (err) {
      if (!silent) showToast("error", getApiError(err, "Impossible de vérifier Oracle et FTP."));
      return null;
    }
  }

  async function loadWatchStatus({ silent = false } = {}) {
    try {
      const response = await api.get("/elt/watch/status");
      console.log("[ELT UI] watch status", response.data);
      console.log("[ELT UI] isWatcherActive", isWatcherActive(response.data));
      setWatchStatus(response.data);
      return response.data;
    } catch (err) {
      if (!silent) showToast("error", getApiError(err, "Impossible de charger la surveillance locale."));
      return null;
    }
  }

  async function loadRunStatus({ silent = false, suppressErrors = false } = {}) {
    try {
      const response = await api.get("/elt/run/status");
      const data = response.data;
      console.log("[ELT UI] run status", data);
      setRunStatus(data);
      const status = String(data?.status || "").toUpperCase();
      if (ACTIVE_RUN_STATUSES.has(status) || data?.active) {
        hasSeenActiveRunRef.current = true;
        setIsRunning(true);
        setHasRunReachedFinalStatus(false);
      }
      if (FINAL_STATUSES.has(status)) {
        const elapsedSinceStart = Date.now() - runPollStartedAtRef.current;
        if (manualRunStartedRef.current && !hasSeenActiveRunRef.current && elapsedSinceStart < 5000) {
          return data;
        }
        await handleFinalRunStatus(data, { silent });
      }
      return data;
    } catch (err) {
      if (!silent && !suppressErrors) {
        showToast({ type: "error", key: "run-status-error", message: getApiError(err, "Erreur backend lors de l’action demandée.") });
      }
      return null;
    }
  }

  async function loadLatestReport({ preserveExisting = false } = {}) {
    try {
      const response = await api.get("/elt/latest-report");
      if (response.data?.success === false && !response.data?.run_id) return;
      setReport(response.data);
      await loadTxtReport(response.data);
      return response.data;
    } catch {
      if (!preserveExisting) {
        setReport(null);
        setTxtReport("");
      }
      return null;
    }
  }

  async function loadTxtReport(nextReport) {
    const path = txtPath(nextReport);
    if (!path) {
      setTxtReport("");
      return;
    }
    try {
      const response = await api.get("/elt/txt-report", { params: { path } });
      setTxtReport(response.data?.content || "");
    } catch {
      setTxtReport("");
    }
  }

  async function loadArchiveFiles() {
    try {
      const response = await api.get("/elt/archive-files", { params: { limit: 50 } });
      const files = response.data?.files || [];
      const filesAdv = response.data?.files_adv || files.filter((item) => String(item.flux || "").toLowerCase().includes("avance"));
      const filesRev = response.data?.files_rev || files.filter((item) => String(item.flux || "").toLowerCase().includes("remboursement"));
      setArchiveFilesAdv(filesAdv);
      setArchiveFilesRev(filesRev);
    } catch (err) {
      setArchiveFilesAdv([]);
      setArchiveFilesRev([]);
      showToast({ type: "error", key: "archive-load-error", message: getApiError(err, "Erreur backend lors de l’action demandée.") });
    }
  }

  async function handleLaunchClick() {
    console.log("[ELT UI] lancer clicked");
    if (watcherActive) {
      showToast({ type: "warning", key: "launch-blocked-watcher", message: "Action impossible : surveillance locale active." });
      return;
    }
    if (runStartLockRef.current || isStartingRun || activeRun) {
      showToast({ type: "warning", key: "launch-blocked-run", message: "Action impossible : traitement ELT en cours." });
      return;
    }
    runStartLockRef.current = true;
    setIsStartingRun(true);
    setHasStartedEltFlow(true);
    setShowModeChoice(false);
    setHasRunReachedFinalStatus(false);
    setReport(null);
    setTxtReport("");

    const connectionState = await loadConnections();
    if (!connectionState) {
      releaseRunStartLock();
      return;
    }
    if (!connectionState.oracle_ok) {
      showToast({
        type: "error",
        title: "Oracle indisponible",
        message: "Oracle indisponible. Vous ne pouvez pas lancer le traitement.",
      });
      releaseRunStartLock();
      return;
    }

    const status = await loadRunStatus();
    if (ACTIVE_RUN_STATUSES.has(String(status?.status || "").toUpperCase()) || status?.active) {
      setIsRunning(true);
      showToast({ type: "warning", key: "launch-blocked-run", message: "Action impossible : traitement ELT en cours." });
      releaseRunStartLock();
      return;
    }

    const watcher = await loadWatchStatus();
    console.log("[ELT UI] watch status before launch", watcher);
    const watcherIsActive = isWatcherActive(watcher);
    console.log("[ELT UI] computed watcher active", watcherIsActive);
    if (watcherIsActive) {
      setWatchStatus(watcher);
      showToast({ type: "warning", key: "launch-blocked-watcher", message: "Action impossible : surveillance locale active." });
      releaseRunStartLock();
      return;
    }

    await checkConnectionsAndLaunch(connectionState, { keepStartingLock: true });
  }

  async function checkConnectionsAndLaunch(precheckedConnections = null, { keepStartingLock = false } = {}) {
    setLoading(true);
    setConnectionChecking(true);
    try {
      const data = precheckedConnections || await loadConnections();
      if (!data) {
        releaseRunStartLock();
        return;
      }

      if (!data.oracle_ok) {
        showToast({
          type: "error",
          title: "Oracle indisponible",
          message: "Oracle indisponible. Vous ne pouvez pas lancer le traitement.",
        });
        releaseRunStartLock();
        return;
      }

      if (data.ftp_ok) {
        setShowModeChoice(true);
        releaseRunStartLock();
        return;
      }

      console.log("[ELT UI] chosen mode", "LOCAL_ONLY");
      await startRun("LOCAL_ONLY", { allowLockedStart: keepStartingLock });
    } catch (err) {
      showToast("error", getApiError(err, "Impossible de vérifier Oracle et FTP."));
      releaseRunStartLock();
    } finally {
      setConnectionChecking(false);
      setLoading(false);
    }
  }

  async function startRun(userMode, { allowLockedStart = false } = {}) {
    console.log("[ELT START] userMode=", userMode);
    console.log("[ELT UI] chosen mode", userMode);
    if (watcherActive) {
      showToast({ type: "warning", key: "launch-blocked-watcher", message: "Action impossible : surveillance locale active." });
      return;
    }
    if ((runStartLockRef.current && !allowLockedStart) || isStartingRun || activeRun) {
      showToast({ type: "warning", key: "launch-blocked-run", message: "Action impossible : traitement ELT en cours." });
      return;
    }
    runStartLockRef.current = true;
    setIsStartingRun(true);
    setLoading(true);
    setShowModeChoice(false);
    setHasRunReachedFinalStatus(false);
    setReport(null);
    setTxtReport("");
    try {
      const response = await api.post("/elt/run/start", null, { params: { user_mode: userMode } });
      const data = response.data;
      console.log("[ELT START RESPONSE]", data);
      console.log("[ELT UI] start run response", data);
      if (data.watch_active) {
        setWatchStatus({ success: true, active: true, watching: true, state: "WAITING_FOR_FILE" });
        showToast({ type: "warning", key: "launch-blocked-watcher", message: "Action impossible : surveillance locale active." });
        releaseRunStartLock();
        return;
      }
      if (!data.success) {
        showToast("error", data.message || data.error || "Lancement ELT impossible.");
        releaseRunStartLock();
        return;
      }
      showToast({ type: "success", key: "run-started", message: "Traitement ELT lancé." });
      manualRunStartedRef.current = true;
      setHasRunStartedFromPage(true);
      setHasRunReachedFinalStatus(false);
      setIsRunning(true);
      setReport(null);
      setTxtReport("");
      setRunStatus({ status: "RUNNING", active: true, user_mode: userMode, scenario_label: data.scenario_label });
      setIsStartingRun(false);
      startRunPolling();
    } catch (err) {
      showToast("error", getApiError(err, "Erreur lors du lancement ELT."));
      releaseRunStartLock();
    } finally {
      setLoading(false);
    }
  }

  async function startWatch() {
    if (activeRun) {
      showToast({ type: "warning", key: "watch-blocked-run", message: "Action impossible : traitement ELT en cours." });
      return;
    }
    if (isStartingRun || isStartingWatcher || connectionChecking) {
      showToast({ type: "warning", key: "watch-blocked-action", message: "Action impossible pour le moment." });
      return;
    }
    if (watcherActive) {
      showToast({ type: "warning", key: "watch-already-active", message: "Surveillance locale déjà active." });
      return;
    }
    setHasStartedEltFlow(true);
    setIsStartingWatcher(true);
    setLoading(true);
    try {
      const connectionState = await loadConnections();
      if (!connectionState) return;
      if (!connectionState.oracle_ok) {
        showToast({
          type: "error",
          title: "Oracle indisponible",
          message: "Oracle indisponible. Vous ne pouvez pas activer la surveillance locale.",
        });
        return;
      }
      const response = await api.post("/elt/watch/start");
      if (response.data?.success) {
        showToast({ type: "success", key: "watch-started", message: "Surveillance locale activée." });
        setWatchStatus({
          success: true,
          active: true,
          watching: true,
          state: "WAITING_FOR_FILE",
          label: "Surveillance active",
          state_label: "Surveillance active",
          message: response.data?.message || "En attente de fichier.",
          pid: response.data?.pid,
        });
      } else {
        showToast("warning", response.data?.message || "Surveillance locale non activée.");
      }
      await loadWatchStatus();
    } catch (err) {
      showToast("error", getApiError(err, "Impossible d'activer la surveillance locale."));
    } finally {
      setIsStartingWatcher(false);
      setLoading(false);
    }
  }

  async function stopWatch() {
    if (isStoppingWatcher) return;
    setIsStoppingWatcher(true);
    setLoading(true);
    try {
      await api.post("/elt/watch/stop");
      showToast({ type: "success", key: "watch-stopped", message: "Surveillance locale désactivée." });
      const nextStatus = await loadWatchStatus();
      if (!nextStatus) {
        setWatchStatus({ success: true, active: false, watching: false, state: "STOPPED" });
      }
    } catch (err) {
      showToast("error", getApiError(err, "Impossible de désactiver la surveillance locale."));
    } finally {
      setIsStoppingWatcher(false);
      setLoading(false);
    }
  }

  async function openTechnicalTasks(sourceReport = report) {
    const path = technicalCsvPath(sourceReport);
    if (!path) {
      showToast("info", "Aucun suivi technique des tâches n'est disponible.");
      return;
    }
    try {
      const response = await api.get("/elt/csv-data", { params: { path } });
      setTechnicalData(response.data || { columns: [], rows: [] });
      setShowTechnical(true);
    } catch (err) {
      showToast("error", getApiError(err, "Impossible de charger le suivi technique des tâches."));
    }
  }

  async function download(path, endpoint, fallback) {
    if (!path) return;
    const response = await api.get(endpoint, { params: { path }, responseType: "blob" });
    saveBlob(response.data, path.split(/[\\/]/).pop() || fallback);
  }

  async function downloadPdf() {
    const path = txtPath(report);
    const response = await api.get("/elt/download/pdf", { params: path ? { path } : {}, responseType: "blob" });
    saveBlob(response.data, "rapport-elt.pdf");
  }

  const pageActions = (
    <div className="actions elt-primary-actions">
      <button
        className="btn btn-primary elt-btn elt-btn--primary"
        onClick={handleLaunchClick}
        disabled={runButtonDisabled}
        title={watcherActive ? "Surveillance locale active. Désactivez-la avant de lancer un ELT manuel." : activeRun ? "Traitement ELT en cours." : ""}
      >
        {isStartingRun || activeRun ? <Loader2 className="spin" size={18} /> : <PlayCircle size={18} />}
        {isStartingRun || activeRun ? "Traitement en cours…" : "Lancer ELT"}
      </button>
      {watcherActive ? (
        <button className="btn btn-secondary" onClick={stopWatch} disabled={stopWatcherDisabled} title={isStoppingWatcher ? "Arrêt de la surveillance en cours." : ""}>
          {isStoppingWatcher ? <Loader2 className="spin" size={18} /> : <Square size={18} />}
          Désactiver surveillance locale
        </button>
      ) : (
        <button
          className="btn btn-secondary"
          onClick={startWatch}
          disabled={startWatcherDisabled}
          title={activeRun ? "Traitement ELT en cours. La surveillance locale ne peut pas être activée pendant l’exécution." : ""}
        >
          {isStartingWatcher ? <Loader2 className="spin" size={18} /> : <Power size={18} />}
          Activer surveillance locale
        </button>
      )}
      <button className="btn btn-secondary" onClick={refreshPage} disabled={refreshDisabled}>
        <RefreshCw className={isRefreshing ? "spin" : ""} size={18} />
        Actualiser
      </button>
    </div>
  );

  return (
    <Layout
      eyebrow="Traitements"
      title="Traitement ELT"
      subtitle="Supervisez les flux, exécutions et contrôles de traitement."
      action={pageActions}
      hideSidebar
      className="app-shell--elt"
    >
      <div className="elt-premium-page">
        <div className="elt-animated-bg" aria-hidden="true">
          <span className="elt-bg-blob elt-bg-blob--blue" />
          <span className="elt-bg-blob elt-bg-blob--pink" />
          <span className="elt-bg-blob elt-bg-blob--orange" />
          <span className="elt-bg-wave elt-bg-wave--one" />
          <span className="elt-bg-wave elt-bg-wave--two" />
          <span className="elt-bg-mesh" />
        </div>
        <div className="elt-bg-waves" aria-hidden="true" />

      {(connectionChecking || showModeChoice) && (
      <section className="elt-panel elt-launch-panel elt-reveal elt-reveal--delay-1">
        {connectionChecking && <div className="elt-checking"><Loader2 className="spin" size={18} />Vérification des connexions...</div>}

        {showModeChoice && (
          <>
            <h3 className="elt-choice-title">Choix du mode de traitement</h3>
            <div className="elt-mode-grid">
              <button className="elt-mode-card" onClick={() => startRun("FTP_DIRECT")} disabled={loading || isStartingRun || activeRun || watcherActive}>
                <span>Traitement direct depuis FTP</span>
                <small>Traite directement les fichiers présents sur le serveur FTP sans copie locale.</small>
              </button>
              <button className="elt-mode-card" onClick={() => startRun("FTP_TO_LOCAL")} disabled={loading || isStartingRun || activeRun || watcherActive}>
                <span>Récupération FTP puis traitement local</span>
                <small>Récupère les fichiers depuis FTP vers le dossier local puis lance le traitement.</small>
              </button>
            </div>
          </>
        )}
      </section>
      )}

      {hasStartedEltFlow && connections && (
        <ConnectionCards connections={connections} watchStatus={watchStatus} runStatus={runStatus} report={report} />
      )}

      {shouldShowReport && (
        <ReportsPanel
          report={report}
          txtReport={txtReport}
          onOpenTechnical={openTechnicalTasks}
          onDownloadPdf={downloadPdf}
        />
      )}

      <ArchiveFilesPanel
        filesAdv={filteredAdvFiles}
        filesRev={filteredRevFiles}
        search={archiveSearch}
        onSearch={setArchiveSearch}
      />

      {shouldShowFreshnessPanel && <BiSyncPanel report={report} navigate={navigate} />}

      {toast && <Toast {...toast} onClose={() => setToast(null)} />}

      {showTechnical && (
        <TechnicalModal
          data={technicalData}
          onClose={() => setShowTechnical(false)}
          onDownload={() => download(technicalCsvPath(report), "/elt/download/csv", "suivi-technique.csv")}
        />
      )}
      </div>
    </Layout>
  );
}

function ConnectionCards({ connections, watchStatus, runStatus, report }) {
  const oracleOk = connections?.oracle_ok ?? runStatus?.oracle_ok ?? report?.oracle_ok;
  const ftpOk = connections?.ftp_ok ?? runStatus?.ftp_ok ?? report?.ftp_ok;
  const latestStatus = runStatus?.status || report?.status || "-";
  const lastKnown = !connections && !runStatus?.active && report;
  const oracleBlocked = connections && oracleOk === false;
  const modeValue = oracleBlocked ? "Non disponible" : scenarioLabel(report?.scenario || runStatus?.scenario || runStatus?.user_mode);
  const statusValue = oracleBlocked ? "Traitement bloqué" : runStatus?.active ? "Traitement en cours" : statusLabel(latestStatus);

  return (
    <section className="elt-status-grid elt-reveal elt-reveal--delay-2">
      <MiniCard title="Oracle" value={oracleOk === true ? "Connecté" : oracleOk === false ? "Indisponible" : "Non vérifié"} detail={lastKnown ? "Dernier état connu" : connections ? "Vérifié maintenant" : "En attente de vérification"} icon={Database} tone="oracle" checked={oracleOk === true} />
      <MiniCard title="FTP" value={ftpOk === true ? "Disponible" : ftpOk === false ? "Indisponible" : "Non vérifié"} detail={lastKnown ? "Dernier état connu" : connections ? "Vérifié maintenant" : "En attente de vérification"} icon={CloudUpload} tone="ftp" checked={ftpOk === true} />
      <MiniCard title="Mode" value={modeValue} detail={oracleBlocked ? "Oracle non validé" : runStatus?.active ? "Scénario actif" : report ? "Dernier scénario" : "En attente"} icon={Activity} tone="mode" />
      <MiniCard title="Statut" value={statusValue} detail={oracleBlocked ? "Oracle indisponible" : runStatus?.active ? "Traitement démarré" : "Dernier état connu"} icon={Clock3} tone="status" checked={String(latestStatus).toUpperCase() === "COMPLETED"} />
    </section>
  );
}

function MiniCard({ title, value, detail, icon: Icon, tone, checked = false }) {
  return (
    <article className={`elt-status-card ${tone} elt-status-card--${tone}`}>
      <span className="elt-status-decoration" aria-hidden="true" />
      {checked && <span className="elt-status-check" aria-hidden="true" />}
      <div className="elt-status-icon"><Icon size={22} /></div>
      <div className="elt-status-content">
        <span className="elt-status-title">{title}</span>
        <strong className="elt-status-value">{value}</strong>
        {detail && <small className="elt-status-subtitle">{detail}</small>}
      </div>
    </article>
  );
}

function Info({ label, value }) {
  return <div className="elt-info-tile"><span>{label}</span><strong>{value || "-"}</strong></div>;
}

function ReportsPanel({ report, txtReport, onOpenTechnical, onDownloadPdf }) {
  return (
    <section className="elt-panel elt-report-print elt-reveal elt-reveal--delay-2">
      <div className="elt-section-title">
        <div>
          <h2>{REPORT_DISPLAY_NAME}</h2>
        </div>
        {report && <span className={badgeClass(report.status)}>{statusLabel(report.status)}</span>}
      </div>

      <div className="elt-report-meta clean">
        <Info label="Statut global métier" value={report.status_label || statusLabel(report.status)} />
        <Info label="Scénario métier" value={report.scenario_label || scenarioLabel(report.scenario)} />
        <Info label="Date génération" value={report.employee_report?.generated_at} />
        <Info label="Run ID" value={report.run_id} />
      </div>
      <div className="actions elt-report-buttons">
        <button className="btn btn-secondary" onClick={() => onOpenTechnical()}><Eye size={18} />Voir tableau technique</button>
        <button className="btn btn-secondary" onClick={onDownloadPdf}><FileText size={18} />Télécharger rapport PDF</button>
      </div>
      <BusinessReportText text={txtReport} />
    </section>
  );
}

function BusinessReportText({ text }) {
  const normalizeReportLine = (value) =>
    String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[’']/g, "'")
      .toUpperCase();
  const joinWords = (...words) => words.join(" ");
  const isHiddenReportSection = (line) => {
    const normalized = normalizeReportLine(line);
    return [
      joinWords("RESUME", "GLOBAL"),
      joinWords("SUIVI", "TECHNIQUE", "RESUME"),
      joinWords("TABLES", "MISES", "A", "JOUR"),
    ].includes(normalized);
  };
  const isHiddenReportLine = (line) => {
    const normalized = normalizeReportLine(line);
    const hiddenPrefixes = [
      ["TACHES", "TOTALES"],
      ["TACHES", "REUSSIES"],
      ["TACHES", "ECHOUEES"],
      ["TACHES", "BLOQUEES"],
      ["TACHES", "SANS", "DONNEES"],
      ["RETRIES", "EFFECTUES"],
      ["FALLBACK", "UTILISE"],
    ].map((parts) => joinWords(...parts));
    return (
      hiddenPrefixes.some((prefix) => normalized.startsWith(prefix)) ||
      normalized.includes(joinWords("LE", "TRAITEMENT", "S'EST", "TERMINE", "AVEC", "SUCCES"))
    );
  };
  const sectionTitles = new Set([
    "RAPPORT MÉTIER ELT - SOS SOLDE",
    REPORT_DISPLAY_NAME.toUpperCase(),
    "INFORMATIONS GÉNÉRALES",
    "INFORMATIONS GENERALES",
    "FLUX AVANCE",
    "FLUX REMBOURSEMENT",
    "DIAGNOSTIC",
    "CONCLUSION MÉTIER",
    "CONCLUSION METIER",
  ]);
  const lines = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !/^=+$/.test(line) && !/^-+$/.test(line))
    .filter((line) => !line.toLowerCase().includes("rapport généré automatiquement"))
    .filter((line) => !isHiddenReportLine(line));

  if (!lines.length) return null;

  const sections = [];
  let current = { title: "Rapport métier", rows: [] };
  let skippingSection = false;
  lines.forEach((line) => {
    const normalized = line.toUpperCase();
    const isHiddenSection = isHiddenReportSection(line);
    const isSection = isHiddenSection || sectionTitles.has(normalized) || (normalized === line && line.length < 70 && !line.includes(":"));
    if (isSection) {
      skippingSection = isHiddenSection;
      if (skippingSection) return;
      if (current.rows.length || current.title !== "Rapport métier") sections.push(current);
      current = { title: normalized.includes("SOS SOLDE") ? REPORT_DISPLAY_NAME : line, rows: [] };
    } else {
      if (skippingSection) return;
      current.rows.push(line);
    }
  });
  if (current.rows.length || current.title !== "Rapport métier") sections.push(current);

  return (
    <article className="elt-report-clean">
      {sections.map((section, sectionIndex) => (
        <section className="elt-report-section" key={`${section.title}-${sectionIndex}`}>
          <h3>{section.title}</h3>
          <div className="elt-report-section-body">
            {section.rows.map((line, index) => {
              const hasColon = line.includes(":");
              if (hasColon) {
                const [label, ...rest] = line.split(":");
                return (
                  <div className="elt-report-kv" key={`${line}-${index}`}>
                    <span>{label.trim()}</span>
                    <strong>{rest.join(":").trim() || "-"}</strong>
                  </div>
                );
              }
              return <p key={`${line}-${index}`}>{line}</p>;
            })}
          </div>
        </section>
      ))}
    </article>
  );
}

function ArchiveFilesPanel({ filesAdv, filesRev, search, onSearch }) {
  return (
    <section className="elt-panel elt-archives-panel elt-reveal elt-reveal--delay-3">
      <div className="elt-section-title">
        <div>
          <h2>Suivi des fichiers traités</h2>
        </div>
        <div className="actions">
          <label className="elt-search">
            <Search size={16} />
            <input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Rechercher un fichier" />
          </label>
        </div>
      </div>
      <div className="elt-archive-split">
        <ArchiveFileTable title="Tables archives - Avance" rows={filesAdv} columns={ADV_FILE_COLUMNS} accent="magenta" />
        <ArchiveFileTable title="Tables archives - Remboursement" rows={filesRev} columns={REV_FILE_COLUMNS} accent="cyan" />
      </div>
    </section>
  );
}

function ArchiveFileTable({ title, rows, columns, accent }) {
  return (
    <article className={`elt-archive-card ${accent}`}>
      <div className="elt-archive-title">
        <Database size={20} />
        <div>
          <h3>{title}</h3>
          <span>{rows.length} fichier(s)</span>
        </div>
      </div>
      <div className="elt-table-wrap">
        <table className="elt-table archive-files">
          <thead>
            <tr>{columns.map(([, label]) => <th key={label}>{label}</th>)}</tr>
          </thead>
          <tbody>
            {rows.length ? rows.map((row, index) => (
              <tr key={`${title}-${row.fichier}-${index}`}>
                {columns.map(([key]) => (
                  <td key={key}>{renderFileCell(key, row[key])}</td>
                ))}
              </tr>
            )) : (
              <tr><td className="empty-cell" colSpan={columns.length}>-</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function renderFileCell(key, value) {
  if (["date_fichier", "date_traitement"].includes(key)) {
    return formatArchiveDate(value);
  }
  if (["chargement", "detail", "aggregation", "service", "parc", "archivage"].includes(key)) {
    return <span className={badgeClass(value)}>{value || "Non renseigné"}</span>;
  }
  return value ?? "-";
}

function BiSyncPanel({ report, navigate }) {
  const latestStatus = String(report?.status || "").toUpperCase();
  const oracleState = oracleSyncState(latestStatus);
  const [nextRefresh, setNextRefresh] = useState(() => getNextPowerBiRefresh());

  useEffect(() => {
    const timer = window.setInterval(() => setNextRefresh(getNextPowerBiRefresh()), 60000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section className="elt-panel elt-bi-sync-panel elt-reveal elt-reveal--delay-3">
      <div className="elt-section-title">
        <div>
          <h2>Pilotage de fraîcheur décisionnelle</h2>
        </div>
      </div>

      <div className="elt-bi-sync-grid">
        <div className={`elt-bi-sync-item elt-bi-sync-item--last ${latestStatus === "COMPLETED" ? "success" : "info"}`}>
          <span>Dernier ELT</span>
          <strong>{eltSyncLabel(latestStatus)}</strong>
        </div>
        <div className="elt-bi-sync-item elt-bi-sync-item--oracle success">
          <span>Oracle</span>
          <strong><span className={oracleState.className}>{oracleState.label}</span></strong>
        </div>
        <div className="elt-bi-sync-item elt-bi-sync-item--refresh accent">
          <span>Prochain rafraîchissement</span>
          <strong>{nextRefresh.isTomorrow ? `demain à ${nextRefresh.label}` : nextRefresh.label}</strong>
        </div>
      </div>

      <div className="actions elt-bi-actions">
        <button className="btn btn-primary" type="button" onClick={() => navigate("/dashboard/service-sos?reload=1")}>
          <RefreshCw size={18} />
          Recharger dashboard Service SOS
        </button>
        <button className="btn btn-primary" type="button" onClick={() => navigate("/dashboard/parc-service-sos?reload=1")}>
          <RefreshCw size={18} />
          Recharger dashboard Parc Service SOS
        </button>
      </div>
    </section>
  );
}

function Toast({ type, text, title, message, actionLabel, onAction, secondaryActionLabel, onSecondaryAction, onClose }) {
  const displayMessage = message || text;
  const Icon = type === "success" ? CheckCircle2 : type === "error" ? AlertCircle : type === "warning" ? ShieldAlert : InfoIcon;
  return (
    <div className={`elt-toast ${type}`} role="status" aria-live="polite">
      <div className="elt-toast-icon" aria-hidden="true">
        <Icon size={18} />
      </div>
      <div className="elt-toast-body">
        {title && <strong>{title}</strong>}
        {displayMessage && <span>{displayMessage}</span>}
        {(actionLabel || secondaryActionLabel) && (
          <div className="elt-toast-actions">
            {actionLabel && onAction && (
              <button
                className="elt-toast-action"
                type="button"
                onClick={() => {
                  onAction();
                  onClose();
                }}
              >
                {actionLabel}
              </button>
            )}
            {secondaryActionLabel && onSecondaryAction && (
              <button className="elt-toast-action elt-toast-action--secondary" type="button" onClick={onSecondaryAction}>
                {secondaryActionLabel}
              </button>
            )}
          </div>
        )}
      </div>
      <button type="button" onClick={onClose} aria-label="Fermer la notification">×</button>
    </div>
  );
}

function TechnicalModal({ data, onClose, onDownload }) {
  const columns = data.columns?.length ? data.columns : TECHNICAL_COLUMNS;
  const rows = data.rows || [];

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="elt-modal-backdrop elt-technical-modal-overlay"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="elt-modal elt-technical-modal" role="dialog" aria-modal="true">
        <div className="elt-section-title elt-technical-modal-header">
          <div>
            <h2>Tableau technique des tâches ELT</h2>
            <p>Détail technique de l’exécution des tâches</p>
          </div>
          <div className="actions elt-technical-modal-actions">
            <button className="btn btn-secondary" onClick={onDownload}><Download size={18} />Télécharger CSV</button>
            <button className="btn btn-primary" onClick={onClose}>Fermer</button>
          </div>
        </div>
        <div className="elt-table-wrap no-pad elt-technical-modal-body elt-technical-table-wrapper">
          <table className="elt-table elt-technical-table">
            <thead>
              <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
            </thead>
            <tbody>
              {rows.length ? rows.map((row, index) => (
                <tr key={`${row.task_name}-${index}`}>
                  {columns.map((column) => (
                    <td key={column}>
                      {column === "status" ? <span className={badgeClass(row[column])}>{statusLabel(row[column])}</span> : row[column] || "-"}
                    </td>
                  ))}
                </tr>
              )) : (
                <tr><td className="empty-cell" colSpan={columns.length}>-</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
