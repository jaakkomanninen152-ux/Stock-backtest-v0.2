# Deploying to the web (a permanent link you can open from anywhere)

This puts the app on Streamlit's free hosting so you get a URL like
`https://your-app-name.streamlit.app` that you can bookmark and open from
your phone, laptop, or anyone else's browser -- no local setup, nothing to
launch.

## 1. Put the code on GitHub (free)

1. Create a free account at https://github.com if you don't have one.
2. Create a new repository (e.g. `stock-backtester`) -- keep it Public
   (Streamlit Community Cloud's free tier requires public repos, unless
   you're on a paid GitHub/Streamlit plan).
3. Upload every file from this project into that repository. Easiest way
   with no command line: on the repo page, click **Add file → Upload
   files**, then drag in all the `.py` files, `requirements.txt`, and
   `README.md`.

## 2. Deploy on Streamlit Community Cloud (free)

1. Go to https://share.streamlit.io and sign in with your GitHub account.
2. Click **New app**.
3. Pick your repository, the branch (usually `main`), and set the main
   file path to `streamlit_app.py`.
4. Click **Deploy**. First deploy takes a few minutes while it installs
   everything from `requirements.txt`.
5. You'll get a URL like `https://stock-backtester-yourname.streamlit.app`.
   Bookmark it -- that's your permanent link.

## 3. One important limitation: the database doesn't persist long-term

Streamlit Community Cloud's free tier uses **ephemeral storage** -- the
SQLite database file (`data/market_data.sqlite3`) gets wiped whenever the
app redeploys or "wakes up" after going to sleep from inactivity (free apps
sleep after a period of no visitors). This means:

- Data you fetch will stick around while you're actively using the app in
  one sitting.
- If you come back days later, you'll likely need to re-fetch your stocks
  (usually quick if you fetch a focused list rather than thousands of
  tickers).
- This is fine for casual/occasional use. If you want your fetched data to
  persist permanently across sleeps and redeploys, you'd need to point the
  app at an external persistent database instead of local SQLite -- e.g. a
  free-tier hosted Postgres (Supabase, Neon, Railway all have free tiers).
  That's a bigger change (swapping `database.py`'s connection string and
  adding a Postgres driver) -- let me know if you want that and I'll set
  it up.

## 4. Updating the app later

Any time you push new commits to the GitHub repo (or upload edited files
through the GitHub web UI), Streamlit Community Cloud automatically
redetects the change and redeploys within a minute or two -- no manual
redeploy step needed.

## Alternatives if you outgrow the free tier

- **Render.com** / **Railway.app** -- free tiers available, more control,
  supports persistent disks (so your database survives) but a bit more
  setup than Streamlit Community Cloud.
- **Your own server / VPS / home computer** -- run `streamlit run
  streamlit_app.py` there permanently (e.g. inside a `screen`/`tmux`
  session, or as a systemd service) and expose it via your own domain or
  a tool like Cloudflare Tunnel. Full control, fully persistent, but you
  manage the uptime yourself.
