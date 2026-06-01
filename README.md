# AI Try-On Course Project

Public course-project version of an AI down-jacket recommendation and virtual try-on platform.

## Contents

- `main-app/`: recommendation site, backend API, and admin dashboard.
- `tryon-workbench/`: standalone virtual try-on workbench.
- `PROJECT_OVERVIEW.md`: architecture and feature summary.
- `DESIGN.md`: design notes.

## Safety Notes

This repository intentionally excludes local databases, generated product-image datasets, dependency folders, build outputs, deployment operation logs, and real environment files.

Use `.env.example` files as templates and provide your own API keys, Cloud Run URLs, GCP project IDs, and bucket names locally or in your deployment environment.

## Local Setup

Install frontend dependencies from each frontend folder with `npm install`.
Install backend dependencies from the relevant `requirements.txt`.

No Gemini, Vertex AI, JWT, database, or cloud credentials are committed.
