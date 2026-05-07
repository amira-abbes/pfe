import {
  Activity,
  BarChart3,
  Clock3,
  Database,
  Download,
  Eye,
  FileText,
  Loader2,
  PlayCircle,
  Power,
  Printer,
  RefreshCw,
  Search,
  ShieldAlert,
  Square,
  Wifi,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api, getApiError } from "../api/api";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

const POWER_BI_URL = import.meta.env.VITE_POWER_BI_ELT_URL || "";

const FINAL_STATUSES = new Set(["COMPLETED", "NO_DATA", "FAILED", "PARTIAL_FAILURE", "STOPPED"]);
const ACTIVE_RUN_STATUSES = new Set(["RUNNING", "INITIALIZING", "PROCESSING"]);

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

function badgeClass(value) {
  const key = String(value || "").toUpperCase();
  if (["COMPLETED", "SUCCESS", "SUCCÈS", "OK"].includes(key)) return "elt-badge success";
  if (["FAILED", "FAILED_INSERT", "FAILED_CONTROL", "ÉCHEC", "ECHEC"].includes(key)) return "elt-badge danger";
  if (["PARTIAL_FAILURE", "WATCHER_ACTIVE", "EN ATTENTE", "FICHIER RÉCENT - CONSERVATION 7 JOURS"].includes(key)) return "elt-badge warning";
  if (["RUNNING", "INITIALIZING", "READY"].includes(key)) return "elt-badge info";
  if (["STOPPED", "NON CONCERNÉ", "NON CONCERNE"].includes(key)) return "elt-badge dark";
  return "elt-badge neutral";
}

