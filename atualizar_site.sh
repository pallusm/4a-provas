#!/bin/bash
set -e

cd /Users/pallusmassucci/Desktop/provas-4a-site

python3 preview_site.py
cp preview.html index.html

git add index.html licoes.json provas.json alertas.json preview.html
git commit -m "Atualiza site" || true
git push
