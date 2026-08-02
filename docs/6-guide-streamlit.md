# Guide Streamlit → BigQuery (Couche Mart)

**ClimaSentinel — Guide Technique Dashboard Python**  
Ce guide détaille les étapes à suivre pour connecter un dashboard Streamlit aux
tables `mart` de BigQuery. Les commandes et les messages d'erreur peuvent être
partagés pour obtenir de l'aide, mais jamais des jetons, clés, fichiers de
credentials, variables secrètes ou captures contenant ces valeurs.

> **Statut : guide de conception uniquement.** Le dépôt ne contient actuellement
> ni dossier `dashboard/`, ni application Streamlit, ni test ou déploiement
> Streamlit. Les étapes ci-dessous décrivent un composant à créer ; elles ne
> documentent pas un service ClimaSentinel déjà exploité.

> **Périmètre bêta — mart opérationnel historique.** Les tables
> `mart_city_score_*` sont dérivées de prévisions. Elles ne représentent ni des
> impacts observés, ni des probabilités, ni un modèle prédictif validé. Certains
> défauts de source peuvent être masqués par zéro ou par une valeur antérieure
> dans ces marts hérités. Les zones Stable / Monitoring / Tipping / Critical
> restent des bandes opérationnelles, pas des déclarations « sûr/dangereux ».

L'application doit afficher de façon visible :

> **Prévision bêta.** Scores ponctuels déterministes sans intervalle de
> confiance. Heat dispose d'un backtest limité sur les données
> d'archive/réanalyse Open-Meteo ; Rain a montré une compétence insuffisante ;
> Wind, Air Quality et River ne sont pas validés sur des
> observations. Une donnée manquante peut être masquée dans ces marts
> opérationnels hérités.

---

## Contexte du Projet

