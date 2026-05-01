import { Plus, RefreshCw, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, getApiError } from "../api/api";
import Layout from "../components/Layout";

export default function AdminDepartmentsPage() {
  const [departements, setDepartements] = useState([]);
  const [droits, setDroits] = useState([]);
  const [selectedDepartement, setSelectedDepartement] = useState("");
  const [selectedDroits, setSelectedDroits] = useState([]);
  const [droitToAdd, setDroitToAdd] = useState("");
  const [newDepartement, setNewDepartement] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [rightsError, setRightsError] = useState("");
  const [loadingRights, setLoadingRights] = useState(false);

  const availableDroits = useMemo(
    () =>
      droits.filter(
        (droit) =>
          !selectedDroits.some((item) => item.nom_droit === droit.nom_droit)
      ),
    [droits, selectedDroits]
  );

  async function loadData() {
    setError("");
    setRightsError("");

    try {
      const [depsResponse, droitsResponse] = await Promise.all([
        api.get("/admin/departements"),
        api.get("/admin/droits"),
      ]);

      const deps = Array.isArray(depsResponse.data) ? depsResponse.data : [];
      const allDroits = Array.isArray(droitsResponse.data)
        ? droitsResponse.data
        : [];

      setDepartements(deps);
      setDroits(allDroits);

      if (
        selectedDepartement &&
        !deps.some((item) => item.nom_departement === selectedDepartement)
      ) {
        setSelectedDepartement("");
        setSelectedDroits([]);
        setDroitToAdd("");
      }
    } catch (err) {
      setError(getApiError(err, "Erreur chargement départements/permissions."));
    }
  }

  async function loadDepartmentRights(nom) {
    setRightsError("");
    setSelectedDroits([]);
    setDroitToAdd("");

    if (!nom) return;

    setLoadingRights(true);

    try {
      const response = await api.get(
        `/admin/departements/by-name/${encodeURIComponent(nom)}/droits`
      );

      setSelectedDroits(response.data?.droits || []);
    } catch (err) {
      setSelectedDroits([]);
      setRightsError(
        getApiError(err, "Département introuvable ou supprimé.")
      );
    } finally {
      setLoadingRights(false);
    }
  }

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createDepartement(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setRightsError("");

    try {
      const response = await api.post("/admin/departements", {
        nom_departement: newDepartement,
      });

      const createdName = response.data?.nom_departement;

      setMessage("Département créé avec succès.");
      setNewDepartement("");

      await loadData();

      if (createdName) {
        setSelectedDepartement(createdName);
        await loadDepartmentRights(createdName);
      }
    } catch (err) {
      setError(getApiError(err, "Erreur création département."));
    }
  }

  async function deleteDepartement(nom) {
    if (!confirm(`Supprimer le département ${nom} ?`)) return;

    setError("");
    setMessage("");
    setRightsError("");

    try {
      await api.delete(`/admin/departements/by-name/${encodeURIComponent(nom)}`);

      setMessage("Département supprimé avec succès.");

      setDepartements((prev) =>
        prev.filter((item) => item.nom_departement !== nom)
      );

      if (selectedDepartement === nom) {
        setSelectedDepartement("");
        setSelectedDroits([]);
        setDroitToAdd("");
      }

      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur suppression département."));
    }
  }

  async function addPermission(event) {
    event.preventDefault();

    if (!selectedDepartement || !droitToAdd) return;

    setError("");
    setMessage("");
    setRightsError("");

    try {
      await api.post(
        `/admin/departements/by-name/${encodeURIComponent(
          selectedDepartement
        )}/droits/${encodeURIComponent(droitToAdd)}`
      );

      setMessage("Permission accordée au département.");
      await loadDepartmentRights(selectedDepartement);
    } catch (err) {
      setRightsError(getApiError(err, "Erreur ajout permission."));
    }
  }

  async function removePermission(nomDroit) {
    if (!selectedDepartement || !nomDroit) return;

    setError("");
    setMessage("");
    setRightsError("");

    try {
      await api.delete(
        `/admin/departements/by-name/${encodeURIComponent(
          selectedDepartement
        )}/droits/${encodeURIComponent(nomDroit)}`
      );

      setMessage("Permission retirée du département.");
      await loadDepartmentRights(selectedDepartement);
    } catch (err) {
      setRightsError(getApiError(err, "Erreur retrait permission."));
    }
  }

  return (
    <Layout
      title="Départements & permissions"
      subtitle="Accorder ou retirer les permissions des départements."
    >
      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      <div className="grid grid-2">
        <div className="card">
          <h2>Nouveau département</h2>

          <form className="form" onSubmit={createDepartement}>
            <div className="input-group">
              <label>Nom département</label>
              <input
                className="input"
                value={newDepartement}
                onChange={(event) => setNewDepartement(event.target.value)}
                placeholder="ex : technique"
                required
              />
            </div>

            <button className="btn btn-primary" type="submit">
              <Plus size={18} />
              Créer département
            </button>
          </form>
        </div>

        <div className="card">
          <h2>Départements</h2>

          <button className="btn btn-secondary" onClick={loadData}>
            <RefreshCw size={18} />
            Actualiser
          </button>

          <div className="table-wrap" style={{ marginTop: 16 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Nom</th>
                  <th>Actions</th>
                </tr>
              </thead>

              <tbody>
                {departements.map((item) => (
                  <tr key={item.id}>
                    <td>{item.nom_departement}</td>
                    <td>
                      <button
                        className="btn btn-danger"
                        onClick={() =>
                          deleteDepartement(item.nom_departement)
                        }
                      >
                        <Trash2 size={16} />
                        Supprimer
                      </button>
                    </td>
                  </tr>
                ))}

                {departements.length === 0 && (
                  <tr>
                    <td colSpan="2">Aucun département.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h2>Permissions du département</h2>

        <div className="form">
          <div className="input-group">
            <label>Département</label>

            <select
              className="select"
              value={selectedDepartement}
              onChange={async (event) => {
                const next = event.target.value;
                setSelectedDepartement(next);
                await loadDepartmentRights(next);
              }}
            >
              <option value="">Sélectionnez un département</option>

              {departements.map((item) => (
                <option key={item.id} value={item.nom_departement}>
                  {item.nom_departement}
                </option>
              ))}
            </select>
          </div>

          {!selectedDepartement && (
            <div className="alert alert-info">
              Sélectionnez un département pour gérer ses permissions.
            </div>
          )}

          {rightsError && (
            <div className="alert alert-error">{rightsError}</div>
          )}

          {selectedDepartement && (
            <>
              <form className="actions" onSubmit={addPermission}>
                <select
                  className="select"
                  value={droitToAdd}
                  onChange={(event) => setDroitToAdd(event.target.value)}
                  disabled={!availableDroits.length || loadingRights}
                >
                  <option value="">Choisir une permission</option>

                  {availableDroits.map((droit) => (
                    <option key={droit.id} value={droit.nom_droit}>
                      {droit.nom_droit}
                    </option>
                  ))}
                </select>

                <button
                  className="btn btn-success"
                  disabled={!droitToAdd || loadingRights}
                  type="submit"
                >
                  <Plus size={18} />
                  Accorder
                </button>
              </form>

              <div className="rights-grid">
                {selectedDroits.map((droit) => (
                  <div key={droit.id} className="right-check">
                    <span>{droit.nom_droit}</span>

                    <button
                      className="btn btn-secondary"
                      onClick={() => removePermission(droit.nom_droit)}
                    >
                      <X size={16} />
                      Retirer
                    </button>
                  </div>
                ))}

                {!loadingRights &&
                  selectedDepartement &&
                  selectedDroits.length === 0 &&
                  !rightsError && (
                    <div className="alert alert-info">
                      Aucune permission accordée à ce département.
                    </div>
                  )}
              </div>
            </>
          )}
        </div>
      </div>
    </Layout>
  );
}