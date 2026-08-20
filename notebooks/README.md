# Cadernos

Os cadernos leem `config/`, `data/` e `scripts/` por caminho relativo à raiz. Execute-os de
dentro do repositório clonado; um `.ipynb` isolado não funciona.

```bash
conda env create -f environment.yml && conda activate worcap-endmembers
jupyter lab
```

## Qual usar

| Caderno | Para quê |
| --- | --- |
| [`02_verificar_resultados_do_artigo.ipynb`](02_verificar_resultados_do_artigo.ipynb) | Conferir os números do artigo com o código visível célula a célula. É o equivalente do `verificar.py` da raiz, em formato de leitura. |
| [`01_reproduzir_ppi_e_paineis.ipynb`](01_reproduzir_ppi_e_paineis.ipynb) | Reproduzir os candidatos PPI e os painéis usando o pacote `worcap_endmembers`. |
| [`standalone/`](standalone/README.md) | Percorrer o método inteiro — amostra, WTSS, PPI, painéis, revisão, STL e clima — com todo o código nas próprias células. Seis cadernos em ordem. |

Para apenas conferir se o artigo é reproduzível, `python verificar.py` na raiz resolve em um
comando.

## Parâmetros congelados

| Parâmetro | Valor |
| --- | --- |
| Pixels sistemáticos por classe | 1.000 |
| Candidatos por classe e data | 4 |
| Projeções PPI | 10.000 |
| Semente | 13 |
| Pool de candidatos | todos com escore positivo |
| Separação angular mínima (SAM) | 2,0° |

## Saídas

`outputs/verificacao/` e `outputs/standalone/`, ambos fora do controle de versão. Os dados em
`data/` não são alterados.
