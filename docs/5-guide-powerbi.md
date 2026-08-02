# Guide de Connexion Power BI → BigQuery (Couche Mart)

**ClimaSentinel — Guide Technique DA1 / DA2**  
Ce guide est destiné aux membres de l'équipe chargés du dashboard. Il détaille pas à pas comment connecter Power BI Desktop aux tables finales de BigQuery.

> **Périmètre bêta — mart opérationnel historique.** Les tables
> `mart_city_score_*` contiennent des scores dérivés de prévisions et des bandes
> opérationnelles ; elles ne constituent ni un historique d'impacts observés, ni
> des probabilités, ni un modèle prédictif validé. Dans ces marts hérités,
> certains défauts de source peuvent être masqués par un zéro ou une valeur
> antérieure. Les libellés Stable / Monitoring / Tipping / Critical ne doivent
> donc jamais être reformulés comme « sûr », « danger certain » ou consigne
> d'action.

Tout dashboard publié doit afficher clairement :

> **Prévision bêta.** Scores ponctuels déterministes sans intervalle de
> confiance. Heat dispose d'un backtest limité sur les données
> d'archive/réanalyse Open-Meteo ; Rain a montré une compétence insuffisante ;
> Wind, Air Quality et River ne sont pas validés sur des
> observations. Une donnée manquante peut être masquée dans ces marts
> opérationnels hérités.

---

## Prérequis

