import json
from datetime import datetime
from pathlib import Path
import subprocess

BASE = Path(__file__).parent

def ler_json(nome):
    p = BASE / nome
    if not p.exists():
        print(f"⚠️ Arquivo não encontrado: {nome}")
        return []
    return json.loads(p.read_text(encoding="utf-8"))

licoes = ler_json("licoes.json")
provas = ler_json("provas.json")
alertas = ler_json("alertas.json")

template = (BASE / "index_template.html").read_text(encoding="utf-8")
atualizado = datetime.now().strftime("%d/%m/%Y às %H:%M")

html = template
html = html.replace("DATA_LICOES_PLACEHOLDER", json.dumps(licoes, ensure_ascii=False))
html = html.replace("DATA_PROVAS_PLACEHOLDER", json.dumps(provas, ensure_ascii=False))
html = html.replace("DATA_ALERTAS_PLACEHOLDER", json.dumps(alertas, ensure_ascii=False))
html = html.replace("ATUALIZADO_PLACEHOLDER", atualizado)

saida = BASE / "preview.html"
saida.write_text(html, encoding="utf-8")

print("✅ Preview do site gerado:")
print(saida)
print(f"📌 Lições: {len(licoes)} | Provas: {len(provas)} | Alertas: {len(alertas)}")

try:
    subprocess.run(["open", str(saida)], check=False)
except Exception:
    pass
