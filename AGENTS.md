# Regras do projeto

Esta pasta é a fonte oficial do projeto:

`/Users/pallusmassucci/Desktop/provas-4a-site`

A pasta `/Users/pallusmassucci/Desktop/provas-4a` é legado. Não use nem altere essa pasta para novas mudanças.

Os LaunchAgents do macOS devem apontar para esta pasta oficial:

- `/Users/pallusmassucci/Desktop/provas-4a-site/run_site.sh`
- `/Users/pallusmassucci/Desktop/provas-4a-site/run_whatsapp.sh`

## Fluxo seguro

1. Trabalhe em escopo pequeno.
2. Antes de alterar arquivos, explique o plano curto e os arquivos envolvidos.
3. Prefira `.venv/bin/python3` quando a pasta `.venv` existir; caso contrário, use `python3`.
4. Não envie WhatsApp real sem confirmação explícita; envio real exige `ENVIAR_WHATSAPP=1` no `.env`.
5. Não dispare notificações externas sem confirmação explícita; OneSignal exige `NOTIFICAR_SITE=1`, `ONESIGNAL_APP_ID` e `ONESIGNAL_API_KEY` no `.env`.
6. Para site, valide com `.venv/bin/python3 preview_site.py` e, quando mexer nos dados ou na geração, também rode `.venv/bin/python3 validar_dados.py`.
7. Para Python, valide com `.venv/bin/python3 -m py_compile 4a_automatico.py`.
8. Não instale dependências sem confirmação.
9. Nunca commitar credenciais; use `.env` local e mantenha `.env.example` sem dados reais.

## Comandos úteis

Gerar preview local:

```bash
.venv/bin/python3 preview_site.py
```

Validar dados e preview:

```bash
.venv/bin/python3 validar_dados.py
```

Publicar usando dados locais:

```bash
./atualizar_site.sh
```

Buscar dados novos da escola e publicar:

```bash
.venv/bin/python3 4a_automatico.py site
```

Testar WhatsApp sem envio:

```bash
.venv/bin/python3 whatsapp_mock.py
```

Prévia integrada do WhatsApp sem envio:

```bash
.venv/bin/python3 4a_automatico.py whatsapp_preview
```
