# Workflows n8n — Bad Debts

## Objectif

Ce dossier contient les workflows n8n utilisés pour automatiser les traitements métier autour du module Bad Debts de la plateforme interne Tunisie Telecom.

L’objectif principal est d’automatiser l’envoi d’un rapport quotidien des clients à risque liés au Service SOS Solde & Data.

## Workflow principal

**Bad Debts — Rapport automatique quotidien**

Ce workflow permet de générer et d’envoyer automatiquement un rapport email professionnel contenant les indicateurs Bad Debts, les clients à risque élevé et les recommandations opérationnelles.

## Chaîne d’exécution

Le workflow suit cette chaîne :

```text
Déclencheur quotidien 08h
→ Récupération des KPIs Bad Debts depuis l’API FastAPI
→ Récupération des derniers rapports agentic
→ Construction d’un résumé métier
→ Envoi d’un email HTML professionnel au responsable
Déclencheurs

Le workflow possède deux déclencheurs :

Déclencheur manuel : utilisé pour les tests et les démonstrations.
Déclencheur quotidien 08h : utilisé pour l’envoi automatique du rapport chaque jour.
Nodes du workflow
1. Déclencheur quotidien 08h

Lance automatiquement le workflow chaque jour à 08h.

2. Déclencheur manuel

Permet de tester le workflow manuellement depuis l’interface n8n.

3. Récupérer résumé Bad Debts

Appelle l’API FastAPI pour récupérer les indicateurs principaux du module Bad Debts.

URL utilisée en local depuis Docker :

http://host.docker.internal:8000/api/v1/metrics/summary
4. Récupérer rapports agentic

Appelle l’API FastAPI pour récupérer les derniers rapports générés par la couche agentic.

URL utilisée en local depuis Docker :

http://host.docker.internal:8000/api/v1/bad-debts/agent/reports?limit=5
5. Construire résumé métier

Transforme les données récupérées en un objet métier prêt à être utilisé dans l’email.

Les données préparées incluent :

la date du rapport
les KPIs principaux
le nombre de clients à risque élevé
la répartition du risque
les recommandations opérationnelles
6. Envoyer rapport email

Envoie un email HTML professionnel au responsable à l’aide d’un compte SMTP applicatif Gmail.

Technologies utilisées
n8n
Docker
FastAPI
PostgreSQL
LangGraph
SMTP Gmail applicatif
HTML email
URLs utilisées en environnement local

Backend accessible depuis n8n Docker :

http://host.docker.internal:8000

Dashboard Bad Debts local :

http://localhost:5173/dashboard/bad-debts/overview

Interface n8n locale :

http://localhost:5678
Fichier workflow exporté

Le workflow exporté doit être stocké dans :

n8n/workflows/bad_debts_daily_report.json

Ce fichier permet de versionner la structure du workflow dans GitHub.

Sécurité

Les identifiants SMTP et les mots de passe ne doivent jamais être versionnés dans Git.

Ne jamais pousser :

.env
backend/.env
stack.env
n8n_data/

Le fichier JSON exporté contient la structure du workflow, mais les credentials doivent être configurés directement dans n8n.

Lancement local de n8n

Depuis le dossier n8n :

docker compose up -d

Puis ouvrir :

http://localhost:5678
Résultat attendu

Chaque jour à 08h, le workflow envoie automatiquement un rapport email contenant :

les clients à risque élevé
les KPIs principaux Bad Debts
la répartition du risque
les recommandations opérationnelles
un bouton vers le dashboard Bad Debts
Intérêt pour le PFE

Cette intégration montre que la plateforme ne se limite pas à l’affichage des données.

Elle automatise également le pilotage métier grâce à n8n :

Données PostgreSQL
→ API FastAPI
→ Couche agentic
→ Workflow n8n
→ Rapport email automatique

Cela permet d’obtenir un système plus complet, plus professionnel et plus proche d’un usage réel en entreprise.