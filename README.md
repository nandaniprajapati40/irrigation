# 🌾 JalDrishti – Crop Water Requirement Monitoring System

JalDrishti is an AI-powered Crop Water Requirement (CWR) monitoring and forecasting platform developed for precision irrigation. The application provides visualization of geospatial datasets, crop water requirement analysis, irrigation recommendations, and an AI chatbot for answering agriculture-related queries.

The project consists of two separate applications:

- **Backend** – FastAPI (Python)
- **Frontend** – Vue.js (Vite)

---

# Project Structure

```
JalDrishti/
│
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── ...
│
├── frontend/
│   ├── package.json
│   ├── src/
│   ├── ...
│
└── README.md
```

---

# Requirements

## Backend

- Python 3.10+
- pip

## Frontend

- Node.js 18+
- npm

---

# Backend Setup

## 1. Navigate to backend

```bash
cd backend
```

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

## 3. Run the backend

```bash
python main.py
```

Backend will start on the configured host and port.

---

# Frontend Setup

## 1. Navigate to frontend

```bash
cd frontend
```

## 2. Install dependencies

```bash
npm install
```

## 3. Run the development server

```bash
npm run server
```

The frontend will start on the configured development port.

---

# Features

- Crop Water Requirement (CWR) Monitoring
- Irrigation Water Requirement (IWR)
- Sentinel Satellite Visualization
- Interactive Charts
- GIS-based Map Visualization
- Date-wise Data Exploration
- AI Chatbot
- Historical and Forecast Analysis

---

# Technology Stack

## Frontend

- Vue.js
- Vite
- Leaflet
- JavaScript
- HTML/CSS

## Backend

- FastAPI
- Python
- Rasterio
- Pandas
- NumPy
- GeoPandas
- MongoDB
- DuckDB

---

# Running the Project

Open two terminals.

### Terminal 1

```bash
cd backend
python main.py
```

### Terminal 2

```bash
cd frontend
npm run server
```

After both services are running, open the frontend URL shown in the terminal.

---

# Notes

- Ensure all required Python packages are installed before running the backend.
- Ensure Node.js dependencies are installed before starting the frontend.
- Backend must be running before using the frontend.
- Verify that backend API URLs are correctly configured in the frontend configuration.

---

# Authors

**JalDrishti Development Team**

AI-Based Crop Water Requirement Monitoring and Irrigation Decision Support System.

---