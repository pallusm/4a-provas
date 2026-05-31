import json
import re
import unicodedata
from datetime import datetime, date
from pathlib import Path

BASE = Path(__file__).parent
SITE_URL = "https://pallusm.github.io/4a-provas"

def limpar_espacos(texto):
    return re.sub(r"\s+", " ", texto or "").strip()

def sem_acentos(texto):
    texto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")

def normalizar_chave(texto):
    texto = sem_acentos(texto).lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return limpar_espacos(texto)

def ler_json(nome):
    p = BASE / nome
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))

def parse_iso(d):
    if not d:
        return None
    if isinstance(d, date):
        return d
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        return None

def dia_semana(d):
    return ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][d.weekday()]

def data_curta(prazo, prazo_tipo=""):
    d = parse_iso(prazo)
    if prazo_tipo == "proxima_aula":
        return "Próxima aula"
    if not d:
        return "Sem prazo"
    return f"{dia_semana(d)}, {d.strftime('%d/%m')}"

def dias_ate(prazo):
    d = parse_iso(prazo)
    if not d:
        return 999
    return (d - date.today()).days

def nome_curto(disciplina):
    d = disciplina or ""
    dl = d.lower()
    if "matemática" in dl or "matematica" in dl: return "Matemática"
    if "português" in dl or "portugues" in dl or "língua" in dl: return "Português"
    if "história" in dl or "historia" in dl: return "História"
    if "geografia" in dl: return "Geografia"
    if "ciências" in dl or "ciencias" in dl: return "Ciências"
    if "projeto" in dl: return "Projeto de Vida"
    if "inglês" in dl or "ingles" in dl: return d
    return d or "Atividade"

def resumir(texto, limite):
    texto = limpar_espacos(texto)
    if len(texto) <= limite:
        return texto
    corte = texto[:limite].rstrip()
    if " " in corte:
        corte = corte.rsplit(" ", 1)[0]
    return corte + "..."

def limpar_texto_whatsapp(texto):
    texto = limpar_espacos(texto)
    if not texto:
        return ""

    texto = re.sub(r"(?i)^tarefa de casa\s*[:\-–]\s*", "", texto).strip()
    texto = re.sub(r"(?i)^homework\s*[:\-–]\s*", "", texto).strip()

    texto = re.sub(r"(?i)\bWB\b", "Workbook", texto)
    texto = re.sub(r"(?i)\bSB\b", "Student’s Book", texto)

    texto = re.sub(r"(?i)\bpá?g?\.\s*(\d+)", r"página \1", texto)
    texto = re.sub(r"(?i)\bpágina\s+(\d+)\s+a\s+(\d+)", r"páginas \1 a \2", texto)
    texto = re.sub(r"(?i)\bpágina\s+(\d+)\s*,\s*(\d+)\s+e\s+(\d+)", r"páginas \1, \2 e \3", texto)

    texto = re.sub(r"(?i)\bpage\s+(\d+)", r"página \1", texto)
    texto = re.sub(r"(?i)\bpages\s+(\d+)\s+(?:and|e|a)\s+(\d+)", r"páginas \1 a \2", texto)

    texto = re.sub(r"(?i)\bexs?\.\s*(\d+)", r"exercício \1", texto)
    texto = re.sub(r"(?i)\bex\s+(\d+)", r"exercício \1", texto)
    texto = re.sub(r"(?i)\bexercício\s+(\d+)\s+e\s+(\d+)", r"exercícios \1 e \2", texto)
    texto = re.sub(r"(?i)\bexercício\s+(\d+),\s*(\d+)\s+e\s+(\d+)", r"exercícios \1, \2 e \3", texto)

    texto = re.sub(r"(?i)\s*[-–—]?\s*Para\s*[:\-]?\s*\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\.?\s*$", "", texto).strip()

    if texto and texto[0].islower():
        texto = texto[0].upper() + texto[1:]

    return limpar_espacos(texto)

def core(texto, limite=520):
    texto = limpar_espacos(texto)
    tn = sem_acentos(texto).lower()

    if "roda de leitura" in tn and "entrevista" in tn:
        return "5ª Proposta da Roda de Leitura no Google Classroom: escolher um personagem da história, elaborar 4 perguntas e criar 4 respostas como se fosse uma entrevista. Pode apresentar em cartaz, vídeo, Canva ou outra ideia criativa."

    if "especiarias" in tn and "trabalho avaliativo" in tn:
        return "Trazer as imagens das especiarias solicitadas no planner. Elas serão usadas no trabalho avaliativo de História em 26/05. Não falte e não esqueça o material."

    return limpar_texto_whatsapp(resumir(texto, limite))

