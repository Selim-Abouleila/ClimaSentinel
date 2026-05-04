# Guide Streamlit → BigQuery (Couche Mart)

**ClimaSentinel — Guide Technique Dashboard Python**  
Ce guide détaille les étapes à suivre pour connecter un dashboard Streamlit aux tables `mart` de BigQuery. Il est conçu pour être partagé avec un LLM qui vous guidera étape par étape.

> 💡 **Comment utiliser ce guide ?**  
> Partagez ce document complet à un LLM (ChatGPT, Gemini, Claude…) et dites-lui :  
> *"Je suis DA sur le projet ClimaSentinel. Aide-moi à suivre ce guide étape par étape pour créer un dashboard Streamlit connecté à BigQuery."*  
> En cas d'erreur, copiez le **message d'erreur complet** depuis votre terminal et soumettez-le au LLM — il saura diagnostiquer le problème. Ne partagez jamais le contenu de votre clé privée JSON avec le LLM.

---

## Contexte du Projet

- **Repo GitHub :** https://github.com/Selim-Abouleila/ClimaSentinel
- **Cloud :** Google Cloud Platform, projet `clima-sentinel`
- **Base de données :** BigQuery, dataset `mart`
- **Compte de service BigQuery :** `powerbi-sa@clima-sentinel.iam.gserviceaccount.com`
- **Rôles IAM accordés :** `BigQuery Data Viewer`, `BigQuery Job User`, `BigQuery Read Session User`
- **Fichier de clé :** JSON fourni par le DE1 (Selim Abouleila)

---

## Tables Disponibles dans BigQuery (`mart`)

| Table | Colonnes clés | Description |
|---|---|---|
| `mart_city_score_current` | `city_id`, `current_tipping_score`, `current_primary_driver`, `rank` | Score actuel et classement des 10 villes sur les 48 prochaines heures |
| `mart_city_score_history` | `city_id`, `date`, `global_tipping_score`, `heat_score`, `wind_score`, `rain_score`, `air_score`, `river_score`, `primary_driver` | Historique des scores sur 7 jours avec décomposition par facteur |
| `mart_city_zone_current` | `zone_name`, `city_count`, `cities_in_zone`, `drivers_in_zone` | Résumé des villes regroupées par zone opérationnelle (Stable / Monitoring / Tipping / Critical) |

---

## Étapes à Réaliser

### Étape 1 — Cloner le repo et créer le dossier dashboard

1. Cloner le repo GitHub ClimaSentinel sur sa machine
2. Se placer à la racine du repo
3. Créer un sous-dossier `dashboard/` à l'intérieur du repo pour y mettre tout le code Streamlit
4. Se placer dans ce nouveau dossier `dashboard/`

> Le dossier `dashboard/` maintient le code Streamlit séparé des autres composants du projet (ingestion Python, dbt, Terraform).

---

### Étape 2 — Mettre en place l'environnement Python

1. Créer un environnement virtuel Python dans le dossier `dashboard/`
2. L'activer (la commande diffère entre Windows et Mac/Linux)
3. Installer les bibliothèques nécessaires : `streamlit`, `google-cloud-bigquery`, `pandas`, `plotly`, `db-dtypes`
4. Générer un fichier `requirements.txt` à partir des packages installés

> ⚠️ `db-dtypes` est obligatoire — sans lui, BigQuery ne peut pas convertir les colonnes `DATE` en DataFrame Pandas et une erreur sera levée.

---

### Étape 3 — Configurer l'authentification BigQuery

1. Créer un dossier `.streamlit/` à l'intérieur du dossier `dashboard/`
2. Créer un fichier `secrets.toml` dans ce dossier `.streamlit/`
3. Y recopier les informations du fichier JSON fourni par le DE1 au format TOML (le LLM peut vous montrer exactement comment structurer ce fichier)
4. Vérifier que `.streamlit/secrets.toml` est bien dans le `.gitignore` du repo — **ne jamais committer ce fichier**

> Le fichier JSON de clé provient du compte de service `powerbi-sa`. Il a été partagé par le DE1 (Selim) **sur Snapchat via un lien Google Drive**. Téléchargez-le depuis ce lien et gardez-le en local sur votre machine — c'est le même fichier que pour Power BI.

---

### Étape 4 — Créer le fichier `app.py`

Créer un fichier `app.py` dans le dossier `dashboard/` qui réalise les opérations suivantes :

1. **Connexion à BigQuery** via les credentials du fichier `secrets.toml`
2. **Chargement des 3 tables mart** depuis BigQuery avec mise en cache (pour ne pas re-requêter à chaque interaction utilisateur)
3. **Interface principale** avec :
   - Un titre et sous-titre descriptifs
   - Un bouton pour forcer le rechargement des données
4. **Section 1 — Vue Globale :** Afficher les 4 zones opérationnelles (`mart_city_zone_current`) avec le nombre de villes par zone
5. **Section 2 — Classement :** Un tableau et un graphique en barres montrant les 10 villes triées par score décroissant (`mart_city_score_current`)
6. **Section 3 — Historique :** Un graphique en courbes montrant l'évolution du score sur 7 jours avec un sélecteur de villes (`mart_city_score_history`)
7. **Section 4 — Décomposition :** Un graphique montrant la contribution de chaque facteur (Heat, Wind, Rain, Air, River) pour une ville sélectionnée

---

### Étape 5 — Lancer le Dashboard en Local

1. S'assurer que l'environnement virtuel est activé
2. Se placer dans le dossier `dashboard/`
3. Lancer la commande Streamlit pour démarrer le serveur local
4. Ouvrir le navigateur sur l'URL indiquée (généralement `http://localhost:8501`)

---

### Étape 6 (Optionnel) — Déployer sur Streamlit Community Cloud

1. Pousser le dossier `dashboard/` sur GitHub (sans le fichier `secrets.toml`)
2. Se connecter sur [share.streamlit.io](https://share.streamlit.io) avec son compte GitHub
3. Créer une nouvelle application en sélectionnant le repo `ClimaSentinel` et le fichier `dashboard/app.py`
4. Dans les paramètres de déploiement, coller le contenu du fichier `secrets.toml` dans la section **Secrets**
5. Déployer — le dashboard sera accessible via une URL publique en quelques minutes

> Le plan gratuit de Streamlit Community Cloud ne nécessite pas de carte bancaire et supporte les repos privés.

---

## Architecture de la Connexion

```
BigQuery (projet: clima-sentinel, dataset: mart)
      ↓  authentification via JSON du compte powerbi-sa
google-cloud-bigquery (bibliothèque Python)
      ↓
app.py (Streamlit)
      ↓
http://localhost:8501 (local) ou https://votre-app.streamlit.app (déployé)
```

---

## Erreurs Courantes et Solutions

| Erreur | Cause | Solution |
|---|---|---|
| `DefaultCredentialsError` | Le fichier `secrets.toml` est absent ou mal formaté | Vérifier que `.streamlit/secrets.toml` existe et contient la section `[gcp_service_account]` |
| `Forbidden 403` | Permission BigQuery manquante | Contacter le DE1 pour vérifier les rôles IAM du compte `powerbi-sa` |
| `ModuleNotFoundError: db_dtypes` | Package oublié à l'installation | Exécuter `pip install db-dtypes` |
| Tables `mart` vides | Le pipeline dbt n'a pas encore tourné | Vérifier dans la console BigQuery que le dataset `mart` contient des données |
| Données figées | Le cache Streamlit est actif | Cliquer sur le bouton "Actualiser" dans l'interface ou redémarrer l'application |
