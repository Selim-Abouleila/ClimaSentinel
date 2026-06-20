# 9. Frontend Architecture

**🌍 Live Dashboard:** [climasentinel.up.railway.app](https://climasentinel.up.railway.app/)

The ClimaSentinel frontend is a modern web application designed to visualize the tipping risk scores of regions around the world in a premium, responsive climate-tech SaaS dashboard.

## Technology Stack
- **Framework**: Next.js 15 (App Router)
- **Styling**: Tailwind CSS v4 with custom CSS variable design tokens
- **Language**: TypeScript
- **Deployment**: Native Node.js deployment on Railway using Nixpacks

## Premium Design System (Top 1% SaaS UI)
To ensure a high-end, futuristic user experience, the dashboard utilizes a rigorous **Deep Space Glassmorphism** design language:
- **Canvas**: Built on a deep navy base (`#030712`) layered with cyan and violet ambient radial glows.
- **Glass Panels**: Cards and panels use highly polished, semi-transparent backgrounds with deep background blurs (`backdrop-blur-16px`) and subtle bright border glows.
- **Branding**: Implements pure CSS text-gradient branding without relying on flat image assets, keeping the UI ultra-clean.
- **Dynamic Severity**: Risk scores are dynamically color-coded via CSS classes (`score-high` for red, `score-medium` for yellow, `score-low` for green) and enhanced with custom text-shadow glowing effects.

## Data Integration
The frontend is completely decoupled from the database. It relies on a server-side API service (`src/lib/api.ts`) to fetch data from the FastAPI Backend.

It uses the `NEXT_PUBLIC_API_URL` environment variable to locate the backend. The frontend expects strictly sanitized data (0-100 scores) and does not ingest raw signal inputs.

### Dashboard (`/`)
- **Hero Section & Stats**: Features a dynamic hero header with an animated "Live" pulse indicator, followed by a 3-panel Summary Row that auto-calculates total active regions, global average risk, and the highest-risk region.
- **Dynamic Grid Rendering**: The Next.js page maps over the JSON response from the backend to generate a modern grid of interactive city cards.
- **Primary Risk Drivers**: Each card prominently displays the specific climate threat driving the score inside a refined glowing pill.
- **Graceful Fallbacks**: If the backend is unreachable or still starting up, the frontend gracefully displays a "System Initialization" glass panel instead of crashing.

### City Analytics Panel (`/city/[city_id]`)
A dynamic route page rendered server-side by Next.js. It calls `GET /data/city/{city_id}/scores` on the backend and displays:
- **Two-Column Analytics Header**: A premium layout showing the Global Tipping Score prominently alongside the region name and primary driver.
- **Refined Factor Breakdown**: Five individual sub-scores (Heat, Wind, Rain, Air Quality, River/Flood), each rendered as an ultra-thin, animated progress bar track with a glowing indicator head. Employs clean monospaced layouts rather than basic emojis.
- **Interactive Back Link**: A modern, pill-shaped back button with sliding SVG animations returning the user to the main dashboard.

Returns a Next.js `notFound()` (404 page) if the `city_id` is not present in `mart_city_score_detail`.
