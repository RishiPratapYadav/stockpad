# ◈ StockPad v0.2 — Supabase Edition

Lightweight stock tracker · Streamlit + yfinance + Supabase  
**Data persists permanently across sessions.**

---

## 📁 Project Files

```
stockpad/
├── app.py                      ← Main Streamlit app
├── requirements.txt            ← Python dependencies
├── supabase_schema.sql         ← Run once in Supabase to create table
├── .gitignore                  ← Keeps secrets off GitHub
└── .streamlit/
    └── secrets.toml            ← Your Supabase keys (NOT committed to GitHub)
```

---

# 🛠️ Full Setup Guide

---

## PART 1 — Supabase Setup

### 1.1 Create a free Supabase account
1. Go to → https://supabase.com
2. Click **Start your project** → Sign up with GitHub (easiest)
3. Verify your email

### 1.2 Create a new project
1. Click **New Project**
2. Fill in:
   - **Name:** `stockpad`
   - **Database Password:** choose a strong password (save it!)
   - **Region:** pick closest to you
3. Click **Create new project**
4. Wait ~2 minutes while it provisions

### 1.3 Create the database table
1. In the left sidebar click **SQL Editor**
2. Click **New Query**
3. Open the file `supabase_schema.sql` from this project
4. Copy the entire contents and paste into the SQL editor
5. Click **Run** (▶ button)
6. You should see: *"Success. No rows returned"*
7. Verify: click **Table Editor** in the sidebar → you should see a `watchlist` table

### 1.4 Get your API keys
1. In the left sidebar click **Project Settings** (⚙ gear icon)
2. Click **API**
3. You need two values — copy them somewhere safe:
   - **Project URL** → looks like `https://abcdefghijkl.supabase.co`
   - **anon public key** → a long string starting with `eyJ...`

---

## PART 2 — GitHub Setup

### 2.1 Create a GitHub account
1. Go to → https://github.com
2. Click **Sign up** → create account → verify email

### 2.2 Create a new repository
1. Click **＋** (top right) → **New repository**
2. Fill in:
   - **Name:** `stockpad`
   - **Visibility:** ✅ Public (required for free Streamlit Cloud)
   - **Initialize with README:** ✅ checked
3. Click **Create repository**

### 2.3 Upload your files
1. In your new repo, click **Add file → Upload files**
2. Upload these files (NOT secrets.toml — that stays local):
   - `app.py`
   - `requirements.txt`
   - `supabase_schema.sql`
   - `.gitignore`
3. Also create the `.streamlit/` folder structure:
   - Click **Add file → Create new file**
   - Type `.streamlit/secrets.toml` as the filename
   - Paste this placeholder content (real keys go in Streamlit Cloud, not here!):
     ```
     SUPABASE_URL = "placeholder"
     SUPABASE_KEY = "placeholder"
     ```
4. Click **Commit changes**

---

## PART 3 — Streamlit Cloud Setup

### 3.1 Create Streamlit account
1. Go to → https://share.streamlit.io
2. Click **Sign in with GitHub** → authorize

### 3.2 Deploy the app
1. Click **New app**
2. Fill in:
   - **Repository:** `your-username/stockpad`
   - **Branch:** `main`
   - **Main file path:** `app.py`
3. Click **Advanced settings** ← important!
4. In the **Secrets** box paste:
   ```toml
   SUPABASE_URL = "https://YOUR_PROJECT_ID.supabase.co"
   SUPABASE_KEY = "your-anon-public-key-here"
   ```
   Replace with your real values from Step 1.4
5. Click **Save** then **Deploy!**
6. Wait ~2 minutes → your app is live! 🎉

### 3.3 Your app URL
```
https://your-username-stockpad-app-xxxxx.streamlit.app
```
Bookmark this. Share it. It's always on.

---

## PART 4 — Updating the App Later

Every time you edit `app.py` and push to GitHub,  
Streamlit Cloud **auto-redeploys** within seconds.

```bash
# If using Git on your computer:
git add app.py
git commit -m "feat: added new column"
git push origin main
```

Or just edit the file directly on GitHub and commit — Streamlit picks it up automatically.

---

## ✨ Features

| Feature                         | Status |
|---------------------------------|--------|
| Add stock by ticker             | ✅     |
| Live price via yfinance         | ✅     |
| % Change · P/E · 52W · Mkt Cap  | ✅     |
| Buy Target / Sell Target        | ✅ editable + saved |
| Price Tag / Tag %               | ✅ editable + saved |
| Sentiment dropdown              | ✅ editable + saved |
| Comments                        | ✅ editable + saved |
| Persistent storage (Supabase)   | ✅     |
| Refresh All prices              | ✅     |
| Export to CSV                   | ✅     |
| Auto-redeploy on GitHub push    | ✅     |

---

## 🔐 Security Note

- Your `secrets.toml` is in `.gitignore` — it will **never** be pushed to GitHub
- Supabase keys are stored securely in Streamlit Cloud's secrets manager
- The anon key is safe to use — it only has access to your watchlist table
