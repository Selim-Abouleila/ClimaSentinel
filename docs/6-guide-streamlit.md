# Guide Streamlit → BigQuery (Couche Mart)

**ClimaSentinel — Guide Technique Dashboard Python**  
Ce guide explique comment créer un dashboard Streamlit qui lit les tables `mart` de BigQuery en utilisant le même compte de service que Power BI.

---

## Prérequis

- **Python 3.10+** installé sur votre machine
- Le fichier **JSON de clé** du compte de service `powerbi-sa` (demandez-le au DE1 — c'est le même fichier que pour Power BI)
- Un terminal (PowerShell, Git Bash, ou terminal VS Code)

---

## Étape 1 — Créer le Projet et Installer les Dépendances

Créez un dossier pour votre dashboard et installez les bibliothèques nécessaires :

```bash
mkdir clima-dashboard
cd clima-dashboard
python -m venv .venv
```

Activez l'environnement virtuel :

```bash
# Sur Windows
.venv\Scripts\activate

# Sur Mac / Linux
source .venv/bin/activate
```

Installez les dépendances :

```bash
pip install streamlit google-cloud-bigquery pandas plotly db-dtypes
```

Créez un fichier `requirements.txt` :

```bash
pip freeze > requirements.txt
```

---

## Étape 2 — Configurer la Clé d'Authentification

### En local (développement)

Créez le dossier de secrets Streamlit :

```bash
mkdir .streamlit
```

Créez le fichier `.streamlit/secrets.toml` et copiez-collez le **contenu** du fichier JSON fourni par le DE1 dans ce format :

```toml
[gcp_service_account]
type = "service_account"
project_id = "clima-sentinel"
private_key_id = "VOTRE_PRIVATE_KEY_ID"
private_key = "-----BEGIN RSA PRIVATE KEY-----\nVOTRE_CLE_PRIVEE\n-----END RSA PRIVATE KEY-----\n"
client_email = "powerbi-sa@clima-sentinel.iam.gserviceaccount.com"
client_id = "VOTRE_CLIENT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
```

> ⚠️ **Ne committez jamais ce fichier sur GitHub.** Vérifiez que `.streamlit/secrets.toml` est bien dans votre `.gitignore`.

Ajoutez cette ligne dans votre `.gitignore` :

```
.streamlit/secrets.toml
```

---

## Étape 3 — Créer le Fichier Principal `app.py`

Créez un fichier `app.py` avec le contenu suivant. **Ce code est prêt à l'emploi** avec les noms exacts de tables et de colonnes de ClimaSentinel :

```python
import streamlit as st
import pandas as pd
import plotly.express as px
from google.cloud import bigquery
from google.oauth2 import service_account

# ─── Configuration de la page ────────────────────────────────────────────────
st.set_page_config(
    page_title="ClimaSentinel Dashboard",
    page_icon="🌍",
    layout="wide"
)

# ─── Connexion à BigQuery via le compte de service ───────────────────────────
@st.cache_resource
def get_bigquery_client():
    """Crée et met en cache le client BigQuery."""
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/bigquery"]
    )
    return bigquery.Client(
        credentials=credentials,
        project="clima-sentinel"
    )

client = get_bigquery_client()

# ─── Chargement des données depuis BigQuery ───────────────────────────────────
@st.cache_data(ttl=3600)  # Cache pendant 1 heure
def load_current_scores():
    """Charge le classement actuel des villes (48h)."""
    query = """
        SELECT
            city_id,
            current_tipping_score,
            current_primary_driver,
            rank
        FROM `clima-sentinel.mart.mart_city_score_current`
        ORDER BY rank ASC
    """
    return client.query(query).to_dataframe()

@st.cache_data(ttl=3600)
def load_score_history():
    """Charge l'historique des scores sur 7 jours."""
    query = """
        SELECT
            city_id,
            date,
            global_tipping_score,
            heat_score,
            wind_score,
            rain_score,
            air_score,
            river_score,
            primary_driver
        FROM `clima-sentinel.mart.mart_city_score_history`
        ORDER BY date ASC
    """
    return client.query(query).to_dataframe()

@st.cache_data(ttl=3600)
def load_zones():
    """Charge le résumé par zone opérationnelle."""
    query = """
        SELECT
            zone_name,
            city_count,
            cities_in_zone,
            drivers_in_zone
        FROM `clima-sentinel.mart.mart_city_zone_current`
        ORDER BY zone_name ASC
    """
    return client.query(query).to_dataframe()

# ─── Interface principale ─────────────────────────────────────────────────────
st.title("🌍 ClimaSentinel — Tableau de Bord Opérationnel")
st.caption("Scores de tension opérationnelle mis à jour quotidiennement à 06h30 UTC")

# Bouton pour forcer le rechargement des données
if st.button("🔄 Actualiser les données"):
    st.cache_data.clear()
    st.rerun()

# Chargement
df_current  = load_current_scores()
df_history  = load_score_history()
df_zones    = load_zones()

st.divider()

# ─── Section 1 : Résumé par Zone ─────────────────────────────────────────────
st.subheader("🚦 État du Réseau — Vue Globale")

zone_colors = {
    "🔴 Critical":  "#ef4444",
    "🟠 Tipping":   "#f97316",
    "🟡 Monitoring":"#eab308",
    "🟢 Stable":    "#22c55e",
}

cols = st.columns(len(df_zones))
for i, row in df_zones.iterrows():
    with cols[i]:
        st.metric(
            label=row["zone_name"],
            value=f"{row['city_count']} ville(s)",
            help=f"Villes : {row['cities_in_zone']}\nFacteurs : {row['drivers_in_zone']}"
        )

st.divider()

# ─── Section 2 : Classement des Villes ───────────────────────────────────────
st.subheader("🏆 Classement des Villes par Tension")

col1, col2 = st.columns([1, 1])

with col1:
    # Tableau de classement
    st.dataframe(
        df_current[["rank", "city_id", "current_tipping_score", "current_primary_driver"]]
        .rename(columns={
            "rank":                  "Rang",
            "city_id":               "Ville",
            "current_tipping_score": "Score (0-100)",
            "current_primary_driver":"Facteur Principal"
        }),
        use_container_width=True,
        hide_index=True
    )

with col2:
    # Graphique en barres horizontales
    fig_bar = px.bar(
        df_current.sort_values("current_tipping_score", ascending=True),
        x="current_tipping_score",
        y="city_id",
        orientation="h",
        color="current_tipping_score",
        color_continuous_scale=["#22c55e", "#eab308", "#f97316", "#ef4444"],
        range_color=[0, 100],
        labels={"current_tipping_score": "Score", "city_id": "Ville"},
        title="Score de Tension par Ville"
    )
    fig_bar.update_layout(showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ─── Section 3 : Évolution Historique ────────────────────────────────────────
st.subheader("📈 Évolution du Score sur 7 Jours")

villes_disponibles = sorted(df_history["city_id"].unique())
villes_selectionnees = st.multiselect(
    "Sélectionner les villes à afficher :",
    options=villes_disponibles,
    default=villes_disponibles[:3]
)

if villes_selectionnees:
    df_filtered = df_history[df_history["city_id"].isin(villes_selectionnees)]
    fig_line = px.line(
        df_filtered,
        x="date",
        y="global_tipping_score",
        color="city_id",
        labels={"global_tipping_score": "Score Global", "date": "Date", "city_id": "Ville"},
        title="Évolution du Score de Basculement"
    )
    fig_line.update_yaxes(range=[0, 100])
    # Lignes de référence des zones
    fig_line.add_hline(y=31, line_dash="dot", line_color="#eab308", annotation_text="Monitoring")
    fig_line.add_hline(y=61, line_dash="dot", line_color="#f97316", annotation_text="Tipping")
    fig_line.add_hline(y=81, line_dash="dot", line_color="#ef4444", annotation_text="Critical")
    st.plotly_chart(fig_line, use_container_width=True)

st.divider()

# ─── Section 4 : Décomposition d'une Ville ───────────────────────────────────
st.subheader("🔍 Décomposition par Facteur")

ville_detail = st.selectbox("Choisir une ville :", options=villes_disponibles)

df_ville = df_history[df_history["city_id"] == ville_detail]

fig_area = px.area(
    df_ville,
    x="date",
    y=["heat_score", "wind_score", "rain_score", "air_score", "river_score"],
    labels={"value": "Score", "date": "Date", "variable": "Facteur"},
    title=f"Décomposition des Facteurs — {ville_detail}",
    color_discrete_map={
        "heat_score":  "#ef4444",
        "wind_score":  "#3b82f6",
        "rain_score":  "#06b6d4",
        "air_score":   "#8b5cf6",
        "river_score": "#0ea5e9",
    }
)
st.plotly_chart(fig_area, use_container_width=True)
```

---

## Étape 4 — Lancer le Dashboard en Local

```bash
streamlit run app.py
```

Le dashboard s'ouvre automatiquement sur [http://localhost:8501](http://localhost:8501).

---

## Étape 5 — Déployer sur Streamlit Community Cloud (Gratuit)

Pour partager le dashboard avec l'équipe sans serveur :

1. Poussez votre code sur un **repo GitHub public ou privé** (sans le fichier `secrets.toml`)
2. Allez sur [share.streamlit.io](https://share.streamlit.io) et connectez votre compte GitHub
3. Cliquez sur **New app** → sélectionnez votre repo et le fichier `app.py`
4. Dans les **paramètres de déploiement**, section **Secrets**, copiez-collez le contenu de votre `secrets.toml`
5. Cliquez sur **Deploy** — votre dashboard est en ligne en quelques minutes

> 💡 Le plan gratuit de Streamlit Community Cloud prend en charge les repos privés et ne nécessite aucune carte bancaire.

---

## Résumé de l'Architecture

```
BigQuery mart.*
      ↓
google-cloud-bigquery (Python)
      ↓  (authentification via JSON du powerbi-sa)
app.py (Streamlit)
      ↓
http://localhost:8501  (local)
       ou
https://votre-app.streamlit.app  (déployé)
```

---

## En Cas de Problème

| Problème | Solution |
|---|---|
| `google.auth.exceptions.DefaultCredentialsError` | Vérifiez que `.streamlit/secrets.toml` existe et que la section `[gcp_service_account]` est correctement remplie |
| `Forbidden 403` sur BigQuery | Le compte de service n'a pas les droits. Contacter le DE1 pour vérifier les rôles IAM |
| `ModuleNotFoundError: db_dtypes` | Exécuter `pip install db-dtypes` — requis pour lire les types DATE de BigQuery dans Pandas |
| Les tables `mart` sont vides | Le pipeline `make deploy` n'a peut-être pas encore tourné. Vérifier dans la console BigQuery |
| Données qui ne se rafraîchissent pas | Cliquer sur le bouton **🔄 Actualiser les données** dans l'interface, ou attendre l'expiration du cache (1 heure) |
