# 🚀 Deploy AgriTrue & get a public link (≈5 minutes, free)

You'll put the code on GitHub, then point Streamlit Community Cloud at it. The result is a
public `https://<something>.streamlit.app` URL you can email to the TEEBAgriFood manager.

---

## Step 1 — Create an empty repo on GitHub
1. Go to <https://github.com/new>
2. Repository name: **agritrue** (or anything). Visibility: **Public** (required for the free tier).
3. **Do not** add a README/.gitignore (this project already has them).
4. Click **Create repository** and copy the URL it shows, e.g. `https://github.com/<you>/agritrue.git`

## Step 2 — Push this folder (run in this project directory)
The local git repo is already initialised and committed for you. Just connect and push:

```bat
git remote add origin https://github.com/<you>/agritrue.git
git branch -M main
git push -u origin main
```

> If git asks you to log in, use your GitHub username + a **Personal Access Token** as the
> password (GitHub → Settings → Developer settings → Tokens → "Generate new token (classic)" →
> tick `repo`). Or install GitHub Desktop and push from there.

## Step 3 — Deploy on Streamlit Community Cloud
1. Go to <https://share.streamlit.io> and sign in **with GitHub**.
2. Click **Create app** → **Deploy a public app from GitHub**.
3. Repository: `<you>/agritrue` · Branch: `main` · Main file path: **`app.py`**
4. (Optional) **Advanced settings → Secrets**, paste:
   ```toml
   OWNER_KEY = "something-private"
   ```
5. Click **Deploy**. First build takes ~2–3 minutes. You'll get your public URL. 🎉

## Step 4 — See who visits (analytics, logs only)
Open your app at <https://share.streamlit.io> → your app → **Manage app → Logs**.
Look for lines that start with `[AGRITRUE-ANALYTICS]` — each shows timestamp, visitor IP,
approximate city/country, and what they clicked. There is **no analytics page in the app
itself**, so the reviewer never sees it.

When running locally instead, read the log with: `python view_logs.py`

---

## Updating the live app later
Make changes, then:
```bat
git add -A
git commit -m "Update"
git push
```
Streamlit Cloud redeploys automatically within a minute.

## Notes
- The free tier sleeps the app after inactivity; the first visit after sleep takes ~30s to wake.
  Open the link once yourself before sharing so it's warm.
- Streamlit Cloud's filesystem resets on redeploy/sleep, so use the **Logs** view (Step 4) as the
  durable record of visits — that's why analytics also print to the server log, not just a file.
