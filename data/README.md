# Synthetic data

All data produced here is synthetic. Generate a reproducible raw dataset and
ground-truth labels with:

```bash
python -m data.generators.generate_all --seed 42 --size 100 --out data/processed
python -m data.generators.make_splits --seed 42 --root data/processed
```

`generate_all` writes `raw/{resources,crew,availability,weather,constraints}.csv`
and `labels.parquet`. `make_splits` writes chronological `train`, `val`, and `test`
files for Ditto pairs, temporal graph records, and forecast resource histories
under `data/processed/splits/`. Install `pyarrow` (included in project dependencies)
for Parquet read/write support. Repeating the commands with the same seed and
configuration produces the same values and partition assignments.

The checked-in Ditto config targets the generated SIH-scale example under
`data/processed/sih_product/`. To train that model, install `ml/requirements.txt`,
run the generator and split commands with `--out data/processed/sih_product`, then:

```bash
python -m ml.entity_matching.train --config ml/entity_matching/configs/ditto.yaml --seed 2026
```
