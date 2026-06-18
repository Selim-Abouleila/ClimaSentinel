# 9. Frontend Architecture

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

### Dashboard Features
- **Dynamic Rendering**: The Next.js page maps over the JSON response from the backend to generate individual city cards.
- **Primary Risk Drivers**: Each card prominently displays the specific climate threat driving the score (e.g., Heat, River/Flood).
- **Graceful Fallbacks**: If the backend is unreachable or still starting up, the frontend gracefully displays a "Waiting for data..." panel instead of crashing.
