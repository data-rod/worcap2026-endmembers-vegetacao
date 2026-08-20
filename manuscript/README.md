# Artigo curto — WORCAP 2026

`artigo.pdf` é a versão submetida, em cinco páginas. O texto é redigido em Word; não há fonte
LaTeX neste repositório.

## Arquivos

- `artigo.pdf` — versão submetida;
- `references.bib` — as doze referências citadas, com DOI quando existe;
- `auditoria_referencias.csv` — autoria, DOI e função de cada fonte;
- `figures/figura_01_decomposicao_espectrotemporal.pdf` e `.png` — Figura 1 do artigo;

Boardman (1993) e Boardman, Kruse e Green (1995) não têm DOI: são *summaries* de workshop do
JPL. Volume e páginas foram conferidos nos originais.

## Regerar a Figura 1 e as métricas

```bash
python scripts/build_spectrotemporal_outputs.py --output-dir manuscript/figures
```

Para conferir os valores contra o artigo, use `python verificar.py` na raiz.

## Submissão

Artigo curto, até cinco páginas, modelo oficial da SBC. Prazo: 18 de agosto de 2026.
Fonte: https://www.gov.br/inpe/pt-br/eventos/worcap-2026/submissoes

Pendente para a versão final: incluir a declaração de disponibilidade de dados e código com o
identificador do depósito.
