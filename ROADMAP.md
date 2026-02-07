# 💚 YuruHealth Development Roadmap

## 🏆 Project Concept
**"Input Minimal, Data Maximal" (入力は最小限、データは最大限)**
- **Mobile First:** Galaxy Fold (Main Screen) での日常使いに最適化。
- **Data Lake Strategy:** 将来のAI分析を見据え、あらゆるログ（生体、環境、活動）を "Raw JSON" で収集・保存する。
- **Abstracted:** デバイス変更に強いデータベース設計。

## 📊 Current Status
- **Version:** v3.0 (Phase 1 Complete)
- **Environment:** Local (WSL2) + Tailscale
- **Database:** SQLite (Migratable to Cloud)

---

## 📅 Implementation Phases

### ✅ Phase 1: Environment & Basics (Completed)
- [x] **Mobile UI Overhaul:** `st.metric` for key stats, clean layout for Galaxy Fold.
- [x] **AI Comments:** Daily health evaluation by Gemini (Witty/Logical modes).
- [x] **Weather Logging:** Automated OpenWeatherMap integration (Hybrid: GPS + Config).
- [x] **Database Expansion:** Added `environmental_logs` table with raw JSON support.

### 🚧 Phase 2: Digital & Creative Activity (Next)
- [ ] **Music Log (YouTube Music):**
    - [ ] Last.fm API integration for scrobbling history (via Pano Scrobbler).
    - [ ] `creative_logs` table creation.
    - [ ] Correlation analysis (Music vs Sleep Score).
- [ ] **Work Log:**
    - [ ] GitHub contributions visualization.
    - [ ] PC usage time tracking (via simple script).

### 📅 Phase 3: Historical Data Import (Time Machine)
- [ ] **Google Takeout Import:**
    - [ ] Script to parse Location History (JSON).
    - [ ] Merge past weather data based on location/time.
- [ ] **Legacy Health Data:** Import from Apple Health/CSV.

### 💊 Phase 4: Intake & Micro-Interactions
- [ ] **One-Tap Logger UI:**
    - [ ] Buttons for [💊 Supple], [☕ Coffee], [🍺 Alcohol].
    - [ ] `intake_logs` table creation.
- [ ] **Correlations:** A/B testing for supplements.

### ☁️ Phase 5: Cloud Migration (Future)
- [ ] **Database:** Migrate SQLite to PostgreSQL/BigQuery.
- [ ] **Hosting:** Deploy to Streamlit Cloud or Cloud Run.

---

## 📂 Tech Stack & Rules
- **Language:** Python 3.11+
- **Framework:** Streamlit (Mobile Optimized)
- **AI:** Gemini 1.5/2.0 (via Google GenAI SDK)
- **Version Control:** Git
