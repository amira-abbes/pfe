# Fixes appliquées

## 1. Renommage du nœud `ai_analysis` → `business_analysis`

L'analyse client produite par l'agent est déterministe (règles métier), pas de l'IA générative. Le nom `ai_analysis` était trompeur.

**Fichiers modifiés :**
- `backend/app/agents/nodes.py` — fonction renommée `ai_analysis_node` → `business_analysis_node`, clé de retour mise à jour
- `backend/app/agents/graph.py` — nœud LangGraph renommé, import mis à jour
- `backend/app/agents/state.py` — champ `AgentState` renommé
- `backend/app/schemas/bad_debts.py` — champ Pydantic renommé
- `backend/app/services/bad_debts_agent_service.py` — toutes les références mises à jour (payload, retours, validation)
- `backend/app/services/bad_debts_service.py` — requête SQL et dict mis à jour
- `backend/app/api/routes/bad_debts.py` — réponse API mise à jour
- `frontend/src/pages/DashboardBadDebtsPage.jsx` — lecture côté frontend mise à jour

---

## 2. Suppression de l'IA dans la génération des messages opérationnels

Les messages et décisions métier (SMS, appels) doivent être 100% déterministes. L'appel à Ollama/LLM dans `message_generation_node` a été retiré.

**Fichier modifié :** `backend/app/agents/nodes.py`

- `message_generation_node` n'appelle plus `_generate_local_contact_message` (qui appelait Ollama pour les SMS anomalie)
- Le message est toujours généré par le template déterministe `generate_message()`
- `generated_by` forcé à `"deterministic_template"` en permanence
- L'IA (Qwen/Ollama) reste utilisée uniquement pour les rapports décisionnels globaux (`bad_debts_llm_report_service.py`)

---

## 3. Logo plus grand sur les pages login / mot de passe oublié / MFA

**Fichier modifié :** `frontend/src/styles/global.css`

| Breakpoint | Avant | Après |
|---|---|---|
| Desktop (défaut) | 80px | 120px |
| Tablette | 76px | 100px |
| Mobile | 64px | 90px |
| Très petit écran | 52px | 72px |
