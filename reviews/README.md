# Avaliações

Os CSVs exportados pelos painéis devem ser armazenados por classe:

```text
reviews/incoming/class_01/
reviews/incoming/class_02/
reviews/incoming/class_09/
reviews/incoming/class_10/
reviews/incoming/class_11/
```

Validação de um arquivo:

```bash
python -m worcap_endmembers validate-reviews reviews/incoming/class_01/arquivo.csv
```

Validação de todos os arquivos recebidos:

```bash
python -m worcap_endmembers validate-all-reviews
```

Fusão dos arquivos válidos:

```bash
python -m worcap_endmembers merge-reviews --output reviews/validated/reviews_consolidadas.parquet
```

O processo de fusão preserva a origem de cada arquivo e bloqueia combinações duplicadas de `classe × data`.