Avant de commencer, assurez-vous d'avoir :
- **Power BI Desktop** installé sur votre machine ([télécharger ici](https://powerbi.microsoft.com/fr-fr/desktop/))
- Un **compte individuel nominatif** autorisé à lire uniquement le dataset BigQuery `mart`
- Le droit d'exécuter des jobs BigQuery, accordé seulement si le connecteur en a besoin
- La validation du propriétaire GCP avant toute publication dans Power BI Service

Consultez également la
[documentation officielle du connecteur Google BigQuery](https://learn.microsoft.com/en-us/power-query/connectors/google-bigquery)
pour les modes d'authentification actuellement pris en charge.

> **Écart IaC actuel :** `infra/terraform/main.tf` crée encore le compte
> `powerbi-sa` et lui attribue au niveau **projet** les rôles
> `roles/bigquery.dataViewer`, `roles/bigquery.jobUser` et
> `roles/bigquery.readSessionUser`. Cette configuration héritée n'implémente pas
> l'objectif de moindre privilège décrit ci-dessous : en particulier,
> `dataViewer` n'est pas limité au dataset `mart`. Ne considérez pas le simple
> `terraform apply` comme une validation de sécurité et n'utilisez pas cette
> identité avant que son périmètre IAM ait été revu et réduit.

---

## Étape 1 — Faire Valider l'Accès

Demandez au propriétaire GCP de configurer l'accès selon les règles suivantes :

1. Utiliser l'identité individuelle de chaque analyste pour Power BI Desktop.
2. Limiter `BigQuery Data Viewer` au dataset `mart`, pas à l'ensemble du projet.
3. Accorder `BigQuery Job User` au niveau minimal requis pour exécuter les requêtes.
4. Si le Navigateur ou la BigQuery Storage API l'exige, ajouter uniquement les
   permissions minimales de visibilité du projet et de session de lecture,
   sans élargir l'accès aux données au-delà de `mart`.
5. Pour Power BI Service, utiliser une identité **dédiée à cette application** si une
   identité technique est nécessaire. Elle ne doit être partagée ni avec Streamlit,
   ni avec un autre service, ni entre utilisateurs.
6. Privilégier une authentification sans clé. Tout secret exceptionnellement requis
   doit rester dans le gestionnaire de secrets approuvé de la plateforme, avec un
   propriétaire, une date d'expiration et une procédure de rotation.

Ces règles suivent les
[bonnes pratiques Google pour les comptes de service](https://docs.cloud.google.com/iam/docs/best-practices-service-accounts).

> **Action de sécurité :** si une clé JSON commune a déjà été créée ou distribuée,
> considérez-la comme compromise. Le propriétaire GCP doit la révoquer, vérifier son
> utilisation, supprimer les copies restantes et, uniquement si nécessaire, créer
> une nouvelle méthode d'authentification dédiée. Une clé ne doit jamais être envoyée
> par messagerie, email ou espace de partage de fichiers.

---

## Étape 2 — Ouvrir Power BI Desktop et Connecter BigQuery

1. Ouvrez **Power BI Desktop**
2. Cliquez sur **Obtenir des données** (en haut à gauche)
3. Dans la barre de recherche, tapez **`BigQuery`**
4. Sélectionnez **Google BigQuery** → cliquez sur **Connecter**

---

## Étape 3 — S'authentifier avec une Identité Nominative

Dans la fenêtre qui s'ouvre :

1. Sélectionnez **Compte organisationnel / OAuth Google** lorsque le connecteur le propose.
2. Connectez-vous avec votre compte individuel autorisé.
3. Vérifiez que l'écran de consentement affiche bien votre identité et le projet attendu.
4. Cliquez sur **Connecter**.

Power BI se connecte avec une identité traçable. L'accès aux données doit rester
limité au dataset `mart`.

---

## Étape 4 — Sélectionner les Tables du Mart

Dans le **Navigateur** qui s'affiche :

1. Développez le projet **`clima-sentinel`**
2. Développez le dataset **`mart`**
3. Cochez les **3 tables suivantes** :

| Table | Utilité dans le Dashboard |
|---|---|
| ✅ `mart_city_score_history` | Courbe par date cible de la prévision actuellement transformée ; la table est reconstruite et n'est ni un historique des exécutions, ni un historique d'impacts observés |
| ✅ `mart_city_score_current` | Vue classant les villes sur les deux dates calendaires UTC « aujourd'hui + demain » ; ce n'est ni un snapshot persistant, ni une fenêtre glissante de 48 heures |
| ✅ `mart_city_zone_current` | Agrégat des zones actuellement occupées (Stable / Monitoring / Tipping / Critical) ; les zones vides ne produisent pas de ligne |

4. Cliquez sur **Charger**

Après une ingestion et une reconstruction dbt complètes, ces marts
opérationnels sont destinés à couvrir les **20 villes actives**. Ne conservez
aucun filtre Top 10 hérité. Pour une recette de données, vérifiez que
`COUNT(DISTINCT city_id)` vaut 20 dans `mart_city_score_current` et que la somme
des `city_count` des zones présentes vaut également 20. Une valeur inférieure
doit être traitée comme un problème de fraîcheur/couverture, pas complétée
artificiellement.

---

## Étape 5 — Choisir le Mode de Connexion

Power BI vous demandera entre **Import** et **DirectQuery** :

| Mode | Explication | Recommandation ClimaSentinel |
|---|---|---|
| **Import** | Power BI télécharge une copie des données. Rapide, mais pas en temps réel. | ✅ **Recommandé** — cadence amont visée : une fois par jour, sous réserve d'une ingestion et d'une transformation réussies |
| **DirectQuery** | Power BI interroge BigQuery à chaque clic ; cela ne rend pas la source amont temps réel. | ❌ Non nécessaire pour notre cadence quotidienne |

→ Sélectionnez **Import** et cliquez sur **OK**.

---

## Étape 6 — Construire les Visuels Clés

Voici les visuels recommandés et les colonnes à utiliser depuis les tables mart :

### 🗺️ Carte de Tension (Vue Globale)
- **Visuel :** Carte (Map)
- **Localisation :** dimension de coordonnées revue pour les 20 villes, dérivée de `config/cities.csv` ; ne supposez pas que des identifiants comme `vienna_at` seront géocodés correctement
- **Couleur des bulles :** `current_tipping_score` de `mart_city_score_current` (gradient Vert → Rouge)

### 🏆 Classement des Villes
- **Visuel :** Tableau ou Graphique en barres
- **Source :** `mart_city_score_current`
- **Colonnes :** `rank`, `city_id`, `current_tipping_score`, `current_primary_driver`
- **Trier par :** `rank` croissant
- **Couverture :** toutes les lignes opérationnelles disponibles, sans limite codée en dur à 10

### 📈 Évolution du Score (Historique)
- **Visuel :** Graphique en courbes
- **Source :** `mart_city_score_history`
- **Axe X :** `date`
- **Axe Y :** `global_tipping_score`
- **Légende :** `city_id` (pour comparer les villes)

Ce graphique compare des **dates cibles dans la prévision courante**. Il ne
permet pas d'analyser comment les prévisions d'une même date ont évolué entre
plusieurs exécutions, car ce mart n'archive pas les snapshots successifs.

### 🚦 Résumé par Zone
- **Visuel :** Graphique en anneau ou Carte de synthèse
- **Source :** `mart_city_zone_current`
- **Colonnes :** `zone_name`, `city_count`, `cities_in_zone`

### 🔍 Décomposition des Facteurs (Explicabilité)
- **Visuel :** Graphique en barres empilées
- **Source :** `mart_city_score_history`
- **Valeurs :** `heat_score`, `wind_score`, `rain_score`, `air_score`, `river_score`
- **Filtre :** Par `city_id` (pour voir la décomposition d'une ville précise)

Ajoutez à la page principale le cartouche bêta ci-dessus. Ne présentez pas cette
décomposition comme une causalité : elle montre uniquement la contribution des
règles de score au total opérationnel.

---

## Étape 7 — Publier sur Power BI Service (Rafraîchissement Automatique)

Pour que le dashboard se mette à jour automatiquement chaque matin :

1. Dans Power BI Desktop, cliquez sur **Publier** (onglet Accueil)
2. Choisissez votre espace de travail Power BI (votre organisation scolaire)
3. Dans le **portail web Power BI Service** ([app.powerbi.com](https://app.powerbi.com)) :
   - Naviguez vers votre **Jeu de données** publié
   - Cliquez sur **Paramètres → Informations d'identification de la source de données**
   - Configurez l'identité approuvée pour cette application, sans réutiliser
     l'identité Streamlit ni une clé personnelle partagée
   - Conservez tout secret requis uniquement dans le gestionnaire de secrets de la
     plateforme et documentez sa rotation
   - Activez le **Rafraîchissement planifié** → Fréquence : `Quotidien` → Heure : `06:30 UTC`

> Le rafraîchissement proposé est planifié 30 minutes après le déclenchement du
> job d'ingestion à 06:00 UTC. Ce délai ne garantit pas que le traitement
> séquentiel des 20 villes et dbt soit terminé. Le job sort désormais en échec
> lorsqu'une source ou dbt échoue, mais le rafraîchissement Power BI ne dépend
> pas automatiquement de ce statut. Vérifiez une exécution Cloud Run réussie,
> puis la fraîcheur et la présence des 20 villes avant de publier le dashboard.

---

## Résumé de l'Architecture de Connexion

```
Cloud Scheduler (06:00 UTC)
        ↓
Cloud Run (Ingestion Python, puis dbt ; échec propagé)
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
| "Accès refusé" lors de la connexion | Faire vérifier l'accès nominatif au dataset `mart` et le droit minimal d'exécuter des jobs BigQuery |
| Les tables `mart` n'apparaissent pas | Vérifier que les datasets existent et qu'un `make deploy` complet s'est terminé sans erreur ; contrôler ensuite la fraîcheur et les 20 `city_id`, car des données antérieures peuvent rester interrogeables après un run inhabituel |
| Le rafraîchissement échoue sur Power BI Service | Vérifier l'identité dédiée, son périmètre IAM et l'état de son secret dans le gestionnaire approuvé ; ne pas échanger de clé par messagerie |
| Données vides / NULL dans les graphiques | Attendu pour les colonnes `river_*` des villes dont `river_enabled=false`; Paris, Amsterdam, Varsovie, Vienne et Budapest sont les villes actuellement activées |
