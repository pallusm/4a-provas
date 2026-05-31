"""
4°A — Eduardo Gomes
Automação completa: Site + WhatsApp

Versão com lógica melhorada:
- não perde lições sem data;
- separa aviso/avaliação de lição quando vêm no mesmo texto;
- preserva G1/G2 em Inglês;
- evita deduplicação agressiva;
- salva JSONs locais + debug_processamento.json;
- mantém WhatsApp enviando lista de lições.
"""

import json
import asyncio
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, date, timedelta
from pathlib import Path
from difflib import SequenceMatcher

# ── Configuração ──────────────────────────────────────────────────────────────

def carregar_env_local():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for linha in env_path.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))

carregar_env_local()

EMAIL       = os.getenv("CLASSAPP_EMAIL", "")
SENHA       = os.getenv("CLASSAPP_SENHA", "")

FILHOS = [
    {"nome": "Benício", "entity_id": "1238516186"},
    {"nome": "Heitor",  "entity_id": "1238516187"},
]

GITHUB_USER    = "pallusm"
GITHUB_REPO    = "4a-provas"
WHATSAPP_GRUPO = "4°A Fund. Manhã - Eduardo Gomes"
NOTIFICAR_SITE = os.getenv("NOTIFICAR_SITE", "").lower() in ("1", "true", "sim", "yes")
MOSTRAR_NAVEGADOR = os.getenv("MOSTRAR_NAVEGADOR", "").lower() in ("1", "true", "sim", "yes")

URL_LOGIN = "https://classapp.com.br/auth"
URL_AULAS = "https://wap.educacionalcloud.com.br/Pedagogico/Aulas"
URL_COMUNICADOS = "https://wap.educacionalcloud.com.br/Comunicacao/Comunicados"
SITE_URL  = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}"

# Tarefas sem data explícita entram no site apenas se estiverem nas primeiras linhas
# do portal, para evitar que tarefas antigas sem prazo fiquem penduradas para sempre.
MAX_LINHA_SEM_PRAZO = 15

# Palavras que indicam avaliação de verdade
PALAVRAS_PROVA = [
    "avaliação", "avaliacao", "atividade avaliativa", "trabalho avaliativo",
    "trabalho avaliativa", "prova", "prova trimestral", "simulado",
    "apresentação avaliativa", "apresentacao avaliativa",
]

# Grade estimada do 4ºA.
# Python usa: segunda=0, terça=1, quarta=2, quinta=3, sexta=4.
GRADE_ESTIMADA = {
    "portugues": [0, 2, 3, 4],
    "lingua portuguesa": [0, 2, 3, 4],
    "matematica": [0, 1, 2, 3],
    "arte": [1],
    "historia": [1],
    "ingles": [1, 2, 3, 4],
    "ciencias": [3, 4],
    "geografia": [3],
    "educacao fisica": [2],
    "educacao tecnologica": [2],
    "projeto de vida": [0],
}

def dias_grade_para_disciplina(disciplina: str) -> list[int]:
    chave = normalizar_chave(disciplina)
    if "ingles" in chave or "l e m" in chave:
        return GRADE_ESTIMADA["ingles"]
    if "portugues" in chave or "lingua portuguesa" in chave:
        return GRADE_ESTIMADA["lingua portuguesa"]
    if "matematica" in chave:
        return GRADE_ESTIMADA["matematica"]
    if "ciencias" in chave:
        return GRADE_ESTIMADA["ciencias"]
    if "geografia" in chave:
        return GRADE_ESTIMADA["geografia"]
    if "historia" in chave:
        return GRADE_ESTIMADA["historia"]
    if "arte" in chave:
        return GRADE_ESTIMADA["arte"]
    if "educacao fisica" in chave:
        return GRADE_ESTIMADA["educacao fisica"]
    if "educacao tecnologica" in chave:
        return GRADE_ESTIMADA["educacao tecnologica"]
    if "projeto de vida" in chave:
        return GRADE_ESTIMADA["projeto de vida"]
    return []

def calcular_proxima_aula(data_aula: date | None, disciplina: str) -> date | None:
    if not data_aula:
        return None

    dias = dias_grade_para_disciplina(disciplina)
    if not dias:
        return None

    for i in range(1, 15):
        candidata = data_aula + timedelta(days=i)
        if candidata.weekday() in dias:
            return candidata

    return None


# Palavras que geram alerta, mas não necessariamente prova
PALAVRAS_ALERTA = [
    "não falte", "nao falte", "não esqueça", "nao esqueca",
    "importante", "atenção", "atencao", "obrigatório", "obrigatorio",
    "planner", "trabalho avaliativo", "atividade avaliativa",
]

MARCADORES_TAREFA = [
    r"tarefa de casa\s*:",
    r"homework\s*:",
    r"atividade para casa\s*:",
    r"em casa\s*:",
]

ONESIGNAL_APP_ID  = "1c203a60-4ab3-4ee6-8c14-a307ad62fb7b"
ONESIGNAL_API_KEY = "os_v2_app_dqqduyckwnhondauumd22yx3pnrh4zeswxtuco5gatv4vcertwmiu46xydsemvyzufyqft7qyoczg57pucuquyo5d6gnxiccyreirsa"

# ── Utilidades de texto e data ────────────────────────────────────────────────

