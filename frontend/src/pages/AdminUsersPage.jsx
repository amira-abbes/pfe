import { Plus, RefreshCw, UserX } from "lucide-react";
import { useEffect, useState } from "react";
import { api, getApiError } from "../api/api";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

export default function AdminUsersPage() {
  const { user: currentUser } = useAuth();

  const isSuperAdmin = currentUser?.role === "SUPER_ADMIN";
  const isAdmin = currentUser?.role === "ADMIN";

  const [users, setUsers] = useState([]);
  const [departements, setDepartements] = useState([]);
  const [form, setForm] = useState({
    email: "",
    nom_complet: "",
    departement_nom: "",
    role: "USER",
  });
  const [message, setMessage] = useState("");
  const [debugLink, setDebugLink] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function loadData() {
    setError("");

    try {
      if (isSuperAdmin) {
        const [usersResponse, depsResponse] = await Promise.all([
          api.get("/admin/users"),
          api.get("/admin/departements"),
        ]);

        const deps = Array.isArray(depsResponse.data) ? depsResponse.data : [];

        setUsers(usersResponse.data);
        setDepartements(deps);

        setForm((current) => ({
          ...current,
          departement_nom:
            current.departement_nom &&
            deps.some((d) => d.nom_departement === current.departement_nom)
              ? current.departement_nom
              : deps[0]?.nom_departement || "",
        }));
      } else {
        const usersResponse = await api.get("/admin/users");

        setUsers(usersResponse.data);
        setDepartements([]);

        setForm((current) => ({
          ...current,
          departement_nom: currentUser?.departement_nom || "",
          role: "USER",
        }));
      }
    } catch (err) {
      setError(getApiError(err, "Erreur chargement utilisateurs."));
    }
  }

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSuperAdmin, currentUser?.departement_nom]);

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function createUser(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setDebugLink("");
    setLoading(true);

    try {
      const payload = {
        email: form.email,
        nom_complet: form.nom_complet,
        role: isSuperAdmin ? form.role : "USER",
        departement_nom: isSuperAdmin
          ? form.departement_nom
          : currentUser?.departement_nom || form.departement_nom || "",
      };

      const response = await api.post("/admin/users", payload);

      setMessage(response.data.message || "Utilisateur créé.");
      setDebugLink(response.data.activation_link_debug || "");

      setForm((current) => ({
        ...current,
        email: "",
        nom_complet: "",
        role: "USER",
      }));

      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur création utilisateur."));
    } finally {
      setLoading(false);
    }
  }

  async function toggleStatus(user) {
    const action = user.est_actif ? "désactiver" : "réactiver";
    if (!confirm(`Voulez-vous ${action} le compte ${user.email} ?`)) return;

    setError("");
    setMessage("");

    try {
      const response = await api.patch(`/admin/users/by-email/${encodeURIComponent(user.email)}/status`, {
        est_actif: !user.est_actif,
      });

      setMessage(response.data.message || "Statut utilisateur mis à jour.");
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur mise à jour statut."));
    }
  }

  async function updateUserProfile(user, changes) {
    if (!isSuperAdmin) return;

    setError("");
    setMessage("");

    try {
      await api.patch(`/admin/users/by-email/${encodeURIComponent(user.email)}/profile`, {
        role: changes.role || user.role,
        departement_nom:
          changes.departement_nom ||
          user.departement_nom ||
          departements[0]?.nom_departement ||
          "",
      });

      setMessage("Profil utilisateur mis à jour.");
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur mise à jour profil utilisateur."));
    }
  }

  async function deleteUser(user) {
    if (!confirm(`Supprimer l’utilisateur ${user.email} ?`)) return;

    setError("");
    setMessage("");

    try {
      await api.delete(`/admin/users/by-email/${encodeURIComponent(user.email)}`);
      setMessage("Utilisateur supprimé.");
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur suppression utilisateur."));
    }
  }

  return (
    <Layout
      title="Gestion utilisateurs"
      subtitle="Créer un compte, envoyer le lien d’activation et gérer les statuts."
    >
      <div className="grid grid-2">
        <div className="card">
          <h2>Créer un utilisateur</h2>

          {error && <div className="alert alert-error">{error}</div>}
          {message && <div className="alert alert-success">{message}</div>}

          {debugLink && (
            <div className="alert alert-info">
              Lien activation debug :
              <br />
              <a href={debugLink}>{debugLink}</a>
            </div>
          )}

          <form className="form" onSubmit={createUser}>
            <div className="input-group">
              <label>Email</label>
              <input
                className="input"
                type="email"
                value={form.email}
                onChange={(event) => updateField("email", event.target.value)}
                required
              />
            </div>

            <div className="input-group">
              <label>Nom complet</label>
              <input
                className="input"
                value={form.nom_complet}
                onChange={(event) => updateField("nom_complet", event.target.value)}
                required
              />
            </div>

            {isSuperAdmin ? (
              <div className="input-group">
                <label>Département</label>
                <select
                  className="select"
                  value={form.departement_nom}
                  onChange={(event) =>
                    updateField("departement_nom", event.target.value)
                  }
                  required
                >
                  <option value="" disabled>
                    Choisir un département
                  </option>
                  {departements.map((item) => (
                    <option key={item.id} value={item.nom_departement}>
                      {item.nom_departement}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="input-group">
                <label>Département</label>
                <div className="input" style={{ display: "flex", alignItems: "center" }}>
                  {currentUser?.departement_nom || "Département associé à votre compte"}
                </div>
              </div>
            )}

            {isSuperAdmin ? (
              <div className="input-group">
                <label>Rôle</label>
                <select
                  className="select"
                  value={form.role}
                  onChange={(event) => updateField("role", event.target.value)}
                >
                  <option value="USER">USER</option>
                  <option value="ADMIN">ADMIN</option>
                </select>
              </div>
            ) : (
              <div className="input-group">
                <label>Rôle</label>
                <div className="input" style={{ display: "flex", alignItems: "center" }}>
                  USER
                </div>
              </div>
            )}

            <button
              className="btn btn-primary"
              disabled={loading || (isSuperAdmin && !form.departement_nom)}
            >
              <Plus size={18} />
              {loading ? "Création..." : "Créer utilisateur"}
            </button>
          </form>
        </div>

        <div className="card">
          <h2>Résumé</h2>

          <p>
            Après création, l’utilisateur reçoit un email avec un bouton
            d’activation. Il crée son mot de passe puis configure Authenticator.
          </p>

          {isAdmin && (
            <div className="alert alert-info">
              En tant qu’administrateur, vous gérez uniquement les utilisateurs
              de votre département.
            </div>
          )}

          <button className="btn btn-secondary" onClick={loadData}>
            <RefreshCw size={18} />
            Actualiser
          </button>
        </div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h2>Liste utilisateurs</h2>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Nom</th>
                <th>Département</th>
                <th>Rôle</th>
                <th>Statut compte</th>
                <th>Actif</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {users.map((item) => (
                <tr key={item.id}>
                  <td>{item.email}</td>
                  <td>{item.nom_complet}</td>

                  <td>
                    {isSuperAdmin ? (
                      <select
                        className="select"
                        value={item.departement_nom || ""}
                        onChange={(event) =>
                          updateUserProfile(item, {
                            departement_nom: event.target.value,
                          })
                        }
                      >
                        <option value="">Aucun département</option>
                        {departements.map((dep) => (
                          <option key={dep.id} value={dep.nom_departement}>
                            {dep.nom_departement}
                          </option>
                        ))}
                      </select>
                    ) : (
                      item.departement_nom || "-"
                    )}
                  </td>

                  <td>
                    {isSuperAdmin ? (
                      <select
                        className="select"
                        value={item.role}
                        onChange={(event) =>
                          updateUserProfile(item, { role: event.target.value })
                        }
                      >
                        <option value="USER">USER</option>
                        <option value="ADMIN">ADMIN</option>
                      </select>
                    ) : (
                      item.role
                    )}
                  </td>

                  <td>
                    <span
                      className={
                        item.est_actif && item.statut_compte === "ACTIVE"
                          ? "badge badge-green"
                          : "badge badge-orange"
                      }
                    >
                      {item.est_actif ? item.statut_compte : "Désactivé"}
                    </span>
                  </td>

                  <td>{item.est_actif ? "Oui" : "Non"}</td>

                  <td>
                    <div className="actions">
                      <button
                        className="btn btn-secondary"
                        onClick={() => toggleStatus(item)}
                      >
                        {item.est_actif ? "Désactiver" : "Réactiver"}
                      </button>

                      <button
                        className="btn btn-danger"
                        onClick={() => deleteUser(item)}
                      >
                        <UserX size={16} />
                        Supprimer
                      </button>
                    </div>
                  </td>
                </tr>
              ))}

              {users.length === 0 && (
                <tr>
                  <td colSpan="7">Aucun utilisateur.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Layout>
  );
}
