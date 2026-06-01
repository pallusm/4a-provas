#!/bin/bash
set -e

cd /Users/pallusmassucci/Desktop/provas-4a-site

PYTHON_BIN="python3"
if [ -x ".venv/bin/python3" ]; then
  PYTHON_BIN=".venv/bin/python3"
fi

$PYTHON_BIN preview_site.py
cp preview.html index.html

git add index.html licoes.json provas.json alertas.json preview.html
git commit -m "Atualiza site" || true
git push
