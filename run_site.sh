#!/bin/bash

cd /Users/pallusmassucci/Desktop/provas-4a-site
PYTHON_BIN="python3"
if [ -x ".venv/bin/python3" ]; then
  PYTHON_BIN=".venv/bin/python3"
fi

echo "==============================" >> /Users/pallusmassucci/Desktop/provas-4a-site/logs/launchd_site.log
echo "SITE iniciado em $(date)" >> /Users/pallusmassucci/Desktop/provas-4a-site/logs/launchd_site.log

$PYTHON_BIN /Users/pallusmassucci/Desktop/provas-4a-site/4a_automatico.py site >> /Users/pallusmassucci/Desktop/provas-4a-site/logs/launchd_site.log 2>&1

echo "SITE finalizado em $(date)" >> /Users/pallusmassucci/Desktop/provas-4a-site/logs/launchd_site.log
