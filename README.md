# grade-histogram-plotter

Small Flask app that plots a grade histogram from pasted scores and custom cutoff values.

## Features

- one grade per line input
- custom cutoff buckets
- histogram rendered as an image in the browser
- summary statistics for numeric grades
- non-numeric entries counted in a `NaN` bucket

## Local development

1. Create and activate a virtual environment.
2. Install dependencies:

	`pip install -r requirements.txt`

3. Run the app:

	`python flask_app.py`

4. Open http://127.0.0.1:5000

## Deploying on Render

This repository includes [render.yaml](render.yaml) for a Blueprint deploy.

### Option 1: Blueprint deploy

1. Push this repository to GitHub.
2. In Render, choose **New +** → **Blueprint**.
3. Select the repository.
4. Render will read [render.yaml](render.yaml) and create the web service.

### Option 2: Manual web service

If you do not want to use the blueprint file, create a Python web service with:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --bind 0.0.0.0:$PORT flask_app:app`

## Files added for deployment

- [requirements.txt](requirements.txt) — Python dependencies for local use and Render builds
- [render.yaml](render.yaml) — Render Blueprint configuration

## Notes

- The app uses the non-interactive Matplotlib `Agg` backend so it works on Render.
- Request logs are written to `log.txt`. On Render, the filesystem is ephemeral, so that file is not persistent across redeploys or restarts.