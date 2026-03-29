# BounceRadar — Stock Agent Application

BounceRadar is a full-stack, institutional-grade bounce detection and stock analysis web application built for retail traders. It leverages quantitative data, NLP processing (with LLMs), and computer vision to deliver actionable trading insights.

## Features

- **Live Market Data (`yfinance`):** Retrieves real-time and historical OHLCV data.
- **Pattern Detection:** Uses computer vision and mathematical cross-validation to recognize chart patterns like Double Bottoms, Bullish Flags, Head and Shoulders, etc.
- **Bounce Analysis Tracker:** Evaluates potential support bounce candidates utilizing RSI, MACD, Volume Spikes, and Support Proximity.
- **Qualitative Edge:** NLP pipeline that processes earnings call transcripts and announcements to extract signals like management shakeups or guidance changes.
- **Dashboards & Watchlists:** Keeps track of your favorite setups with specialized UI components mapped to the Indian (and US) markets.

## Technology Stack

### Backend
- **Python / FastAPI:** High-performance async API gateway.
- **Postgres:** Data Lake persistence for price history and technical layers.
- **MinIO:** S3-compatible object storage for storing raw transcripts, PDFs, and generated chart PNGs.
- **Redis & BackgroundTasks:** Distributed state tracking and asynchronous task queue management.
- **yfinance & TA-Lib:** Financial market data ingestion and technical analysis algorithms.
- **Gemini Pro & Flash:** Provides reasoning on NLP transcripts and visual pattern extraction.

### Frontend
- **React 18 & Vite:** Lightning-fast component rendering.
- **Tailwind CSS & Framer Motion:** Responsive, premium UI styling with high-fidelity, subtle animations.
- **Recharts:** Clean and interactive candlestick plotting.

---

## Setup & Installation

You have two main paths to run this application: **With Docker** (Recommended for full capabilities) or **Locally** (Lightweight API mode).

### Option 1: Full Architecture via Docker (Recommended)
This spins up the entire backend stack including Postgres, MinIO, and Redis.

1. **Start Docker Infrastructure**
   ```bash
   # Make sure Docker Desktop / Docker daemon is running
   docker-compose up -d
   ```
2. **Setup Environment Variables**
   Rename `backend/.env.sample` to `backend/.env`.
   Add your Gemini API key to enable the NLP and Vision features:
   ```env
   GEMINI_API_KEY="your-google-gemini-key"
   ```
3. **Run the App**  
   The `docker-compose.yml` file handles booting up both the backend API (port 8000) and the frontend Vite server (port 5173). Simply visit [http://localhost:5173](http://localhost:5173).

### Option 2: Lightweight Local Mode (No Docker)
If you don't have Docker installed, the backend will gracefully degrade. It will bypass the Postgres Data Lake and MinIO features by falling back to fetching live data directly from `yfinance`. 

1. **Start the Backend**
   ```bash
   cd backend
   pip install -r requirements.txt
   uvicorn main:app --port 8000 --reload
   ```
2. **Start the Frontend**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Navigate to [http://localhost:5173](http://localhost:5173) in your browser.

---

## Service Architecture

- **Role 1 (Data Lake):** Manages Postgres normalization, timestamp conversions (UTC/IST), and MinIO document storage. Employs a zero-network local query constraint when working through the backend pipeline.
- **Role 2 (NLP Radar):** Extracts text from MinIO filings. Cleans boilerplate structures and funnels content to Gemini 1.5 Pro to detect qualitative metrics (e.g., Promoter buying). Never executes quantitative math.
- **Role 3 (Chart Intelligence):** Generates clean charts, feeds to Gemini 1.5 Flash for visual pattern identification, and structurally verifies findings using TA-Lib (The "Double-Lock" rule).
- **Role 4 (Orchestrator):** Validates inputs, manages the `redis` state queue lifecycle for analyses, and merges the data from Roles 1, 2, and 3 into the final API payload mapping.
