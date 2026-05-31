# 4a-provas

Projeto único da agenda do 4ºA.

Use esta pasta como fonte oficial:

```bash
/Users/pallusmassucci/Desktop/provas-4a-site
```

A pasta antiga `/Users/pallusmassucci/Desktop/provas-4a` deve ser tratada como legado enquanto a migração é conferida.

## Arquivos principais

- `4a_automatico.py`: busca dados da escola, processa lições/provas/alertas e publica o site.
- `index_template.html`: modelo usado para gerar o HTML final.
- `preview_site.py`: gera `preview.html` com os JSONs locais.
- `index.html`: página publicada no GitHub Pages.
- `licoes.json`, `provas.json`, `alertas.json`: dados usados pelo preview.
- `atualizar_site.sh`: gera preview, copia para `index.html`, faz commit e push.

## Configurar Python

Para buscar dados da escola nesta pasta nova, crie um ambiente local uma vez:

```bash
cd /Users/pallusmassucci/Desktop/provas-4a-site
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

Antes de buscar dados novos da escola, crie um arquivo `.env` local com suas credenciais:

```bash
CLASSAPP_EMAIL=seu-email
CLASSAPP_SENHA=sua-senha
```

## Atualizar site

Para publicar usando os dados locais já existentes:

```bash
cd /Users/pallusmassucci/Desktop/provas-4a-site
./atualizar_site.sh
```

Para buscar dados novos da escola e publicar:

```bash
cd /Users/pallusmassucci/Desktop/provas-4a-site
.venv/bin/python3 4a_automatico.py site
```

Não rode envio real de WhatsApp sem confirmar antes.
