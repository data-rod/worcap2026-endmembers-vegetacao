# Cadernos técnicos independentes

Estes cadernos apresentam o fluxo científico com o código visível nas próprias células. Os cadernos não importam o pacote Python local e podem ser executados somente com as bibliotecas científicas declaradas em `requirements.txt` ou `environment.yml`.

## Ordem de execução

1. `01_amostra_e_series_wtss.ipynb` — audita a amostra sistemática, as distâncias espaciais, o GeoPackage e as séries WTSS; também documenta uma consulta remota opcional.
2. `02_reproduzir_candidatos_ppi.ipynb` — implementa o PPI e o SAM, processa as cinco classes e compara os candidatos com a versão publicada.
3. `03_reconstruir_paineis.ipynb` — gera os cinco painéis HTML offline a partir dos candidatos e das séries WTSS.
4. `04_validar_e_consolidar_revisoes.ipynb` — valida os CSVs dos avaliadores, consolida as decisões e constrói a série espectral representativa quando houver revisões completas.
5. `05_serie_espectral_e_stl.ipynb` — aplica a regra do avaliador principal, completa a grade temporal, calcula índices auxiliares e decompõe as dez bandas por STL nas classes elegíveis.

Os cadernos localizam automaticamente a raiz do repositório. É possível iniciá-los a partir desta pasta ou da raiz.

## Execução

Crie e ative um ambiente Python 3.11 ou superior. Em seguida, instale as dependências gerais:

```bash
python -m pip install -r requirements.txt
```

Para auditar também o GeoPackage, instale `geopandas`. Ele já está incluído em `environment.yml` para ambientes Conda.

Inicie o Jupyter Lab:

```bash
jupyter lab
```

As saídas reproduzidas são gravadas em `outputs/standalone/`, diretório ignorado pelo controle de versão. Os dados científicos de referência permanecem inalterados em `data/`.

## Consulta remota

O primeiro caderno mantém `EXECUTAR_NOVA_CONSULTA = False`. Alterar esse valor para `True` consulta apenas o primeiro ponto e demonstra a interface WTSS. Os 920.000 registros usados no estudo já estão em `data/wtss/`; portanto, a reprodução do PPI e dos painéis não exige acesso à rede.
