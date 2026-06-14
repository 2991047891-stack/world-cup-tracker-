# World Cup Prediction Tracker Deployment

This folder is ready to deploy as a small hosted collaborative app.

## Recommended: Render

1. Create a GitHub repository and upload the files in this `outputs` folder.
2. Go to Render and create a new **Blueprint** from that repository.
3. Render will read `render.yaml`, create a Python web service, and attach a persistent disk at `/var/data`.
4. After deploy, open:

   `https://YOUR-RENDER-SERVICE.onrender.com/world-cup-prediction-tracker.html`

## Why the disk matters

The app saves shared predictions in:

`shared-predictions.json`

On Render, new edits are written to `/var/data/shared-predictions.json`, so predictions survive restarts.

## Local Run

```bash
python3 collaborative_server.py
```

Then open:

`http://127.0.0.1:4180/world-cup-prediction-tracker.html`