- **Repo GitHub :** https://github.com/Selim-Abouleila/ClimaSentinel
- **Cloud :** Google Cloud Platform, projet `clima-sentinel`
- **Base de données :** BigQuery, dataset `mart`
- **Développement local :** identité individuelle via
  [Application Default Credentials (ADC)](https://docs.cloud.google.com/docs/authentication/provide-credentials-adc)
- **Application déployée (cible, non provisionnée par ce dépôt) :** identité
  technique dédiée à Streamlit, distincte de Power BI et de toute identité
  personnelle
- **IAM :** lecture limitée au dataset `mart`, plus le droit minimal requis pour
  exécuter les requêtes

> **Action de sécurité :** toute ancienne clé JSON commune ou réutilisée entre
> Power BI et Streamlit doit être révoquée et ses copies supprimées. Vérifiez les
> journaux d'utilisation avant de créer, si nécessaire, une nouvelle méthode
> d'authentification dédiée. N'envoyez jamais un secret par messagerie, email ou
> espace de partage de fichiers.

---

## Tables Disponibles dans BigQuery (`mart`)

| Table | Colonnes clés | Description |
|---|---|---|
| `mart_city_score_current` | `city_id`, `current_tipping_score`, `current_primary_driver`, `rank` | Vue de classement sur les deux dates calendaires UTC « aujourd'hui + demain » ; ni snapshot persistant, ni fenêtre glissante de 48 heures |
| `mart_city_score_history` | `city_id`, `date`, `global_tipping_score`, `heat_score`, `wind_score`, `rain_score`, `air_score`, `river_score`, `primary_driver` | Dates cibles de la prévision actuellement transformée ; la table reconstruite n'archive ni les exécutions précédentes, ni des impacts observés |
| `mart_city_zone_current` | `zone_name`, `city_count`, `cities_in_zone`, `drivers_in_zone` | Résumé des zones opérationnelles occupées ; une zone sans ville n'apparaît pas |

Après un rafraîchissement complet, ces marts opérationnels sont destinés à
contenir les 20 villes actives. L'application doit dériver son compteur, son
classement et ses sélecteurs des lignes réellement retournées, sans limite
codée en dur à 10. Une couverture inférieure à 20 doit rester visible comme
un état de données incomplet ou obsolète.

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

#### En local

1. Installez et initialisez la CLI Google Cloud.
2. Authentifiez votre identité individuelle :

   ```bash
   gcloud auth application-default login
   ```

3. Demandez uniquement l'accès en lecture au dataset `mart` et le droit minimal
   nécessaire à l'exécution des requêtes.
4. Laissez `google-cloud-bigquery` utiliser ADC. Ne créez pas de clé JSON locale
   et ne recopiez pas de credential GCP dans `.streamlit/secrets.toml`.

#### Pour une application déployée

1. Faites provisionner une identité technique dédiée à l'application
   Streamlit. Le Terraform actuel ne crée aucune identité Streamlit. Elle ne
   doit jamais réutiliser l'identité Power BI.
2. Limitez sa lecture au dataset `mart` et accordez seulement les permissions
   nécessaires à l'exécution.
3. Privilégiez une fédération d'identité ou une autre authentification sans clé
   prise en charge par l'hébergeur.
4. Placez toute configuration sensible exceptionnellement requise uniquement
   dans le
   [gestionnaire de secrets de la plateforme](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management),
   jamais dans Git, un fichier partagé ou un canal de messagerie.
5. Définissez un propriétaire, une expiration et une rotation. Si l'hébergeur ne
   permet pas cette gestion, ne déployez pas avant d'avoir choisi une plateforme
   ou une méthode conforme.

Appliquez aussi les
[bonnes pratiques Google pour les comptes de service](https://docs.cloud.google.com/iam/docs/best-practices-service-accounts)
à cette identité dédiée.

---

### Étape 4 — Créer le fichier `app.py`

Créer un fichier `app.py` dans le dossier `dashboard/` qui réalise les opérations suivantes :

1. **Connexion à BigQuery** via ADC en local ou l'identité dédiée de l'application en déploiement
2. **Chargement des 3 tables mart** depuis BigQuery avec mise en cache (pour ne pas re-requêter à chaque interaction utilisateur)
3. **Interface principale** avec :
   - Un titre et sous-titre descriptifs
   - Le cartouche bêta obligatoire indiqué au début de ce guide
   - Un bouton pour forcer le rechargement des données
4. **Section 1 — Vue Globale :** Afficher les zones présentes dans `mart_city_zone_current` ; si l'interface doit toujours montrer les 4 zones, compléter explicitement les zones absentes avec un compteur à zéro
5. **Section 2 — Classement :** Un tableau et un graphique en barres montrant toutes les lignes opérationnelles réellement disponibles dans `mart_city_score_current` (20 après un rafraîchissement complet), sans Top 10 codé en dur
6. **Section 3 — Horizon courant :** Un graphique en courbes par date cible avec un sélecteur dynamique couvrant toutes les villes présentes dans `mart_city_score_history`, sans le présenter comme un historique des runs ou des observations
7. **Section 4 — Décomposition :** Un graphique montrant la contribution de chaque règle de facteur (Heat, Wind, Rain, Air, River) au score, sans la présenter comme une causalité

---

### Étape 5 — Lancer le Dashboard en Local

1. S'assurer que l'environnement virtuel est activé
2. Se placer dans le dossier `dashboard/`
3. Lancer la commande Streamlit pour démarrer le serveur local
4. Ouvrir le navigateur sur l'URL indiquée (généralement `http://localhost:8501`)

---

### Étape 6 (Optionnel) — Déployer sur Streamlit Community Cloud

1. Pousser le dossier `dashboard/` sur GitHub, sans aucun secret ni credential
2. Se connecter sur [share.streamlit.io](https://share.streamlit.io) avec son compte GitHub
3. Créer une nouvelle application en sélectionnant le repo `ClimaSentinel` et le fichier `dashboard/app.py`
4. Configurer l'identité Streamlit dédiée dans le gestionnaire de secrets de la
   plateforme, sans réutiliser une identité Power BI ou personnelle
5. Vérifier le périmètre IAM et la procédure de rotation avant de déployer

> Les fonctions et limites de l'offre d'hébergement peuvent évoluer. Vérifiez-les
> au moment du déploiement et ne rendez pas l'application publique tant que son
> identité et ses secrets ne sont pas correctement isolés.

---

## Architecture de la Connexion

```
BigQuery (projet: clima-sentinel, dataset: mart)
      ↓  ADC individuel (local) ou identité Streamlit dédiée (déploiement)
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
| `DefaultCredentialsError` | ADC n'est pas initialisé en local, ou l'identité dédiée n'est pas configurée sur l'hébergeur | En local, relancer `gcloud auth application-default login` ; en déploiement, vérifier la configuration du gestionnaire de secrets |
| `Forbidden 403` | Permission BigQuery manquante ou périmètre IAM incorrect | Faire vérifier l'accès en lecture au dataset `mart` et le droit minimal d'exécuter des jobs |
| `ModuleNotFoundError: db_dtypes` | Package oublié à l'installation | Exécuter `pip install db-dtypes` |
| Tables `mart` vides | Sources `raw` non initialisées, ingestion absente ou transformation dbt non réussie | Vérifier séparément les sources, les journaux dbt et les lignes réellement présentes dans le dataset `mart` |
| Données figées | Le cache Streamlit est actif | Cliquer sur le bouton "Actualiser" dans l'interface ou redémarrer l'application |
