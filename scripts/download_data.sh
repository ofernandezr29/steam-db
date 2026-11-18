#!/usr/bin/env bash
# Download the raw dataset from Kaggle into data/ (the raw data is never committed).
# Dataset: "Game Recommendations on Steam" by Anton Kozyriev, license CC0 1.0.
# https://www.kaggle.com/datasets/antonkozyriev/game-recommendations-on-steam
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
URL="https://www.kaggle.com/api/v1/datasets/download/antonkozyriev/game-recommendations-on-steam"
if [[ -f data/recommendations.csv && -f data/games.csv && -f data/users.csv && -f data/games_metadata.json ]]; then
    echo "data/ already has the four files"; exit 0
fi
echo "Downloading (~700 MB zip, ~2.2 GB unzipped)…"
curl -fL --retry 3 -o data/archive.zip "$URL"
unzip -o data/archive.zip -d data
rm data/archive.zip
wc -l data/*.csv data/*.json