def limpar_espacos(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


def sem_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def normalizar_chave(texto: str) -> str:
    texto = sem_acentos(texto).lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return limpar_espacos(texto)


def parse_data(texto: str) -> date | None:
    """Converte datas dd/mm, dd-mm, dd/mm/aaaa etc. Sem warning no Python 3.14+."""
    ano = date.today().year
    texto = (texto or "").strip()

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            d = datetime.strptime(texto, fmt).date()
            return d if d.year == ano else None
        except ValueError:
            pass

    for sep in ("/", "-"):
        m = re.fullmatch(r"(\d{1,2})" + re.escape(sep) + r"(\d{1,2})", texto)
        if m:
            dia, mes = m.groups()
            try:
                return datetime.strptime(f"{dia}{sep}{mes}{sep}{ano}", f"%d{sep}%m{sep}%Y").date()
            except ValueError:
                pass

    return None


def extrair_prazos(texto: str) -> list[date]:
    texto = texto or ""
    # Prioriza datas depois de palavras de prazo.
    padrao = r"(?:para|prazo|data|dia|não falte|nao falte)[:\s,\-]+(\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?)"
    datas = []
    for m in re.findall(padrao, texto, re.IGNORECASE):
        d = parse_data(m)
        if d:
            datas.append(d)

    # Fallback: qualquer data no texto.
    if not datas:
        for m in re.findall(r"\b(\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?)\b", texto):
            d = parse_data(m)
            if d:
                datas.append(d)

    # Remove duplicatas preservando ordem.
    out = []
    seen = set()
    for d in datas:
        if d not in seen:
            out.append(d)
            seen.add(d)
    return out


def contem_nao_consta(texto: str) -> bool:
    t = normalizar_chave(texto)
    return "tarefa de casa nao consta" in t or t.endswith("nao consta") or t == "nao consta"


def extrair_grupo(disciplina: str) -> str | None:
    m = re.search(r"\bG\s*([12])\b", disciplina or "", re.IGNORECASE)
    return f"G{m.group(1)}" if m else None


def normalizar_disciplina(disciplina: str) -> str:
    d = limpar_espacos(disciplina)
    dl = d.lower()
    grupo = extrair_grupo(d)

    if "l.e.m" in dl or "inglês" in dl or "ingles" in dl:
        return f"Inglês — {grupo}" if grupo else "Inglês"
    if "língua" in dl or "português" in dl or "portugues" in dl:
        return "Português"
    if "matemática" in dl or "matematica" in dl:
        return "Matemática"
    if "história" in dl or "historia" in dl:
        return "História"
    if "ciências" in dl or "ciencias" in dl:
        return "Ciências"
    if "geografia" in dl:
        return "Geografia"
    if "projeto" in dl:
        return "Projeto de Vida"
    if "educação física" in dl or "educacao fisica" in dl:
        return "Ed. Física"
    if "tecnológica" in dl or "tecnologica" in dl:
        return "Tecnologia"
    if "arte" in dl:
        return "Arte"
    return d


def remover_prefixo_disciplina(texto: str, disciplina: str) -> str:
    texto = limpar_espacos(texto)
    disciplina = limpar_espacos(disciplina)
    if disciplina and texto.lower().startswith(disciplina.lower()):
        return limpar_espacos(texto[len(disciplina):])
    return texto


def extrair_tarefa(texto: str) -> str:
    """Pega somente o trecho de tarefa/homework, sem o conteúdo da aula."""
    texto = limpar_espacos(texto)
    padrao = r"(" + "|".join(MARCADORES_TAREFA) + r")"
    partes = re.split(padrao, texto, flags=re.IGNORECASE)
    if len(partes) <= 1:
        return ""

    # Pega tudo depois do primeiro marcador de tarefa.
    tarefa = limpar_espacos("".join(partes[2:]))

    # Remove repetições no início: "Tarefa de casa: Tarefa de casa: ..."
    while True:
        novo = re.sub(r"^(tarefa de casa|homework|atividade para casa|em casa)\s*[:\-]\s*", "", tarefa, flags=re.IGNORECASE).strip()
        if novo == tarefa:
            break
        tarefa = novo

    if contem_nao_consta(tarefa):
        return ""
    return tarefa


def e_prova(texto: str) -> bool:
    t = normalizar_chave(texto)
    return any(normalizar_chave(p) in t for p in PALAVRAS_PROVA)


def e_alerta(texto: str) -> bool:
    t = normalizar_chave(texto)
    return any(normalizar_chave(p) in t for p in PALAVRAS_ALERTA)


def tipo_prazo(texto: str, prazos: list[date]) -> str:
    t = normalizar_chave(texto)
    if prazos:
        return "data_definida"
    if "proxima aula" in t or "próxima aula" in (texto or "").lower() or "trazer para correcao" in t:
        return "proxima_aula"
    return "sem_prazo"


def separar_avaliacao_e_licao(tarefa: str) -> tuple[str | None, str | None]:
    """Se avaliação e lição vierem juntas, separa em dois textos.

    Exemplo História:
    'Atenção... trabalho avaliativo... Para: 26-05 Tarefa de casa - p. 170... Para: 26-05'
    """
    tarefa = limpar_espacos(tarefa)

    # Procura um segundo marcador de tarefa no meio do texto.
    # Não considera marcador no começo, porque isso é só prefixo repetido.
    m = re.search(r"(?i)\b(tarefa de casa|homework|atividade para casa|em casa)\s*[-:]\s*", tarefa)
    if m and m.start() > 25:
        antes = limpar_espacos(tarefa[:m.start()])
        depois = limpar_espacos(tarefa[m.start():])
        depois = re.sub(r"(?i)^(tarefa de casa|homework|atividade para casa|em casa)\s*[-:]\s*", "", depois).strip()
        if e_prova(antes) or e_alerta(antes):
            return antes, depois
        if e_prova(depois) or e_alerta(depois):
            return depois, antes

    # Se o texto inteiro é avaliativo, vira prova/avaliação.
    if e_prova(tarefa):
        return tarefa, None

    return None, tarefa


def escolher_prazo(texto: str, preferir_ultimo: bool = True) -> date | None:
    prazos = extrair_prazos(texto)
    if not prazos:
        return None
    return prazos[-1] if preferir_ultimo else prazos[0]


def extrair_conteudo_aula(texto_bruto: str, disciplina_original: str = "") -> str:
    """
    Extrai o conteúdo trabalhado em aula, removendo a parte de tarefa de casa.
    Exemplo:
    'Língua Portuguesa Estudo do texto... Tarefa de casa: página 109...'
    vira:
    'Estudo do texto...'
    """
    texto = limpar_espacos(texto_bruto or "")
    disciplina_original = limpar_espacos(disciplina_original or "")

    # Remove a disciplina do começo quando ela aparece como prefixo.
    if disciplina_original and texto.lower().startswith(disciplina_original.lower()):
        texto = texto[len(disciplina_original):].strip()

    # Corta antes do primeiro marcador de tarefa.
    marcadores = [
        "Tarefa de casa:",
        "tarefa de casa:",
        "Homework:",
        "homework:",
        "Atividade para casa:",
        "atividade para casa:",
    ]

    for marcador in marcadores:
        if marcador in texto:
            return limpar_espacos(texto.split(marcador, 1)[0])

    return limpar_espacos(texto)


def criar_item_base(tipo: str, disciplina: str, texto: str, prazo: date | None, fonte: dict, categoria_prazo: str) -> dict:
    item = {
        "tipo": tipo,
        "disciplina": disciplina,
        "grupo": extrair_grupo(disciplina),
        "prazo": prazo,
        "sem_prazo": prazo is None,
        "prazo_tipo": categoria_prazo,
        "origens": [fonte.get("filho", "")],
        "linha_origem": fonte.get("linha"),
        "fonte": fonte.get("filho", ""),
    }
    if tipo == "licao":
        item["tarefa"] = texto
    else:
        item["conteudo"] = texto
    return item


def texto_item(item: dict) -> str:
    return item.get("tarefa") or item.get("conteudo") or item.get("texto") or ""


def similar(a: str, b: str) -> float:
    a, b = normalizar_chave(a), normalizar_chave(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def dedup_inteligente(lista: list[dict]) -> list[dict]:
    """Remove duplicatas reais, mas preserva G1/G2 e textos diferentes."""
    resultado: list[dict] = []

    for item in lista:
        txt = texto_item(item)
        prazo_key = item["prazo"].isoformat() if item.get("prazo") else item.get("prazo_tipo", "sem_prazo")
        disc_key = normalizar_chave(item.get("disciplina", ""))
        tipo_key = item.get("tipo")

        duplicado = None
        for atual in resultado:
            atual_prazo = atual["prazo"].isoformat() if atual.get("prazo") else atual.get("prazo_tipo", "sem_prazo")
            if atual.get("tipo") != tipo_key:
                continue
            if normalizar_chave(atual.get("disciplina", "")) != disc_key:
                continue
            if atual_prazo != prazo_key:
                continue
            # Só remove se o texto for praticamente igual.
            if similar(texto_item(atual), txt) >= 0.92:
                duplicado = atual
                break

        if duplicado:
            # Mantém o texto mais completo e agrega origens.
            if len(txt) > len(texto_item(duplicado)):
                if item.get("tipo") == "licao":
                    duplicado["tarefa"] = txt
                else:
                    duplicado["conteudo"] = txt
            for origem in item.get("origens", []):
                if origem and origem not in duplicado.setdefault("origens", []):
                    duplicado["origens"].append(origem)
        else:
            resultado.append(item)

    def sort_key(x):
        return (x.get("prazo") is None, x.get("prazo") or date.max, x.get("disciplina", ""), texto_item(x)[:60])

    resultado.sort(key=sort_key)
    return resultado


def serial(lista: list[dict]) -> list[dict]:
    out = []
    for i in lista:
        d = dict(i)
        if isinstance(d.get("prazo"), date):
            d["prazo"] = d["prazo"].isoformat()
        out.append(d)
    return out


def prazo_eh_futuro(item: dict, hoje: date) -> bool:
    if item.get("sem_prazo"):
        return True
    return item.get("prazo") and item["prazo"] >= hoje


def prazo_eh_historico(item: dict, hoje: date) -> bool:
    if item.get("sem_prazo"):
        return False
    return item.get("prazo") and item["prazo"] < hoje


# ── Automação ClassApp / Portal ───────────────────────────────────────────────

async def fazer_login(page, console):
    console.print("[yellow]🔐 Fazendo login...[/yellow]")
    await page.goto(URL_LOGIN, wait_until="networkidle")
    await page.wait_for_timeout(3000)

    await page.wait_for_selector("input", timeout=15000)
    campo = None
    for inp in await page.locator("input:visible").all():
        tipo = await inp.get_attribute("type") or ""
        nome = await inp.get_attribute("name") or ""
        ph   = await inp.get_attribute("placeholder") or ""
        if tipo in ("email", "text") or "mail" in nome.lower() or "mail" in ph.lower():
            campo = inp
            break
    if not campo:
        campo = page.locator("input:visible").first

    await campo.fill(EMAIL)
    for s in [
        "button:visible:has-text('Entrar')",
        "button:visible:has-text('Continuar')",
        "button:visible:has-text('Próximo')",
        "button[type='submit']:visible",
    ]:
        if await page.locator(s).count() > 0:
            await page.locator(s).first.click(force=True)
            break
    else:
        await page.keyboard.press("Enter")
    await page.wait_for_timeout(1500)

    if await page.locator("input[type='password']:visible").count() == 0:
        for texto_senha in [
            "Entrar com senha",
            "Entrar com minha senha",
            "Usar senha",
            "Usar minha senha",
            "Login com senha",
            "Senha",
        ]:
            clicou_senha = False
            for locator in [
                page.get_by_role("button", name=re.compile(texto_senha, re.I)),
                page.get_by_role("link", name=re.compile(texto_senha, re.I)),
                page.get_by_text(re.compile(texto_senha, re.I)),
            ]:
                try:
                    if await locator.count() > 0:
                        await locator.first.click(force=True)
                        console.print("  [dim]Opção de senha selecionada.[/dim]")
                        clicou_senha = True
                        break
                except Exception:
                    pass
            if clicou_senha:
                break
        await page.wait_for_timeout(2000)

    if await page.locator("input[type='password']:visible").count() == 0 and MOSTRAR_NAVEGADOR:
        console.print("[yellow]Clique em 'entrar com senha' no Chromium aberto e pressione Enter aqui.[/yellow]")
        await asyncio.to_thread(input)
        await page.wait_for_timeout(1000)

    await page.wait_for_selector("input[type='password']", timeout=15000)
    senha_input = page.locator("input[type='password']").first
    await senha_input.fill(SENHA)
    await page.wait_for_timeout(800)

    # Clique robusto no botão azul "Enter"
    clicou = False
    for seletor in [
        "button:visible:has-text('Continuar')",
        "button:visible:has-text('Enter')",
        "text=Enter",
        "button:visible:has-text('Entrar')",
        "button:visible:has-text('Acessar')",
        "button[type='submit']:visible"
    ]:
        try:
            if await page.locator(seletor).count() > 0:
                await page.locator(seletor).first.click(force=True)
                clicou = True
                break
        except Exception:
            pass

    if not clicou:
        await senha_input.press("Enter")

    await page.wait_for_timeout(6000)

    console.print(f"[dim]URL após tentativa de login: {page.url}[/dim]")
    await page.screenshot(path="debug_login_falhou.png", full_page=True)

    if "auth" in page.url:
        if MOSTRAR_NAVEGADOR:
            console.print("[yellow]Login automático não avançou. Corrija no Chromium aberto e pressione Enter aqui para continuar.[/yellow]")
            await asyncio.to_thread(input)
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000)
            console.print(f"[dim]URL após login manual: {page.url}[/dim]")
            if "auth" not in page.url:
                console.print("  ✅ Login manual OK!\n")
                return True
        console.print("[red]❌ Login falhou[/red]")
        console.print("[yellow]📸 Print salvo em debug_login_falhou.png[/yellow]")
        return False
    console.print("  ✅ Login OK!\n")
    return True


async def buscar_dados_filho(page, contexto, filho, console):
    """Acessa o portal de um filho e retorna todos os dados brutos."""
    nome = filho["nome"]
    entity_id = filho["entity_id"]
    url_acessos = f"https://classapp.com.br/entities/{entity_id}/accesses"

    console.print(f"[yellow]👦 Buscando dados de {nome}...[/yellow]")
    await page.goto(url_acessos, wait_until="networkidle")

    botao = None
    for _ in range(40):
        await page.wait_for_timeout(1000)
        c = await page.locator("button:has-text('Acessar')").all()
        if c:
            botao = c[0]
            break

    if not botao:
        console.print(f"  [red]❌ Botão não encontrado para {nome}[/red]")
        return []

    try:
        async with contexto.expect_page(timeout=15000) as nova_info:
            await botao.click(timeout=10000, force=True)
        page_edu = await nova_info.value
        await page_edu.wait_for_load_state("networkidle")
        await page_edu.wait_for_timeout(4000)
    except Exception:
        await botao.click()
        await page.wait_for_load_state("networkidle")
        page_edu = page
        await page_edu.wait_for_timeout(4000)

    if URL_AULAS not in page_edu.url:
        await page_edu.goto(URL_AULAS, wait_until="networkidle")
        await page_edu.wait_for_timeout(4000)

    # Preferência: ler o JSON interno do portal, porque ele traz a data real da aula.
    try:
        model = await page_edu.evaluate("() => (typeof model !== 'undefined' ? model : (window.model || null))")
    except Exception:
        model = None

    # Fallback: em algumas páginas o model aparece no HTML como "var model = {...}",
    # mas não fica acessível como window.model.
    if not model:
        try:
            html_model = await page_edu.content()
            m = re.search(r"var\s+model\s*=\s*(\{[\s\S]*?\});", html_model)
            if m:
                model = json.loads(m.group(1))
        except Exception:
            model = None

    if model and model.get("Aulas"):
        dados = []
        linha_idx = 1

        for bloco_aula in model.get("Aulas", []):
            for svc in bloco_aula.get("SVC", []) or []:
                for aula in svc.get("aulas", []) or []:
                    disciplina = limpar_espacos(aula.get("disciplina", ""))
                    conteudo = limpar_espacos(aula.get("conteudo", ""))
                    tarefa = limpar_espacos(aula.get("tarefa", ""))
                    data_txt = limpar_espacos(aula.get("data", "")).split(" ")[0]
                    data_aula = parse_data(data_txt)

                    if not disciplina:
                        continue

                    dados.append({
                        "filho": nome,
                        "linha": linha_idx,
                        "data_aula": data_aula,
                        "disciplina_original": disciplina,
                        "disciplina": disciplina,
                        "texto": limpar_espacos(f"{disciplina} {conteudo} {tarefa}"),
                    })
                    linha_idx += 1

        console.print(f"  {len(dados)} registros encontrados via model")

        if page_edu is not page:
            await page_edu.close()

        return dados

    linhas = await page_edu.locator("table tbody tr").all()
    console.print(f"  {len(linhas)} registros encontrados")

    dados = []
    data_aula_atual = None

    for idx, linha in enumerate(linhas, start=1):
        celulas = await linha.locator("td").all_inner_texts()
        celulas_limpas = [c.strip() for c in celulas if c.strip()]

        # Algumas linhas da tabela são apenas a data, exemplo: 21/05/2026.
        if len(celulas_limpas) == 1:
            possivel_data = parse_data(celulas_limpas[0])
            if possivel_data:
                data_aula_atual = possivel_data
            continue

        if len(celulas_limpas) < 2:
            continue

        dados.append({
            "filho": nome,
            "linha": idx,
            "data_aula": data_aula_atual,
            "disciplina_original": celulas_limpas[0],
            "disciplina": celulas_limpas[0],
            "texto": limpar_espacos(" ".join(celulas_limpas)),
        })

    if page_edu is not page:
        await page_edu.close()

    return dados



def extrair_datas_futuras_comunicado(texto: str, hoje: date) -> list[date]:
    """Tenta achar datas futuras em textos de comunicados."""
    texto_limpo = sem_acentos(texto or "").lower()
    ano = hoje.year
    datas = []

    meses = {
        "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
        "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
        "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    }

    # Ex.: 1º e 02 de junho / 1 e 02 de junho
    for m in re.finditer(r"(\d{1,2})(?:º|o)?(?:\s*e\s*(\d{1,2})(?:º|o)?)?\s+de\s+([a-z]+)", texto_limpo):
        mes = meses.get(m.group(3))
        if not mes:
            continue
        for dia_txt in [m.group(1), m.group(2)]:
            if not dia_txt:
                continue
            try:
                d = date(ano, mes, int(dia_txt))
                if d >= hoje:
                    datas.append(d)
            except Exception:
                pass

    # Ex.: 01/06, 02/06, 01/06/2026
    for m in re.finditer(r"\b(\d{1,2})(?:º|o)?[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", texto_limpo):
        try:
            dia = int(m.group(1))
            mes = int(m.group(2))
            ano_data = ano
            if m.group(3):
                ano_data = int(m.group(3))
                if ano_data < 100:
                    ano_data += 2000
            d = date(ano_data, mes, dia)
            if d >= hoje:
                datas.append(d)
        except Exception:
            pass

    return sorted(set(datas))


def texto_visivel_html(html: str) -> str:
    """Remove tags simples de HTML, decodifica entidades e limpa espaços."""
    from html import unescape
    html = re.sub(r"<br\s*/?>", " ", html or "", flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = unescape(html)
    html = re.sub(r"\xa0|&nbsp;", " ", html)
    return limpar_espacos(html)


def comunicado_simulado_padrao(hoje: date) -> dict | None:
    """Mantém o comunicado do 2º Simulado visível até a primeira data da prova."""
    data_simulado = date(2026, 6, 1)
    if hoje > data_simulado:
        return None

    texto = (
        "2º Simulado Anglo - 2º trimestre 4º ano do Ensino Fundamental. "
        "Comunicado 77/26. Nos dias 01/06 e 02/06, a escola realizará o 2º Simulado Anglo 2026. "
        "01/06: Língua Portuguesa, História e Geografia. "
        "02/06: Matemática e Ciências. "
        "A atividade vale de 0 a 1,0 ponto, com nota global para as disciplinas. "
        "Não há prova substitutiva para os simulados. "
        "O comunicado completo e os conteúdos estão no PDF oficial."
    )

    return {
        "tipo": "alerta",
        "disciplina": "Comunicado",
        "fonte": "Comunicados",
        "origens": ["Comunicados"],
        "grupo": None,
        "linha_origem": 77,
        "prazo": data_simulado,
        "prazo_tipo": "data_definida",
        "sem_prazo": False,
        "titulo": "2º Simulado Anglo - 2º trimestre 4º ano do Ensino Fundamental",
        "texto": texto,
        "conteudo": texto,
        "conteudo_aula": "",
        "link": "https://wap.educacionalcloud.com.br/Comunicacao/ComunicadoDet/370509",
        "pdf_url": "https://documentos.educacionalcloud.com.br/colegios/EGOMES/comunicados/77-%20Simulado%20Anglo%20-%204EF.pdf",
    }


def garantir_comunicado_simulado(alertas: list[dict], hoje: date) -> list[dict]:
    comunicado = comunicado_simulado_padrao(hoje)
    if not comunicado:
        return alertas

    chave_simulado = normalizar_chave(comunicado["titulo"])
    for item in alertas:
        texto = f"{item.get('titulo', '')} {item.get('texto', '')} {item.get('conteudo', '')}"
        if "simulado anglo" in normalizar_chave(texto) or normalizar_chave(item.get("titulo", "")) == chave_simulado:
            return alertas

    return alertas + [comunicado]


async def buscar_comunicados_importantes(page, contexto, filho, console, hoje: date) -> list[dict]:
    """Busca comunicados importantes do portal e transforma em alertas."""
    from urllib.parse import urljoin
    from urllib.request import urlretrieve
    from html import unescape

    try:
        from pypdf import PdfReader
    except Exception:
        PdfReader = None

    nome = filho["nome"]
    entity_id = filho["entity_id"]
    url_acessos = f"https://classapp.com.br/entities/{entity_id}/accesses"

    console.print("[yellow]📣 Buscando comunicados importantes...[/yellow]")

    await page.goto(url_acessos, wait_until="networkidle")
    await page.wait_for_timeout(2000)

    botao = None
    for _ in range(30):
        await page.wait_for_timeout(500)
        c = await page.locator("button:has-text('Acessar')").all()
        if c:
            botao = c[0]
            break

    if not botao:
        console.print("  [yellow]⚠️ Botão Acessar não encontrado para comunicados.[/yellow]")
        return []

    try:
        async with contexto.expect_page(timeout=15000) as nova_info:
            await botao.click(timeout=10000, force=True)
        page_edu = await nova_info.value
        await page_edu.wait_for_load_state("networkidle")
    except Exception:
        await botao.click()
        await page.wait_for_load_state("networkidle")
        page_edu = page

    await page_edu.goto(URL_COMUNICADOS, wait_until="networkidle")
    await page_edu.wait_for_timeout(3000)

    linhas = await page_edu.locator("#ComunicadoAluno table tbody tr").all()

    palavras = [
        "simulado", "prova", "provas", "avaliação", "avaliacao",
        "recuperação", "recuperacao", "reunião", "reuniao",
        "encontro entre pais", "pais e professores"
    ]

    ignorar = [
        "dança", "danca", "street dance", "estacionamento",
        "atividades esportivas para pais", "sos educação", "sos educacao"
    ]

    comunicados = []
    base_url = "https://wap.educacionalcloud.com.br"

    for idx, linha in enumerate(linhas, start=1):
        celulas = await linha.locator("td").all_inner_texts()
        celulas = [limpar_espacos(c) for c in celulas if limpar_espacos(c)]

        if len(celulas) < 2:
            continue

        data_publicacao_txt = celulas[0]
        titulo = celulas[1]
        titulo_norm = sem_acentos(titulo).lower()

        if not any(p in titulo_norm for p in palavras):
            continue
        if any(p in titulo_norm for p in ignorar):
            continue

        links = await linha.locator("a").evaluate_all("(els) => els.map(a => a.getAttribute('href'))")
        detalhe = ""
        for href in links:
            if href and "ComunicadoDet" in href:
                detalhe = urljoin(base_url, href)
                break

        if not detalhe:
            continue

        try:
            await page_edu.goto(detalhe, wait_until="networkidle")
            await page_edu.wait_for_timeout(2000)

            html = await page_edu.content()

            # Preferência: pegar o texto limpo do model interno do comunicado,
            # para evitar menus e textos laterais do portal.
            texto_pagina = ""
            try:
                model_det = await page_edu.evaluate("() => (typeof model !== 'undefined' ? model : (window.model || null))")
            except Exception:
                model_det = None

            if not model_det:
                try:
                    m_model = re.search(r"var\s+model\s*=\s*(\{[\s\S]*?\});", html)
                    if m_model:
                        model_det = json.loads(m_model.group(1))
                except Exception:
                    model_det = None

            try:
                detalhes = model_det.get("ComunicadoDet") or []
                if detalhes:
                    texto_pagina = texto_visivel_html(detalhes[0].get("texto", ""))
            except Exception:
                texto_pagina = ""

            if not texto_pagina:
                texto_pagina = await page_edu.locator("body").inner_text()

            pdf_urls = re.findall(r'https?://[^"\']+\.pdf', html, flags=re.I)
            pdf_urls = [unescape(u).replace("&amp;", "&") for u in pdf_urls]

            texto_pdf = ""
            pdf_url = pdf_urls[0] if pdf_urls else ""

            if pdf_url and PdfReader:
                try:
                    pasta_tmp = Path(__file__).parent / "_comunicados_pdf"
                    pasta_tmp.mkdir(exist_ok=True)
                    pdf_path = pasta_tmp / f"comunicado_{idx}.pdf"
                    urlretrieve(pdf_url, pdf_path)

                    reader = PdfReader(str(pdf_path))
                    partes = []
                    for p in reader.pages:
                        partes.append(p.extract_text() or "")
                    texto_pdf = limpar_espacos("\n".join(partes))
                except Exception:
                    texto_pdf = ""

            texto_total = limpar_espacos(f"{titulo}. {texto_pagina} {texto_pdf}")
            datas = extrair_datas_futuras_comunicado(texto_total, hoje)
            prazo = datas[0] if datas else parse_data(data_publicacao_txt)

            if not prazo or prazo < hoje:
                continue

            comunicados.append({
                "tipo": "alerta",
                "disciplina": "Comunicado",
                "fonte": "Comunicados",
                "origens": ["Comunicados"],
                "grupo": None,
                "linha_origem": idx,
                "prazo": prazo,
                "prazo_tipo": "data_definida",
                "sem_prazo": False,
                "titulo": titulo,
                "texto": texto_total[:3500],
                "conteudo": texto_total[:3500],
                "conteudo_aula": "",
                "link": detalhe,
                "pdf_url": pdf_url,
            })

        except Exception as e:
            console.print(f"  [yellow]⚠️ Não consegui ler comunicado: {titulo} ({e})[/yellow]")

        await page_edu.goto(URL_COMUNICADOS, wait_until="networkidle")
        await page_edu.wait_for_timeout(800)

    if page_edu is not page:
        await page_edu.close()

    comunicados = dedup_inteligente(comunicados)
    console.print(f"  ✅ {len(comunicados)} comunicado(s) importante(s) encontrado(s)")
    return comunicados


# ── Processamento dos dados ──────────────────────────────────────────────────

def processar_dados(todos_dados: list[dict], hoje: date) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    licoes: list[dict] = []
    provas: list[dict] = []
    alertas: list[dict] = []
    debug: list[dict] = []

    # Remove apenas duplicatas brutas idênticas entre os filhos.
    brutos_unicos = []
    vistos_brutos = set()
    for item in todos_dados:
        chave = (normalizar_chave(item.get("disciplina", "")), normalizar_chave(item.get("texto", "")))
        if chave not in vistos_brutos:
            vistos_brutos.add(chave)
            brutos_unicos.append(item)

    for item in brutos_unicos:
        texto_bruto = limpar_espacos(item.get("texto", ""))
        disciplina_original = item.get("disciplina", "")
        disciplina = normalizar_disciplina(disciplina_original)
        conteudo_aula = extrair_conteudo_aula(texto_bruto, disciplina_original)
        tarefa = extrair_tarefa(texto_bruto)

        dbg = {
            "filho": item.get("filho"),
            "linha": item.get("linha"),
            "data_aula": item.get("data_aula").isoformat() if item.get("data_aula") else None,
            "disciplina_original": item.get("disciplina"),
            "disciplina": disciplina,
            "texto_bruto": texto_bruto,
            "conteudo_aula": conteudo_aula,
            "tarefa_extraida": tarefa,
            "acoes": [],
        }

        if not tarefa:
            dbg["acoes"].append("ignorado_sem_tarefa")
            debug.append(dbg)
            continue

        avaliacao_txt, licao_txt = separar_avaliacao_e_licao(tarefa)

        # Avaliação / prova
        if avaliacao_txt:
            prazo = escolher_prazo(avaliacao_txt, preferir_ultimo=False) or escolher_prazo(tarefa, preferir_ultimo=False)
            cat = tipo_prazo(avaliacao_txt, [prazo] if prazo else [])
            if prazo:
                prova = criar_item_base("prova", disciplina, avaliacao_txt, prazo, item, cat)
                prova["conteudo_aula"] = conteudo_aula
                provas.append(prova)
                dbg["acoes"].append(f"prova_prazo_{prazo.isoformat()}")
            else:
                dbg["acoes"].append("prova_sem_prazo_ignorada")

            if e_alerta(avaliacao_txt) and (prazo or item.get("linha", 9999) <= MAX_LINHA_SEM_PRAZO):
                alerta = criar_item_base("alerta", disciplina, avaliacao_txt, prazo, item, cat)
                alerta["texto"] = avaliacao_txt
                alerta["conteudo_aula"] = conteudo_aula
                alertas.append(alerta)
                dbg["acoes"].append("alerta_criado")

        # Lição normal
        if licao_txt:
            prazo = escolher_prazo(licao_txt, preferir_ultimo=True)
            cat = tipo_prazo(licao_txt, [prazo] if prazo else [])

            # Quando não há data explícita, usamos a grade estimada apenas
            # para saber quando remover da lista.
            # Para os pais, continuará aparecendo como "Próxima aula".
            if not prazo and item.get("data_aula") and dias_grade_para_disciplina(disciplina):
                prazo = calcular_proxima_aula(item.get("data_aula"), disciplina)
                cat = "proxima_aula"

            if not prazo and item.get("linha", 9999) > MAX_LINHA_SEM_PRAZO:
                dbg["acoes"].append(f"licao_sem_prazo_ignorada_linha_{item.get('linha')}")
            else:
                licao = criar_item_base("licao", disciplina, licao_txt, prazo, item, cat)
                licao["conteudo_aula"] = conteudo_aula
                licoes.append(licao)
                dbg["acoes"].append(f"licao_{cat}_{prazo.isoformat() if prazo else 'sem_data'}")

                # Alerta em lição sem transformar automaticamente em prova.
                if e_alerta(licao_txt) and (prazo or item.get("linha", 9999) <= MAX_LINHA_SEM_PRAZO):
                    alerta = criar_item_base("alerta", disciplina, licao_txt, prazo, item, cat)
                    alerta["texto"] = licao_txt
                    alerta["conteudo_aula"] = conteudo_aula
                    alertas.append(alerta)
                    dbg["acoes"].append("alerta_da_licao")

        debug.append(dbg)

    licoes = dedup_inteligente(licoes)
    provas = dedup_inteligente(provas)
    alertas = dedup_inteligente(alertas)

    # Um mesmo texto pode ser útil para classificar a atividade como prova/lição
    # e também conter palavras de alerta ("atenção", "não falte", etc.).
    # Para o site ficar claro, o item fica apenas na categoria principal.
    chaves_principais = {
        (
            normalizar_chave(item.get("disciplina", "")),
            item.get("prazo").isoformat() if item.get("prazo") else item.get("prazo_tipo", "sem_prazo"),
            normalizar_chave(texto_item(item))[:120],
        )
        for item in (licoes + provas)
    }

    alertas_filtrados = []
    for alerta in alertas:
        eh_comunicado = alerta.get("disciplina") == "Comunicado" or alerta.get("fonte") == "Comunicados" or bool(alerta.get("pdf_url"))
        chave = (
            normalizar_chave(alerta.get("disciplina", "")),
            alerta.get("prazo").isoformat() if alerta.get("prazo") else alerta.get("prazo_tipo", "sem_prazo"),
            normalizar_chave(texto_item(alerta))[:120],
        )
        if eh_comunicado or chave not in chaves_principais:
            alertas_filtrados.append(alerta)
    alertas = alertas_filtrados
    alertas = garantir_comunicado_simulado(alertas, hoje)

    # Ordenação final.
    licoes.sort(key=lambda x: (x.get("prazo") is None, x.get("prazo") or date.max, x.get("disciplina", "")))
    provas.sort(key=lambda x: (x.get("prazo") is None, x.get("prazo") or date.max, x.get("disciplina", "")))
    alertas.sort(key=lambda x: (x.get("prazo") is None, x.get("prazo") or date.max, x.get("disciplina", "")))

    return licoes, provas, alertas, debug


# ── Notificação OneSignal ────────────────────────────────────────────────────

async def disparar_notificacao(licoes_fut, provas_fut, alertas, console):
    """Envia notificação push via OneSignal para todos os assinantes."""
    import urllib.request, urllib.error

    hoje = date.today()

    if alertas:
        titulo = f"⚠️ Atenção — {alertas[0]['disciplina']}"
        corpo = limpar_espacos(alertas[0].get("texto", texto_item(alertas[0])))[:100] + "..."
    elif provas_fut:
        p = provas_fut[0]
        if p.get("prazo"):
            dias = (p["prazo"] - hoje).days
            quando = "Hoje!" if dias == 0 else "Amanhã!" if dias == 1 else f"Em {dias} dias"
        else:
            quando = "Sem prazo definido"
        titulo = f"📝 Avaliação de {p['disciplina']}"
        corpo = f"{quando} — {limpar_espacos(p.get('conteudo',''))[:80]}..."
    elif licoes_fut:
        total = len(licoes_fut)
        titulo = f"📚 {total} lição(ões) pendente(s)"
        corpo = f"{licoes_fut[0]['disciplina']}: {limpar_espacos(licoes_fut[0].get('tarefa',''))[:80]}..."
    else:
        console.print("  [dim]Nenhuma novidade para notificar.[/dim]")
        return

    payload = json.dumps({
        "app_id": ONESIGNAL_APP_ID,
        "included_segments": ["All"],
        "headings": {"en": titulo, "pt": titulo},
        "contents": {"en": corpo, "pt": corpo},
        "url": SITE_URL,
        "chrome_web_icon": f"{SITE_URL}/icon.png",
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://onesignal.com/api/v1/notifications",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Basic {ONESIGNAL_API_KEY}"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            resultado = json.loads(resp.read())
            n = resultado.get("recipients", 0)
            console.print(f"  🔔 Notificação enviada para {n} assinante(s)!")
    except urllib.error.HTTPError as e:
        console.print(f"  [yellow]⚠️ Erro ao enviar notificação: {e.read().decode()}[/yellow]")
    except Exception as e:
        console.print(f"  [yellow]⚠️ Erro ao enviar notificação: {e}[/yellow]")


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    from playwright.async_api import async_playwright
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    modo = sys.argv[1] if len(sys.argv) > 1 else "tudo"
    console.print(f"\n[bold cyan]📚 4°A — Eduardo Gomes | Modo: {modo}[/bold cyan]\n")

    hoje = date.today()

    async with async_playwright() as pw:
        navegador = await pw.chromium.launch(headless=not MOSTRAR_NAVEGADOR)
        contexto = await navegador.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
        )
        page = await contexto.new_page()

        ok = await fazer_login(page, console)
        if not ok:
            await navegador.close()
            return

        todos_dados = []
        for filho in FILHOS:
            dados = await buscar_dados_filho(page, contexto, filho, console)
            todos_dados.extend(dados)

        # Comunicados: basta buscar por um filho, pois os comunicados são da mesma turma.
        comunicados_importantes = await buscar_comunicados_importantes(page, contexto, FILHOS[0], console, hoje)

        await navegador.close()

    console.print(f"\n[yellow]🔍 Processando {len(todos_dados)} registros brutos...[/yellow]")
    if not todos_dados:
        console.print("[red]❌ Nenhum registro foi coletado. Mantendo os arquivos atuais e abortando para não apagar a agenda.[/red]")
        return

    licoes, provas, alertas, debug = processar_dados(todos_dados, hoje)

    if comunicados_importantes:
        alertas = dedup_inteligente(alertas + comunicados_importantes)
        alertas.sort(key=lambda x: (x.get("prazo") is None, x.get("prazo") or date.max, x.get("disciplina", "")))

    licoes_fut = [x for x in licoes if prazo_eh_futuro(x, hoje)]
    licoes_hist = [x for x in licoes if prazo_eh_historico(x, hoje)]
    provas_fut = [x for x in provas if prazo_eh_futuro(x, hoje)]
    provas_hist = [x for x in provas if prazo_eh_historico(x, hoje)]
    alertas_fut = [x for x in alertas if prazo_eh_futuro(x, hoje)]

    base = Path(__file__).parent
    (base / "licoes.json").write_text(json.dumps(serial(licoes_fut), ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "provas.json").write_text(json.dumps(serial(provas_fut), ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "alertas.json").write_text(json.dumps(serial(alertas_fut), ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "debug_processamento.json").write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")

    console.print(f"  ✅ {len(licoes_fut)} lições futuras | {len(provas_fut)} provas futuras | {len(alertas_fut)} alertas")
    console.print(f"  📚 Histórico: {len(licoes_hist)} lições | {len(provas_hist)} provas")
    for l in licoes_fut[:20]:
        prazo_txt = l["prazo"].isoformat() if l.get("prazo") else l.get("prazo_tipo", "sem_prazo")
        console.print(f"  [dim]→ {l['disciplina']} | prazo: {prazo_txt}[/dim]")
    console.print()

    # ── Publica site ──────────────────────────────────────────────────────────
    if modo in ("tudo", "site"):
        console.print("[yellow]🌐 Publicando no GitHub Pages...[/yellow]")

        template = Path(__file__).parent / "index_template.html"
        html = template.read_text(encoding="utf-8")

        todos_licoes = serial(licoes_fut) + serial(licoes_hist)
        todos_provas = serial(provas_fut) + serial(provas_hist)

        html = html.replace("DATA_LICOES_PLACEHOLDER", json.dumps(todos_licoes, ensure_ascii=True))
        html = html.replace("DATA_PROVAS_PLACEHOLDER", json.dumps(todos_provas, ensure_ascii=True))
        html = html.replace("DATA_ALERTAS_PLACEHOLDER", json.dumps(serial(alertas_fut), ensure_ascii=True))
        html = html.replace("ATUALIZADO_PLACEHOLDER", datetime.now().strftime("%d/%m/%Y às %H:%M"))

        repo_dir = Path(__file__).parent

        (repo_dir / "index.html").write_text(html, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "commit", "-m", f"Auto {datetime.now().strftime('%d/%m/%Y %H:%M')}"],
            capture_output=True,
            text=True,
        )
        if "nothing to commit" not in result.stdout + result.stderr:
            subprocess.run(["git", "-C", str(repo_dir), "push"], check=True)
            console.print("  ✅ Site publicado!")
            if NOTIFICAR_SITE:
                await disparar_notificacao(licoes_fut, provas_fut, alertas_fut, console)
            else:
                console.print("  [dim]Notificação externa desativada. Use NOTIFICAR_SITE=1 para ativar.[/dim]")
        else:
            console.print("  [dim]Sem mudanças no site.[/dim]")

    # ── Envia WhatsApp ────────────────────────────────────────────────────────
    if modo in ("tudo", "whatsapp", "whatsapp_preview"):
        import pyperclip
        console.print("\n[yellow]📱 Preparando mensagem WhatsApp...[/yellow]")

        cache_path = Path(__file__).parent / "wa_cache.json"
        def cache_key_item(i: dict, campo: str) -> str:
            prazo = i["prazo"].isoformat() if i.get("prazo") else i.get("prazo_tipo", "sem_prazo")
            return f"{i.get('disciplina')}_{prazo}_{normalizar_chave(i.get(campo, ''))[:60]}"

        cache_atual = {
            "licoes": [cache_key_item(l, "tarefa") for l in licoes_fut],
            "provas": [cache_key_item(p, "conteudo") for p in provas_fut],
            "alertas": [cache_key_item(a, "texto") for a in alertas_fut],
        }

        cache_anterior = {}
        if cache_path.exists():
            try:
                cache_anterior = json.loads(cache_path.read_text())
            except Exception:
                pass

        tem_novidade = cache_atual != cache_anterior

        # No modo de prévia, sempre monta a mensagem, mas não atualiza cache.
        # No envio real, o cache só pode ser atualizado depois que a mensagem for enviada.
        if modo == "whatsapp_preview":
            tem_novidade = True

        if not tem_novidade:
            console.print("  [dim]Nenhuma novidade desde o último envio — WhatsApp não disparado.[/dim]")
        else:
            console.print("  ✅ Novidades detectadas — preparando mensagem!")

            # WhatsApp: mensagem pensada para pais.
            # Regra principal: curto, mas nunca superficial.
            # Preserva páginas, exercícios, apostila, workbook, materiais para levar
            # e informações avaliativas importantes.
            LIMITE_COMUNICADO = 520
            LIMITE_ALERTA = 360
            LIMITE_PROVA = 300
            LIMITE_LICAO = 520
            MAX_LICOES = 8
            MAX_PROVAS = 6
            MAX_ALERTAS = 4

            hora_atual = datetime.now().hour

            def nome_curto(d: str) -> str:
                dl = sem_acentos(d or "").lower()
                if "matematica" in dl: return "Matemática"
                if "portugues" in dl or "lingua" in dl: return "Português"
                if "historia" in dl: return "História"
                if "geografia" in dl: return "Geografia"
                if "ciencias" in dl: return "Ciências"
                if "arte" in dl: return "Arte"
                if "fisica" in dl: return "Ed. Física"
                if "tecnologia" in dl: return "Tecnologia"
                if "ingles" in dl:
                    return (d or "Inglês").replace("L.E.M. - Inglês", "Inglês").strip()
                if "projeto" in dl: return "Projeto de Vida"
                if "comunicado" in dl: return "Comunicado"
                return (d or "Geral").split(" ")[0]

            def dias_ate(d: date | None) -> int:
                if not d:
                    return 999
                return (d - date.today()).days

            def dia_semana(d: date) -> str:
                return ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][d.weekday()]

            def data_curta(d: date | None, prazo_tipo: str = "") -> str:
                if prazo_tipo == "proxima_aula":
                    return "Próxima aula"
                if not d:
                    return "Próxima aula"
                diff = dias_ate(d)
                if diff == 0:
                    return "Hoje"
                if diff == 1:
                    return "Amanhã"
                return f"{dia_semana(d)}, {d.strftime('%d/%m')}"

            def resumir(texto: str, limite: int) -> str:
                texto = limpar_espacos(texto)
                if len(texto) <= limite:
                    return texto
                corte = texto[:limite].rstrip()
                if " " in corte:
                    corte = corte.rsplit(" ", 1)[0]
                return corte + "..."

            def chave_msg(item: dict, campo: str = "texto") -> str:
                base = item.get(campo) or item.get("tarefa") or item.get("conteudo") or item.get("texto") or ""
                prazo = item["prazo"].isoformat() if item.get("prazo") else item.get("prazo_tipo", "sem_prazo")
                return f"{nome_curto(item.get('disciplina',''))}|{prazo}|{normalizar_chave(base)[:90]}"

            def dedup_msg(lista: list[dict], campo: str = "texto") -> list[dict]:
                vistos = set()
                saida = []
                for item in lista:
                    k = chave_msg(item, campo)
                    if k in vistos:
                        continue
                    vistos.add(k)
                    saida.append(item)
                return saida

            def ordenar_item(i: dict):
                return (
                    dias_ate(i.get("prazo")),
                    nome_curto(i.get("disciplina", "")),
                    normalizar_chave(i.get("texto") or i.get("tarefa") or i.get("conteudo") or "")[:40],
                )

            def extrair_core_licao(texto: str, limite: int = LIMITE_LICAO) -> str:
                """
                Preserva o core para os pais:
                páginas, exercícios, workbook, planner, materiais, trabalhos e instruções práticas.
                Também trata alguns textos longos da escola de forma mais humana.
                """
                texto = limpar_espacos(texto)
                if not texto:
                    return ""

                texto_norm = sem_acentos(texto).lower()

                # Casos especiais que estavam ficando ruins no WhatsApp.
                if "roda de leitura" in texto_norm and "entrevista" in texto_norm:
                    return resumir(
                        "5ª Proposta da Roda de Leitura no Google Classroom: escolher um personagem da história, elaborar 4 perguntas e criar 4 respostas como se fosse uma entrevista. Pode apresentar em cartaz, vídeo, Canva ou outra ideia criativa. Para: 11/06",
                        limite
                    )

                if "especiarias" in texto_norm and "trabalho avaliativo" in texto_norm:
                    return resumir(
                        "Trazer as imagens das especiarias solicitadas no planner. Elas serão usadas no trabalho avaliativo de História em 26/05. Não falte e não esqueça o material.",
                        limite
                    )

                if len(texto) <= limite:
                    return texto

                partes = re.split(r"(?<=[.!?])\s+|;\s+|\s+-\s+|\n+", texto)
                palavras_fortes = [
                    "p.", "página", "páginas", "pagina", "paginas", "page", "pages",
                    "workbook", "student", "student's book", "apostila", "caderno",
                    "exercício", "exercícios", "exercicio", "exercicios", "ex.", "exs.",
                    "trazer", "finalizar", "terminar", "realizar", "fazer", "ler",
                    "google classroom", "classroom", "planner", "pesquisa", "lapbook",
                    "cartaz", "desenho", "canva", "vídeo", "video", "apresentação",
                    "apresentacao", "material", "folha avulsa", "trabalho avaliativo",
                    "atividade avaliativa", "não falte", "nao falte", "não esqueça", "nao esqueca",
                    "perguntas", "respostas", "personagem", "entrevista"
                ]

                escolhidas = []
                for parte in partes:
                    parte_limpa = limpar_espacos(parte)
                    parte_norm = sem_acentos(parte_limpa).lower()
                    if not parte_limpa:
                        continue
                    if any(chave in parte_norm for chave in palavras_fortes):
                        escolhidas.append(parte_limpa)

                if escolhidas:
                    core = " ".join(escolhidas)
                    return resumir(core, limite)

                return resumir(texto, limite)

            def resumo_comunicado(item: dict) -> str:
                titulo = item.get("titulo") or item.get("conteudo") or item.get("texto") or "Comunicado"
                texto = limpar_espacos(item.get("texto") or item.get("conteudo") or "")

                texto_norm = sem_acentos(texto).lower()
                if "simulado anglo" in texto_norm:
                    linhas_simulado = []
                    linhas_simulado.append("2º Simulado Anglo — 01/06 e 02/06")
                    if "lingua portuguesa" in texto_norm or "língua portuguesa" in texto.lower():
                        linhas_simulado.append("01/06: Português, História e Geografia.")
                    if "matematica" in texto_norm or "matemática" in texto.lower():
                        linhas_simulado.append("02/06: Matemática e Ciências.")
                    if "0 a 1,0" in texto_norm or "0 a 1" in texto_norm:
                        linhas_simulado.append("Vale até 1,0 ponto na média trimestral.")
                    if "nao ha prova substitutiva" in texto_norm or "não há prova substitutiva" in texto.lower():
                        linhas_simulado.append("Não há prova substitutiva.")
                    return "\n  ".join(linhas_simulado)

                return resumir(f"{titulo}. {texto}", LIMITE_COMUNICADO)

            def texto_alerta_whatsapp(item: dict) -> str:
                txt = item.get("texto") or item.get("conteudo") or texto_item(item)
                return resumir(extrair_core_licao(txt, LIMITE_ALERTA), LIMITE_ALERTA)

            def texto_prova_whatsapp(item: dict) -> str:
                txt = item.get("conteudo") or item.get("texto") or texto_item(item)
                return resumir(extrair_core_licao(txt, LIMITE_PROVA), LIMITE_PROVA)

            def limpar_texto_whatsapp(texto: str) -> str:
                """
                Tratamento seguro para WhatsApp.
                Só expande abreviações comuns e remove datas repetidas no final.
                Não inventa informação nova.
                """
                texto = limpar_espacos(texto)
                if not texto:
                    return ""

                # Remove prefixos repetidos.
                texto = re.sub(r"(?i)^tarefa de casa\s*[:\-–]\s*", "", texto).strip()
                texto = re.sub(r"(?i)^homework\s*[:\-–]\s*", "", texto).strip()

                # Expansões seguras de material escolar.
                texto = re.sub(r"(?i)\bWB\b", "Workbook", texto)
                texto = re.sub(r"(?i)\bSB\b", "Student’s Book", texto)

                # p. / pág. / pag. antes de número.
                texto = re.sub(r"(?i)\bpá?g?\.\s*(\d+)", r"página \1", texto)
                texto = re.sub(r"(?i)\bpágina\s+(\d+)\s+a\s+(\d+)", r"páginas \1 a \2", texto)

                # page/pages em inglês.
                texto = re.sub(r"(?i)\bpage\s+(\d+)", r"página \1", texto)
                texto = re.sub(r"(?i)\bpages\s+(\d+)\s+(?:and|e|a)\s+(\d+)", r"páginas \1 a \2", texto)

                # Ajusta listas de páginas: "página 170, 171 e 172" -> "páginas 170, 171 e 172".
                texto = re.sub(
                    r"(?i)\bpágina\s+(\d+)\s*,\s*(\d+)\s+e\s+(\d+)",
                    r"páginas \1, \2 e \3",
                    texto
                )

                # ex. / exs. / ex antes de número.
                texto = re.sub(r"(?i)\bexs?\.\s*(\d+)", r"exercício \1", texto)
                texto = re.sub(r"(?i)\bex\s+(\d+)", r"exercício \1", texto)
                texto = re.sub(r"(?i)\bexercício\s+(\d+)\s+e\s+(\d+)", r"exercícios \1 e \2", texto)
                texto = re.sub(r"(?i)\bexercício\s+(\d+),\s*(\d+)\s+e\s+(\d+)", r"exercícios \1, \2 e \3", texto)

                # Remove data repetida no fim quando já aparece no título da linha.
                texto = re.sub(r"(?i)\s*[-–—]?\s*Para\s*[:\-]?\s*\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\.?\s*$", "", texto).strip()

                # Ajustes leves de início de frase.
                if texto and texto[0].islower():
                    texto = texto[0].upper() + texto[1:]

                return limpar_espacos(texto)


            def texto_licao_whatsapp(item: dict) -> str:
                txt = item.get("tarefa") or item.get("conteudo") or item.get("texto") or ""
                return limpar_texto_whatsapp(extrair_core_licao(txt, LIMITE_LICAO))

            def eh_comunicado(item: dict) -> bool:
                return item.get("disciplina") == "Comunicado" or item.get("fonte") == "Comunicados" or bool(item.get("pdf_url"))

            comunicados_msg = dedup_msg([a for a in alertas_fut if eh_comunicado(a)], "texto")
            alertas_msg = dedup_msg([a for a in alertas_fut if not eh_comunicado(a)], "texto")
            provas_msg = dedup_msg(provas_fut, "conteudo")
            licoes_msg = dedup_msg(licoes_fut, "tarefa")

            # Remove de "Atenção" o que já aparece em "Provas e trabalhos",
            # para não repetir o mesmo aviso duas vezes no WhatsApp.
            chaves_provas = {normalizar_chave(p.get("conteudo") or p.get("texto") or "")[:80] for p in provas_msg}
            alertas_msg = [
                a for a in alertas_msg
                if normalizar_chave(a.get("texto") or a.get("conteudo") or "")[:80] not in chaves_provas
            ]

            # Mantém as lições mesmo quando também viram alerta.
            # Para os pais, a seção "Lições" precisa continuar mostrando o que fazer.

            comunicados_msg = sorted(comunicados_msg, key=ordenar_item)[:3]
            alertas_msg = sorted(alertas_msg, key=ordenar_item)[:MAX_ALERTAS]
            provas_msg = sorted(provas_msg, key=ordenar_item)[:MAX_PROVAS]
            licoes_msg = sorted(licoes_msg, key=ordenar_item)[:MAX_LICOES]

            if hora_atual < 15:
                titulo_msg = "📚 *4ºA — Resumo do Dia*"
                subtitulo = "_Bom dia! Veja o que realmente precisa de atenção._"
            else:
                titulo_msg = "📚 *4ºA — Lembrete da Tarde*"
                subtitulo = "_Boa tarde! Resumo das próximas pendências._"

            linhas = [titulo_msg, subtitulo, ""]

            if comunicados_msg:
                linhas.append("📣 *Comunicado importante*")
                for c in comunicados_msg:
                    prazo = data_curta(c.get("prazo"), c.get("prazo_tipo", ""))
                    resumo = resumo_comunicado(c)
                    linhas.append(f"• *{prazo}*")
                    for linha in resumo.split("\n"):
                        linhas.append(f"  {linha.strip()}")
                    if c.get("pdf_url"):
                        linhas.append("  PDF completo disponível no site.")
                linhas.append("")

            if alertas_msg:
                linhas.append("⚠️ *Atenção importante*")
                for a in alertas_msg:
                    prazo = data_curta(a.get("prazo"), a.get("prazo_tipo", ""))
                    disc = nome_curto(a.get("disciplina", ""))
                    txt = texto_alerta_whatsapp(a)
                    linhas.append(f"• *{disc} — {prazo}*")
                    linhas.append(f"  {txt}")
                linhas.append("")

            if provas_msg:
                linhas.append("📝 *Provas e trabalhos*")
                for p in provas_msg:
                    prazo = data_curta(p.get("prazo"), p.get("prazo_tipo", ""))
                    disc = nome_curto(p.get("disciplina", ""))
                    txt = texto_prova_whatsapp(p)
                    linhas.append(f"• *{disc} — {prazo}*")
                    linhas.append(f"  {txt}")
                linhas.append("")

            linhas.append("📌 *Lições*")
            if licoes_msg:
                for l in licoes_msg:
                    prazo = data_curta(l.get("prazo"), l.get("prazo_tipo", ""))
                    disc = nome_curto(l.get("disciplina", ""))
                    txt = texto_licao_whatsapp(l)
                    linhas.append(f"• *{disc} — {prazo}*")
                    linhas.append(f"  {txt}")
            else:
                linhas.append("✅ Nenhuma lição pendente.")
            linhas.append("")

            total_aberto = len(comunicados_msg) + len(alertas_msg) + len(provas_msg) + len(licoes_msg)
            if total_aberto == 0:
                linhas.append("✅ Nada importante em aberto no momento.")

            linhas.append("🌐 *Ver tudo com detalhes:*")
            linhas.append("https://pallusm.github.io/4a-provas")

            mensagem = "\n".join(linhas)
            pyperclip.copy(mensagem)
            console.print("  ✅ Mensagem formatada!")

            if modo == "whatsapp_preview":
                console.print("\n[bold green]Prévia da mensagem WhatsApp:[/bold green]\n")
                print(mensagem)
                await navegador.close()
                return


        if tem_novidade:
            from playwright.async_api import async_playwright
            console.print("  Abrindo WhatsApp Web...")

            wa_session = Path(__file__).parent / "wa_session"
            wa_session.mkdir(exist_ok=True)

            async with async_playwright() as pw:
                navegador = await pw.chromium.launch_persistent_context(
                    user_data_dir=str(wa_session),
                    headless=False,
                    args=["--start-maximized"],
                )
                page = navegador.pages[0] if navegador.pages else await navegador.new_page()

                await page.goto("https://web.whatsapp.com", wait_until="networkidle")
                await page.wait_for_timeout(3000)

                qr = await page.locator("canvas").count()
                if qr > 0:
                    console.print(Panel("[yellow]📱 Escaneie o QR Code no WhatsApp Web.\nDepois pressione ENTER aqui.[/yellow]"))
                    input()
                    await page.wait_for_timeout(3000)

                console.print("  Aguardando WhatsApp carregar...")
                try:
                    await page.wait_for_selector(
                        "div[aria-label='Lista de conversas'], div[aria-label='Chat list'], #pane-side",
                        timeout=60000,
                    )
                    console.print("  ✅ WhatsApp carregado!")
                except Exception:
                    console.print("  [yellow]⚠️ Timeout na lista — tentando continuar...[/yellow]")

                await page.wait_for_timeout(3000)
                await page.screenshot(path="wa_debug.png")
                console.print("  Buscando grupo...")

                try:
                    grupo_lista = page.locator("span[title*='4°A Fund']").first
                    await grupo_lista.click(timeout=8000)
                    await page.wait_for_timeout(2000)
                    console.print("  ✅ Grupo encontrado na lista!")
                except Exception:
                    console.print("  [dim]Não achou na lista — tentando busca...[/dim]")
                    try:
                        busca = page.locator("div[contenteditable='true'][data-tab='3']").first
                        await busca.click(timeout=8000)
                        await busca.type(WHATSAPP_GRUPO, delay=50)
                        await page.wait_for_timeout(3000)
                        await page.locator(f"span[title='{WHATSAPP_GRUPO}']").first.click(timeout=8000)
                        await page.wait_for_timeout(2000)
                        console.print("  ✅ Grupo encontrado via busca!")
                    except Exception as e:
                        console.print(f"  [red]❌ Grupo não encontrado: {e}[/red]")
                        await page.screenshot(path="wa_debug_grupo.png")
                        await navegador.close()
                        return

                caixa = None
                for sel in [
                    "div[contenteditable='true'][data-tab='10']",
                    "div[contenteditable='true'][title*='mensagem' i]",
                    "div[contenteditable='true'][title*='message' i]",
                    "div[role='textbox'][data-tab='10']",
                    "footer div[contenteditable='true']",
                ]:
                    try:
                        el = page.locator(sel).first
                        await el.click(timeout=5000)
                        caixa = el
                        break
                    except Exception:
                        continue

                if not caixa:
                    console.print("  [red]❌ Caixa de mensagem não encontrada[/red]")
                    await navegador.close()
                    return

                # Colar a mensagem inteira é mais confiável do que digitar
                # caractere por caractere no WhatsApp Web.
                pyperclip.copy(mensagem)
                await page.keyboard.press("Meta+V")
                await page.wait_for_timeout(1000)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(2000)

                console.print("  ✅ Mensagem enviada!")
                cache_path.write_text(json.dumps(cache_atual, ensure_ascii=False))
                await navegador.close()

    console.print(Panel(f"[bold green]✅ Concluído!\n🌐 {SITE_URL}[/bold green]"))


if __name__ == "__main__":
    asyncio.run(main())
