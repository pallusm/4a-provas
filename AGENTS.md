# Regras do projeto

Esta pasta é a fonte oficial do projeto:

`/Users/pallusmassucci/Desktop/provas-4a-site`

A pasta `/Users/pallusmassucci/Desktop/provas-4a` é legado e não deve receber novas mudanças durante a migração.

## Fluxo seguro

1. Trabalhe em escopo pequeno.
2. Antes de alterar arquivos, explique o plano curto e os arquivos envolvidos.
3. Não envie WhatsApp real sem confirmação explícita.
4. Para site, valide com `python3 preview_site.py`.
5. Para Python, valide com `python3 -m py_compile 4a_automatico.py`.
6. Não instale dependências sem confirmação.
7. Nunca commitar credenciais; use `.env` local e mantenha `.env.example` sem dados reais.

## Comandos úteis

Gerar preview local:

```bash
python3 preview_site.py
```

Publicar usando dados locais:

```bash
./atualizar_site.sh
```

Buscar dados novos da escola e publicar:

```bash
python3 4a_automatico.py site
```
