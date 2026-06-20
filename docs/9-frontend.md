# 9. Frontend Architecture

**🌍 Live Dashboard:** [climasentinel.up.railway.app](https://climasentinel.up.railway.app/)

The ClimaSentinel frontend is a modern web application designed to visualize the tipping risk scores of cities around the world in a stunning and responsive dashboard.

## Technology Stack
- **Framework**: Next.js (React)
- **Styling**: Tailwind CSS with custom Glassmorphism tokens
- **Language**: TypeScript
- **Deployment**: Native Node.js deployment on Railway

## Design System
To ensure a premium user experience, the dashboard utilizes a **Glassmorphism** design language. 
- The UI is built on a dark mode canvas (`#0f172a`) with ambient radial gradients.
- Cards and panels use semi-transparent backgrounds with background blur (`backdrop-filter`) to create a "frosted glass" effect.
- Risk scores are dynamically color-coded (Red for High Risk, Yellow for Medium, Green for Low) directly within the React components.

## Data Integration
The frontend is completely decoupled from the database. Instead, it relies on an API service (`src/lib/api.ts`) to fetch data from the FastAPI Backend.

It uses the `NEXT_PUBLIC_API_URL` environment variable to locate the backend. In the staging environment, this points to the live Staging backend, and in production, it points to the Production backend.

### Dashboard (`/`)
- **Dynamic Rendering**: The Next.js page maps over the JSON response from the backend to generate individual city cards.
- **Primary Risk Drivers**: Each card prominently displays the specific climate threat driving the score (e.g., Heat, River/Flood).
- **Clickable Cards**: Every city card is a `<Link>` that navigates to the city detail page (`/city/{city_id}`).
- **Graceful Fallbacks**: If the backend is unreachable or still starting up, the frontend gracefully displays a "Waiting for data..." panel instead of crashing.

### City Detail Page (`/city/[city_id]`)
A dynamic route page rendered server-side by Next.js. It calls `GET /data/city/{city_id}/scores` on the backend and displays:
- **Global Tipping Score** with colour-coded severity (Red / Amber / Green).
- **Primary Driver** badge showing which factor is dominant.
- **Factor Breakdown**: five individual sub-scores (🌡️ Heat, 💨 Wind, 🌧️ Rain, 🌫️ Air Quality, 🌊 River/Flood), each rendered as a colour-coded animated progress bar (0–100).
- A **score legend** explaining the three severity bands.
- A **back link** returning to the main dashboard.

Returns a Next.js `notFound()` (404 page) if the `city_id` is not present in `mart_city_score_detail`.
