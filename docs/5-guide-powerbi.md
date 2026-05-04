# Guide de Connexion Power BI → BigQuery (Couche Mart)

**ClimaSentinel — Guide Technique DA1 / DA2**  
Ce guide est destiné aux membres de l'équipe chargés du dashboard. Il détaille pas à pas comment connecter Power BI Desktop aux tables finales de BigQuery.

---

## Prérequis

Avant de commencer, assurez-vous d'avoir :
- **Power BI Desktop** installé sur votre machine ([télécharger ici](https://powerbi.microsoft.com/fr-fr/desktop/))
- Votre adresse Gmail (celle que vous avez communiquée au DE1) avec accès au projet GCP `clima-sentinel`
- Le fichier **JSON de clé** du compte de service `powerbi-sa` (à demander au DE1 — il le génère depuis la console GCP)

---

## Étape 1 — Récupérer la Clé JSON auprès du DE1

Le compte de service Power BI a été créé et géré via Terraform dans le projet. Le DE1 doit effectuer les actions suivantes **une seule fois** :

1. Aller sur [console.cloud.google.com](https://console.cloud.google.com)
2. Naviguer vers **IAM & Admin → Comptes de service**
3. Trouver le compte **`powerbi-sa@clima-sentinel.iam.gserviceaccount.com`**
4. Cliquer dessus → onglet **Clés** → **Ajouter une clé → Créer une clé (JSON)**
5. Envoyer le fichier `.json` téléchargé **de façon sécurisée** à chaque membre DA (ne pas le partager par email ni committer sur GitHub)

> ⚠️ **Ce fichier JSON est une clé d'accès. Ne le partagez jamais publiquement et ne le committez jamais sur GitHub.**

---

## Étape 2 — Ouvrir Power BI Desktop et Connecter BigQuery

1. Ouvrez **Power BI Desktop**
2. Cliquez sur **Obtenir des données** (en haut à gauche)
3. Dans la barre de recherche, tapez **`BigQuery`**
4. Sélectionnez **Google BigQuery** → cliquez sur **Connecter**

---

## Étape 3 — S'authentifier avec le Compte de Service

Dans la fenêtre qui s'ouvre :

1. Sélectionnez le mode **Compte de service (Service Account)**
2. Cliquez sur **Parcourir** et choisissez le fichier `.json` que le DE1 vous a envoyé
3. Cliquez sur **Se connecter**

Power BI va maintenant se connecter à votre projet GCP en lecture seule.

---

## Étape 4 — Sélectionner les Tables du Mart

Dans le **Navigateur** qui s'affiche :

1. Développez le projet **`clima-sentinel`**
2. Développez le dataset **`mart`**
3. Cochez les **3 tables suivantes** :

| Table | Utilité dans le Dashboard |
|---|---|
| ✅ `mart_city_score_history` | Graphiques de tendances (évolution du score sur 7 jours) |
| ✅ `mart_city_score_current` | Classement des villes par tension (vue temps réel) |
| ✅ `mart_city_zone_current` | Résumé exécutif par zone (Stable / Critique, etc.) |

4. Cliquez sur **Charger**

---

## Étape 5 — Choisir le Mode de Connexion

Power BI vous demandera entre **Import** et **DirectQuery** :

| Mode | Explication | Recommandation ClimaSentinel |
|---|---|---|
| **Import** | Power BI télécharge une copie des données. Rapide, mais pas en temps réel. | ✅ **Recommandé** — nos données se mettent à jour 1 fois par jour |
| **DirectQuery** | Power BI interroge BigQuery à chaque clic. Temps réel, mais plus lent et coûteux. | ❌ Non nécessaire pour notre cadence |

→ Sélectionnez **Import** et cliquez sur **OK**.

---

## Étape 6 — Construire les Visuels Clés

Voici les visuels recommandés et les colonnes à utiliser depuis les tables mart :

### 🗺️ Carte de Tension (Vue Globale)
- **Visuel :** Carte (Map)
- **Localisation :** Colonne `city_id` (vous devrez peut-être ajouter une table de coordonnées séparée avec lat/lon)
- **Couleur des bulles :** `current_tipping_score` de `mart_city_score_current` (gradient Vert → Rouge)

### 🏆 Classement des Villes
- **Visuel :** Tableau ou Graphique en barres
- **Source :** `mart_city_score_current`
- **Colonnes :** `rank`, `city_id`, `current_tipping_score`, `current_primary_driver`
- **Trier par :** `rank` croissant

### 📈 Évolution du Score (Historique)
- **Visuel :** Graphique en courbes
- **Source :** `mart_city_score_history`
- **Axe X :** `date`
- **Axe Y :** `global_tipping_score`
- **Légende :** `city_id` (pour comparer les villes)

### 🚦 Résumé par Zone
- **Visuel :** Graphique en anneau ou Carte de synthèse
- **Source :** `mart_city_zone_current`
- **Colonnes :** `zone_name`, `city_count`, `cities_in_zone`

### 🔍 Décomposition des Facteurs (Explicabilité)
- **Visuel :** Graphique en barres empilées
- **Source :** `mart_city_score_history`
- **Valeurs :** `heat_score`, `wind_score`, `rain_score`, `air_score`, `river_score`
- **Filtre :** Par `city_id` (pour voir la décomposition d'une ville précise)

---

## Étape 7 — Publier sur Power BI Service (Rafraîchissement Automatique)

Pour que le dashboard se mette à jour automatiquement chaque matin :

1. Dans Power BI Desktop, cliquez sur **Publier** (onglet Accueil)
2. Choisissez votre espace de travail Power BI (votre organisation scolaire)
3. Dans le **portail web Power BI Service** ([app.powerbi.com](https://app.powerbi.com)) :
   - Naviguez vers votre **Jeu de données** publié
   - Cliquez sur **Paramètres → Informations d'identification de la source de données**
   - Entrez à nouveau les informations du compte de service (JSON)
   - Activez le **Rafraîchissement planifié** → Fréquence : `Quotidien` → Heure : `06:30 UTC`

> 💡 Cela déclenche le rafraîchissement 30 minutes après l'exécution du pipeline dbt (qui se lance à 06:00 UTC), garantissant que les données sont toujours à jour.

---

## Résumé de l'Architecture de Connexion

```
Cloud Scheduler (06:00 UTC)
        ↓
Cloud Run (Ingestion Python)
        ↓
BigQuery raw.*  →  dbt (Silver)  →  stg.*
                                         ↓
                                   dbt (Gold)
                                         ↓
                               BigQuery mart.*
                                         ↓
                          Power BI (Import, 06:30 UTC)
                                         ↓
                              Dashboard Interactif
```

---

## En cas de Problème

| Problème | Solution |
|---|---|
| "Accès refusé" lors de la connexion | Contacter le DE1 pour vérifier que votre compte de service a bien les rôles `BigQuery Data Viewer` + `BigQuery Job User` |
| Les tables `mart` n'apparaissent pas | Vérifier que le pipeline `make deploy` a bien été exécuté avec succès (le dataset `mart` doit exister dans BigQuery) |
| Le rafraîchissement échoue sur Power BI Service | Re-saisir les credentials JSON dans les paramètres du jeu de données |
| Données vides / NULL dans les graphiques | Normal pour les colonnes `river_*` des villes sans rivière (Amsterdam, Paris, etc.) |
