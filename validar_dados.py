import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).parent


def limpar(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def normalizar(texto):
    texto = unicodedata.normalize("NFD", texto or "")
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^a-z0-9]+", " ", texto.lower())
    return limpar(texto)


def carregar(nome):
    caminho = BASE / nome
    if not caminho.exists():
        raise SystemExit(f"ERRO: arquivo ausente: {nome}")
    return json.loads(caminho.read_text(encoding="utf-8"))


def texto_item(item):
    return item.get("tarefa") or item.get("conteudo") or item.get("texto") or ""


def chave_item(item, campo):
    texto = item.get(campo) or texto_item(item)
    prazo = item.get("prazo") or item.get("prazo_tipo") or "sem_prazo"
    return (
        normalizar(item.get("disciplina", "")),
        prazo,
        normalizar(texto)[:120],
    )


def parse_data(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return None


def main():
    hoje = date.today()
    licoes = carregar("licoes.json")
    provas = carregar("provas.json")
    alertas = carregar("alertas.json")
    erros = []
    avisos = []

    conjuntos = [
        ("licoes.json", "tarefa", licoes),
        ("provas.json", "conteudo", provas),
        ("alertas.json", "texto", alertas),
    ]

    vistos = {}
    for nome, campo, itens in conjuntos:
        for idx, item in enumerate(itens, start=1):
            chave = chave_item(item, campo)
            if chave in vistos:
                erros.append(f"Duplicata entre {vistos[chave]} e {nome}#{idx}")
            else:
                vistos[chave] = f"{nome}#{idx}"

            prazo = parse_data(item.get("prazo"))
            if item.get("tipo") in ("prova", "avaliacao") and not prazo:
                erros.append(f"Prova sem prazo em {nome}#{idx}")
            if prazo and prazo < hoje and item.get("disciplina") == "Comunicado":
                avisos.append(f"Comunicado vencido ainda nos dados: {nome}#{idx}")

    texto_alertas = normalizar(" ".join(
        f"{a.get('titulo', '')} {a.get('texto', '')} {a.get('conteudo', '')}" for a in alertas
    ))
    if "simulado anglo" not in texto_alertas:
        erros.append("Comunicado do Simulado Anglo ausente em alertas.json")

    preview = BASE / "preview.html"
    if preview.exists():
        html = preview.read_text(encoding="utf-8")
        for placeholder in [
            "DATA_LICOES_PLACEHOLDER",
            "DATA_PROVAS_PLACEHOLDER",
            "DATA_ALERTAS_PLACEHOLDER",
            "ATUALIZADO_PLACEHOLDER",
        ]:
            if placeholder in html:
                erros.append(f"Placeholder ainda presente no preview: {placeholder}")
        if "2º Simulado Anglo" not in html and "2\u00ba Simulado Anglo" not in html:
            erros.append("Preview sem o comunicado do Simulado Anglo")
    else:
        avisos.append("preview.html ainda não foi gerado")

    print("Validação da agenda 4ºA")
    print(f"Lições: {len(licoes)} | Provas: {len(provas)} | Comunicados/alertas: {len(alertas)}")

    if avisos:
        print("\nAvisos:")
        for aviso in avisos:
            print(f"- {aviso}")

    if erros:
        print("\nErros:")
        for erro in erros:
            print(f"- {erro}")
        raise SystemExit(1)

    print("\nOK: dados consistentes para preview/publicação.")


if __name__ == "__main__":
    main()