function yesNoBadge(value) {
  if (value === true) return <span className="elt-badge success">Connecté</span>;
  if (value === false) return <span className="elt-badge danger">Indisponible</span>;
  return <span className="elt-badge neutral">Non vérifié</span>;
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

function formatSeconds(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return "-";
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return minutes ? `${minutes} min ${rest}s` : `${rest}s`;
}

export default function AdminEltPage() {
  const { hasRight } = useAuth();
  const canRunElt = hasRight("lancer_elt");

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [connections, setConnections] = useState(null);
  const [connectionChecking, setConnectionChecking] = useState(false);
  const [runStatus, setRunStatus] = useState(null);
  const [watchStatus, setWatchStatus] = useState(null);
  const [report, setReport] = useState(null);
  const [txtReport, setTxtReport] = useState("");
  const [archiveFilesAdv, setArchiveFilesAdv] = useState([]);
  const [archiveFilesRev, setArchiveFilesRev] = useState([]);
  const [archiveMessage, setArchiveMessage] = useState("");
  const [archiveSearch, setArchiveSearch] = useState("");
  const [showModeChoice, setShowModeChoice] = useState(false);
  const [showWatcherConflict, setShowWatcherConflict] = useState(false);
  const [technicalData, setTechnicalData] = useState({ columns: [], rows: [] });
  const [showTechnical, setShowTechnical] = useState(false);

  const runPollRef = useRef(null);
  const watchPollRef = useRef(null);
  const pendingLaunchAfterWatcherStop = useRef(false);

  const activeRun = ACTIVE_RUN_STATUSES.has(String(runStatus?.status || "").toUpperCase()) || runStatus?.active === true;
  const watcherActive = isWatcherActive(watchStatus);

  useEffect(() => {
    refreshPage(false);
    return () => {
      window.clearInterval(runPollRef.current);
      window.clearInterval(watchPollRef.current);
    };
  }, []);

  useEffect(() => {
    window.clearInterval(runPollRef.current);
    if (activeRun) {
      console.log("[ELT UI] polling started");
      runPollRef.current = window.setInterval(loadRunStatus, 2000);
    }
    return () => {
      if (runPollRef.current) console.log("[ELT UI] polling stopped cleanup");
      window.clearInterval(runPollRef.current);
    };
  }, [activeRun]);

  useEffect(() => {
    window.clearInterval(watchPollRef.current);
    if (watcherActive) {
      console.log("[ELT UI] watcher polling started");
      watchPollRef.current = window.setInterval(async () => {
        const nextWatchStatus = await loadWatchStatus();
        const state = String(nextWatchStatus?.state || nextWatchStatus?.status || "").toUpperCase();
        if (state === "PROCESSING") {
          await loadRunStatus();
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

  async function refreshPage(checkConnections = true) {
    console.log("[ELT UI] refresh all");
    setLoading(true);
    setError("");
    setShowModeChoice(false);
    try {
      await Promise.all([
        checkConnections ? loadConnections() : Promise.resolve(null),
        loadWatchStatus(),
        loadRunStatus(),
        loadLatestReport(),
        loadArchiveFiles(),
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function loadConnections() {
    try {
      const response = await api.get("/elt/check-connections");
      console.log("[ELT UI] check connections", response.data);
      setConnections(response.data);
      return response.data;
    } catch (err) {
      setError(getApiError(err, "Impossible de vérifier Oracle et FTP."));
      return null;
    }
  }

  async function loadWatchStatus() {
    try {
      const response = await api.get("/elt/watch/status");
      console.log("[ELT UI] watch status", response.data);
      console.log("[ELT UI] isWatcherActive", isWatcherActive(response.data));
      setWatchStatus(response.data);
      return response.data;
    } catch (err) {
      setError(getApiError(err, "Impossible de charger la surveillance locale."));
      return null;
    }
  }

  async function loadRunStatus() {
    try {
      const response = await api.get("/elt/run/status");
      const data = response.data;
      console.log("[ELT UI] run status", data);
      setRunStatus(data);
      const status = String(data?.status || "").toUpperCase();
      if (FINAL_STATUSES.has(status)) {
        window.clearInterval(runPollRef.current);
        console.log("[ELT UI] polling stopped final status=", status);
        await Promise.all([loadLatestReport(), loadArchiveFiles(), loadWatchStatus()]);
      }
      return data;
    } catch (err) {
      setError(getApiError(err, "Impossible de suivre le traitement ELT."));
      return null;
    }
  }

  async function loadLatestReport() {
    try {
      const response = await api.get("/elt/latest-report");
      if (response.data?.success === false && !response.data?.run_id) return;
      setReport(response.data);
      await loadTxtReport(response.data);
    } catch {
      setReport(null);
      setTxtReport("");
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
      const nextMessage = response.data?.success === false ? response.data?.message : "";
      setArchiveMessage(nextMessage || "");
    } catch (err) {
      setArchiveFilesAdv([]);
      setArchiveFilesRev([]);
      setArchiveMessage(getApiError(err, "Impossible de charger le suivi des fichiers traités."));
    }
  }

  async function handleLaunchClick() {
    console.log("[ELT UI] lancer clicked");
    setError("");
    setMessage("");
    setShowModeChoice(false);

    const status = await loadRunStatus();
    if (["RUNNING", "INITIALIZING"].includes(String(status?.status || "").toUpperCase())) {
      setMessage("Un traitement ELT est déjà en cours. Veuillez attendre la fin.");
      return;
    }

    const watcher = await loadWatchStatus();
    console.log("[ELT UI] watch status before launch", watcher);
    const watcherIsActive = isWatcherActive(watcher);
    console.log("[ELT UI] computed watcher active", watcherIsActive);
    if (watcherIsActive) {
      setShowWatcherConflict(true);
      pendingLaunchAfterWatcherStop.current = true;
      return;
    }

    await checkConnectionsAndLaunch();
  }

  async function checkConnectionsAndLaunch() {
    setLoading(true);
    setConnectionChecking(true);
    setError("");
    try {
      const data = await loadConnections();
      if (!data) return;

      if (!data.oracle_ok) {
        setMessage("Oracle indisponible. Impossible de lancer le traitement.");
        return;
      }

      if (data.ftp_ok) {
        setShowModeChoice(true);
        setMessage("Oracle et FTP sont disponibles. Choisissez le mode de traitement.");
        return;
      }

      console.log("[ELT UI] chosen mode", "LOCAL_ONLY");
      setMessage("Traitement local disponible. Le serveur FTP est indisponible. Le système utilise les fichiers présents dans le dossier local.");
      await startRun("LOCAL_ONLY");
    } catch (err) {
      setError(getApiError(err, "Impossible de vérifier Oracle et FTP."));
    } finally {
      setConnectionChecking(false);
      setLoading(false);
    }
  }

  async function startRun(userMode) {
    console.log("[ELT START] userMode=", userMode);
    console.log("[ELT UI] chosen mode", userMode);
    setLoading(true);
    setError("");
    setShowModeChoice(false);
    try {
      const response = await api.post("/elt/run/start", null, { params: { user_mode: userMode } });
      const data = response.data;
      console.log("[ELT START RESPONSE]", data);
      console.log("[ELT UI] start run response", data);
      if (data.watch_active) {
        setShowWatcherConflict(true);
        setMessage(data.message);
        return;
      }
      if (!data.success) {
        setError(data.message || data.error || "Lancement ELT impossible.");
        return;
      }
      setMessage("Traitement ELT lancé avec succès.");
      setRunStatus({ status: "RUNNING", active: true, user_mode: userMode, scenario_label: data.scenario_label });
      console.log("[ELT UI] polling started");
      await loadRunStatus();
    } catch (err) {
      setError(getApiError(err, "Erreur lors du lancement ELT."));
    } finally {
      setLoading(false);
    }
  }

  async function stopWatcherAndContinue() {
    setLoading(true);
    setError("");
    try {
      await api.post("/elt/watch/stop");
      setShowWatcherConflict(false);
      const watcher = await loadWatchStatus();
      if (isWatcherActive(watcher)) {
        setError("La surveillance locale est encore active. Veuillez réessayer.");
        return;
      }
      if (pendingLaunchAfterWatcherStop.current) {
        pendingLaunchAfterWatcherStop.current = false;
        await checkConnectionsAndLaunch();
      }
    } catch (err) {
      setError(getApiError(err, "Impossible de désactiver la surveillance locale."));
    } finally {
      setLoading(false);
    }
  }

  async function startWatch() {
    setLoading(true);
    setError("");
    try {
      const response = await api.post("/elt/watch/start");
      setMessage(response.data?.message || "Surveillance locale activée.");
      if (response.data?.success) {
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
      }
      await loadWatchStatus();
    } catch (err) {
      setError(getApiError(err, "Impossible d'activer la surveillance locale."));
    } finally {
      setLoading(false);
    }
  }

  async function stopWatch() {
    setLoading(true);
    setError("");
    try {
      const response = await api.post("/elt/watch/stop");
      setMessage(response.data?.message || "Surveillance locale désactivée.");
      await loadWatchStatus();
    } catch (err) {
      setError(getApiError(err, "Impossible de désactiver la surveillance locale."));
    } finally {
      setLoading(false);
    }
  }

  async function openTechnicalTasks() {
    const path = technicalCsvPath(report);
    if (!path) {
      setError("Aucun suivi technique des tâches n'est disponible.");
      return;
    }
    try {
      const response = await api.get("/elt/csv-data", { params: { path } });
      setTechnicalData(response.data || { columns: [], rows: [] });
      setShowTechnical(true);
    } catch (err) {
      setError(getApiError(err, "Impossible de charger le suivi technique des tâches."));
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

  function printReport() {
    window.print();
  }

  return (
    <Layout title="Pilotage ELT SOS Solde" subtitle="Supervision des flux Avance et Remboursement">
      <section className="elt-hero">
        <div className="elt-hero-brand">
          <img src="/tt-logo.png" alt="Tunisie Telecom" />
          <div>
            <span>Plateforme interne</span>
            <h2>Pilotage ELT SOS Solde</h2>
            <p>Supervision des flux Avance et Remboursement</p>
          </div>
        </div>
        <div className="elt-hero-actions">
          <button className="btn btn-primary" onClick={handleLaunchClick} disabled={!canRunElt || loading || activeRun}>
            {loading || activeRun ? <Loader2 className="spin" size={18} /> : <PlayCircle size={18} />}
            Lancer ELT
          </button>
          {watcherActive ? (
            <button className="btn btn-secondary" onClick={stopWatch} disabled={loading || activeRun}><Square size={18} />Désactiver surveillance locale</button>
          ) : (
            <button className="btn btn-secondary" onClick={startWatch} disabled={loading || activeRun}><Power size={18} />Activer surveillance locale</button>
          )}
          <button className="btn btn-secondary" onClick={() => refreshPage(true)} disabled={loading}><RefreshCw size={18} />Actualiser</button>
        </div>
      </section>

      <ConnectionCards connections={connections} watchStatus={watchStatus} runStatus={runStatus} report={report} />

      <section className="elt-panel elt-launch-panel">
        <div className="elt-section-title">
          <div>
            <h2>Actions de traitement</h2>
          </div>
        </div>

        {connectionChecking && <div className="elt-checking"><Loader2 className="spin" size={18} />Vérification des connexions...</div>}
        {message && <div className="alert alert-info">{message}</div>}
        {error && <div className="alert alert-error">{error}</div>}

        {connections && !connections.oracle_ok && (
          <div className="elt-blocker">
            <ShieldAlert size={22} />
            <strong>Oracle indisponible. Impossible de lancer le traitement.</strong>
          </div>
        )}

        {showModeChoice && (
          <>
            <h3 className="elt-choice-title">Choix du mode de traitement</h3>
            <div className="elt-mode-grid">
              <button className="elt-mode-card" onClick={() => startRun("FTP_DIRECT")} disabled={loading}>
                <span>Traitement direct depuis FTP</span>
                <small>Traite directement les fichiers présents sur le serveur FTP sans copie locale.</small>
              </button>
              <button className="elt-mode-card" onClick={() => startRun("FTP_TO_LOCAL")} disabled={loading}>
                <span>Récupération FTP puis traitement local</span>
                <small>Récupère les fichiers depuis FTP vers le dossier local puis lance le traitement.</small>
              </button>
            </div>
          </>
        )}
      </section>

      <RealtimeStatus status={runStatus} />

      {watcherActive && (
        <WatcherPanel
          status={watchStatus}
          loading={loading}
          runActive={activeRun}
          onStart={startWatch}
          onStop={stopWatch}
          onRefresh={loadWatchStatus}
        />
      )}

      <ReportsPanel
        report={report}
        txtReport={txtReport}
        onDownloadTxt={() => download(txtPath(report), "/elt/download/txt", "rapport-metier.txt")}
        onOpenTechnical={openTechnicalTasks}
        onDownloadPdf={downloadPdf}
        onPrint={printReport}
      />

      <ArchiveFilesPanel
        filesAdv={filteredAdvFiles}
        filesRev={filteredRevFiles}
        search={archiveSearch}
        onSearch={setArchiveSearch}
        message={archiveMessage}
        onRefresh={loadArchiveFiles}
      />

      <PowerBiPanel />

      {showWatcherConflict && (
        <div className="elt-modal-backdrop" role="presentation">
          <div className="elt-confirm-modal" role="dialog" aria-modal="true">
            <ShieldAlert size={30} />
            <h2>Surveillance locale active</h2>
            <p>La surveillance locale est active. Pour lancer un traitement manuel, désactivez d’abord la surveillance.</p>
            <div className="actions">
              <button className="btn btn-danger" onClick={stopWatcherAndContinue} disabled={loading}>
                <Square size={18} />
                Désactiver la surveillance et lancer
              </button>
              <button className="btn btn-secondary" onClick={() => setShowWatcherConflict(false)} disabled={loading}>
                Annuler
              </button>
            </div>
          </div>
        </div>
      )}

      {showTechnical && (
        <TechnicalModal
          data={technicalData}
          onClose={() => setShowTechnical(false)}
          onDownload={() => download(technicalCsvPath(report), "/elt/download/csv", "suivi-technique.csv")}
        />
      )}
    </Layout>
  );
}

function ConnectionCards({ connections, watchStatus, runStatus, report }) {
  const oracleOk = connections?.oracle_ok ?? runStatus?.oracle_ok ?? report?.oracle_ok;
  const ftpOk = connections?.ftp_ok ?? runStatus?.ftp_ok ?? report?.ftp_ok;
  const latestStatus = runStatus?.status || report?.status || "-";
  const lastKnown = !connections && !runStatus?.active && report;

  return (
    <section className="elt-status-grid">
      <MiniCard title="Oracle" value={oracleOk === true ? "Connecté" : oracleOk === false ? "Indisponible" : "Non vérifié"} detail={lastKnown ? "Dernier état connu" : connections ? "Vérifié maintenant" : "En attente de vérification"} icon={Database} tone={oracleOk ? "green" : "orange"} />
      <MiniCard title="FTP" value={ftpOk === true ? "Connecté" : ftpOk === false ? "Indisponible" : "Non vérifié"} detail={lastKnown ? "Dernier état connu" : connections ? "Vérifié maintenant" : "En attente de vérification"} icon={Wifi} tone={ftpOk ? "green" : "orange"} />
      <MiniCard title="Surveillance" value={isWatcherActive(watchStatus) ? "Active" : "Arrêtée"} icon={Activity} tone={isWatcherActive(watchStatus) ? "cyan" : "yellow"} />
      <MiniCard title="Dernier run" value={statusLabel(latestStatus)} detail={runStatus?.active ? "Traitement en cours" : "Dernier état connu"} icon={Clock3} tone="violet" />
      <MiniCard title="Scénario" value={scenarioLabel(report?.scenario || runStatus?.scenario || runStatus?.user_mode)} detail={runStatus?.active ? "Scénario actif" : report ? "Dernier scénario" : "-"} icon={PlayCircle} tone="magenta" />
    </section>
  );
}

function MiniCard({ title, value, detail, icon: Icon, tone }) {
  return (
    <article className={`elt-status-card ${tone}`}>
      <div className="elt-status-icon"><Icon size={20} /></div>
      <div>
        <span>{title}</span>
        <strong>{value}</strong>
        {detail && <small>{detail}</small>}
      </div>
    </article>
  );
}

function RealtimeStatus({ status }) {
  const currentStatus = String(status?.status || "STOPPED").toUpperCase();
  const active = ACTIVE_RUN_STATUSES.has(currentStatus) || status?.active;
  const progress = Number(status?.global_progress_percent || 0);
  if (!active) {
    return (
      <section className="elt-panel elt-realtime-idle">
        <div className="elt-section-title">
          <div>
            <h2>Suivi temps réel</h2>
            <p>Aucun traitement ELT actif pour le moment.</p>
          </div>
          <span className="elt-badge neutral">En attente</span>
        </div>
      </section>
    );
  }
  return (
    <section className="elt-panel elt-realtime-active">
      <div className="elt-section-title">
        <div>
          <h2>Suivi temps réel</h2>
          <p>{status?.message || "Aucun traitement actif pour le moment."}</p>
        </div>
        <span className={badgeClass(currentStatus)}>{statusLabel(currentStatus)}</span>
      </div>
      <Progress label="Progression globale" value={progress} />
      <div className="elt-progress-split">
        <Progress label="Avance" value={Number(status?.adv_progress_percent || 0)} />
        <Progress label="Remboursement" value={Number(status?.rev_progress_percent || 0)} />
      </div>
      <div className="elt-kpi-row no-pad">
        <Kpi label="Tâches terminées" value={status?.completed_count ?? 0} />
        <Kpi label="En cours" value={status?.running_count ?? 0} />
        <Kpi label="En attente" value={status?.waiting_count ?? 0} />
        <Kpi label="Échouées" value={status?.failed_count ?? 0} />
      </div>
      <div className="elt-live-details">
        <Info label="Tâche Avance en cours" value={status?.current_adv_task || "Aucune"} />
        <Info label="Tâche Remboursement en cours" value={status?.current_rev_task || "Aucune"} />
        <Info label="Temps écoulé" value={formatSeconds(status?.elapsed_seconds)} />
        <Info label="Temps restant estimé" value={formatSeconds(status?.estimated_remaining_seconds)} />
      </div>
    </section>
  );
}

function Progress({ label, value }) {
  const percent = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className="elt-progress-block">
      <div className="elt-progress-label"><span>{label}</span><strong>{percent}%</strong></div>
      <div className="elt-progress"><div style={{ width: `${percent}%` }} /></div>
    </div>
  );
}

function Kpi({ label, value }) {
  return <div className="elt-kpi"><span>{label}</span><strong>{value}</strong></div>;
}

function Info({ label, value }) {
  return <div className="elt-info-tile"><span>{label}</span><strong>{value || "-"}</strong></div>;
}

function WatcherPanel({ status, loading, runActive, onStart, onStop, onRefresh }) {
  return (
    <section className="elt-panel">
      <div className="elt-section-title">
        <div>
          <h2>Surveillance locale</h2>
          <p>{status?.message || "Surveillance locale non initialisée."}</p>
        </div>
        <div className="actions">
          {status?.active ? (
            <button className="btn btn-secondary" onClick={onStop} disabled={loading || runActive}><Square size={18} />Désactiver surveillance locale</button>
          ) : (
            <button className="btn btn-secondary" onClick={onStart} disabled={loading || runActive}><Power size={18} />Activer surveillance locale</button>
          )}
          <button className="btn btn-secondary" onClick={onRefresh} disabled={loading}><RefreshCw size={18} />Actualiser</button>
        </div>
      </div>
      <div className="elt-live-details">
        <Info label="État" value={status?.state_label || "Surveillance arrêtée"} />
        <div className="elt-info-tile"><span>Oracle</span>{yesNoBadge(status?.oracle_ok)}</div>
        <div className="elt-info-tile"><span>FTP</span>{yesNoBadge(status?.ftp_ok)}</div>
        <Info label="Dernier fichier détecté" value={status?.last_detected_file || "Aucun"} />
      </div>
    </section>
  );
}

function ReportsPanel({ report, txtReport, onDownloadTxt, onOpenTechnical, onDownloadPdf, onPrint }) {
  return (
    <section className="elt-panel elt-report-print">
      <div className="elt-section-title">
        <div>
          <h2>Rapports</h2>
        </div>
        {report && <span className={badgeClass(report.status)}>{statusLabel(report.status)}</span>}
      </div>

      {report ? (
        <>
          <div className="elt-report-meta clean">
            <Info label="Statut global métier" value={report.status_label || statusLabel(report.status)} />
            <Info label="Scénario métier" value={report.scenario_label || scenarioLabel(report.scenario)} />
            <Info label="Date génération" value={report.employee_report?.generated_at} />
            <Info label="Run ID" value={report.run_id} />
          </div>
          <div className="actions elt-report-buttons">
            <button className="btn btn-secondary" onClick={onDownloadTxt}><Download size={18} />Télécharger TXT</button>
            <button className="btn btn-secondary" onClick={onOpenTechnical}><Eye size={18} />Suivi technique des tâches</button>
            <button className="btn btn-secondary" onClick={onDownloadPdf}><FileText size={18} />Télécharger rapport PDF</button>
            <button className="btn btn-primary" onClick={onPrint}><Printer size={18} />Imprimer</button>
          </div>
          <BusinessReportText text={txtReport} />
        </>
      ) : (
        <div className="empty-cell">Aucun rapport métier disponible pour le moment.</div>
      )}
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

  if (!lines.length) return <div className="elt-report-clean empty">Rapport métier TXT non disponible.</div>;

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
      current = { title: line, rows: [] };
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

function ArchiveFilesPanel({ filesAdv, filesRev, search, onSearch, message, onRefresh }) {
  return (
    <section className="elt-panel">
      <div className="elt-section-title">
        <div>
          <h2>Suivi des fichiers traités</h2>
          <p>{message || "Lecture métier depuis ARCHIVE_ADV_TMP et ARCHIVE_REV_TMP."}</p>
        </div>
        <div className="actions">
          <label className="elt-search">
            <Search size={16} />
            <input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Rechercher un fichier" />
          </label>
          <button className="btn btn-secondary" onClick={onRefresh}><RefreshCw size={18} />Actualiser</button>
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
              <tr><td className="empty-cell" colSpan={columns.length}>Aucun fichier traité à afficher.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function renderFileCell(key, value) {
  if (["chargement", "detail", "aggregation", "service", "parc", "archivage"].includes(key)) {
    return <span className={badgeClass(value)}>{value || "Non renseigné"}</span>;
  }
  return value ?? "-";
}

function PowerBiPanel() {
  const configured = POWER_BI_URL.trim().length > 0;
  return (
    <section className="elt-panel">
      <div className="elt-section-title">
        <div>
          <h2>Dashboard Power BI</h2>
          <p>Visualisation décisionnelle des traitements ELT et indicateurs métier.</p>
        </div>
        {configured ? (
          <a className="btn btn-primary" href={POWER_BI_URL} target="_blank" rel="noreferrer"><BarChart3 size={18} />Voir dashboard Power BI</a>
        ) : (
          <span className="elt-badge neutral">Dashboard Power BI non configuré.</span>
        )}
      </div>
    </section>
  );
}

function TechnicalModal({ data, onClose, onDownload }) {
  const columns = data.columns?.length ? data.columns : TECHNICAL_COLUMNS;
  const rows = data.rows || [];
  return (
    <div className="elt-modal-backdrop" role="presentation">
      <div className="elt-modal" role="dialog" aria-modal="true">
        <div className="elt-section-title">
          <div>
            <h2>Suivi technique des tâches</h2>
            <p>Table technique affichée uniquement sur demande.</p>
          </div>
          <div className="actions">
            <button className="btn btn-secondary" onClick={onDownload}><Download size={18} />Télécharger</button>
            <button className="btn btn-primary" onClick={onClose}>Fermer</button>
          </div>
        </div>
        <div className="elt-table-wrap no-pad">
          <table className="elt-table">
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
                <tr><td className="empty-cell" colSpan={columns.length}>Aucune tâche technique disponible.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