def eh_comunicado(item):
    return item.get("disciplina") == "Comunicado" or item.get("fonte") == "Comunicados" or bool(item.get("pdf_url"))

def ordenar(item):
    return (dias_ate(item.get("prazo")), nome_curto(item.get("disciplina", "")))

def dedup(lista, campo):
    vistos = set()
    out = []
    for item in lista:
        texto = item.get(campo) or item.get("texto") or item.get("conteudo") or item.get("tarefa") or ""
        prazo = item.get("prazo") or item.get("prazo_tipo") or "sem_prazo"
        chave = f"{normalizar_chave(item.get('disciplina', ''))}|{prazo}|{normalizar_chave(texto)[:120]}"
        if chave and chave not in vistos:
            vistos.add(chave)
            out.append(item)
    return out

licoes = ler_json("licoes.json")
provas = ler_json("provas.json")
alertas = ler_json("alertas.json")

comunicados_msg = dedup([a for a in alertas if eh_comunicado(a)], "texto")[:3]
alertas_msg = dedup([a for a in alertas if not eh_comunicado(a)], "texto")
provas_msg = dedup(provas, "conteudo")
licoes_msg = dedup(licoes, "tarefa")

chaves_provas = {normalizar_chave(p.get("conteudo") or p.get("texto") or "")[:80] for p in provas_msg}
alertas_msg = [
    a for a in alertas_msg
    if normalizar_chave(a.get("texto") or a.get("conteudo") or "")[:80] not in chaves_provas
]

comunicados_msg = sorted(comunicados_msg, key=ordenar)[:3]
alertas_msg = sorted(alertas_msg, key=ordenar)[:4]
provas_msg = sorted(provas_msg, key=ordenar)[:6]
licoes_msg = sorted(licoes_msg, key=ordenar)[:8]

hora = datetime.now().hour
if hora < 15:
    titulo = "📚 *4ºA — Resumo do Dia*"
    subtitulo = "_Bom dia! Veja o que realmente precisa de atenção._"
else:
    titulo = "📚 *4ºA — Lembrete da Tarde*"
    subtitulo = "_Boa tarde! Resumo das próximas pendências._"

linhas = [titulo, subtitulo, ""]

if comunicados_msg:
    linhas.append("📣 *Comunicado importante*")
    for c in comunicados_msg:
        linhas.append(f"• *{data_curta(c.get('prazo'), c.get('prazo_tipo', ''))}*")
        titulo_c = c.get("titulo") or "Comunicado importante"
        texto_c = c.get("texto") or c.get("conteudo") or ""
        if "simulado" in normalizar_chave(titulo_c + " " + texto_c):
            linhas.append("  2º Simulado Anglo — 01/06 e 02/06")
            linhas.append("  01/06: Português, História e Geografia.")
            linhas.append("  02/06: Matemática e Ciências.")
            linhas.append("  Vale até 1,0 ponto na média trimestral.")
            linhas.append("  Não há prova substitutiva.")
            linhas.append("  PDF completo disponível no site.")
        else:
            linhas.append("  " + core(titulo_c + ". " + texto_c, 420))
    linhas.append("")

if alertas_msg:
    linhas.append("⚠️ *Atenção importante*")
    for a in alertas_msg:
        linhas.append(f"• *{nome_curto(a.get('disciplina'))} — {data_curta(a.get('prazo'), a.get('prazo_tipo', ''))}*")
        linhas.append("  " + core(a.get("texto") or a.get("conteudo") or "", 360))
    linhas.append("")

if provas_msg:
    linhas.append("📝 *Provas e trabalhos*")
    for p in provas_msg:
        linhas.append(f"• *{nome_curto(p.get('disciplina'))} — {data_curta(p.get('prazo'), p.get('prazo_tipo', ''))}*")
        linhas.append("  " + core(p.get("conteudo") or p.get("texto") or "", 300))
    linhas.append("")

linhas.append("📌 *Lições*")
if licoes_msg:
    for l in licoes_msg:
        linhas.append(f"• *{nome_curto(l.get('disciplina'))} — {data_curta(l.get('prazo'), l.get('prazo_tipo', ''))}*")
        linhas.append("  " + core(l.get("tarefa") or l.get("conteudo") or l.get("texto") or "", 520))
else:
    linhas.append("✅ Nenhuma lição pendente.")

linhas.append("")
linhas.append("🌐 *Ver tudo com detalhes:*")
linhas.append(SITE_URL)

mensagem = "\n".join(linhas)

print("\nPrévia mockada do WhatsApp:\n")
print(mensagem)

try:
    import pyperclip
    pyperclip.copy(mensagem)
    print("\n✅ Mensagem copiada para a área de transferência.")
except Exception:
    pass
