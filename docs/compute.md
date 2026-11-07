# Compute backends

`groundtruth.compute.map_placebos(fn, items, backend, seed)` runs `fn(item, item_seed)`
over items on a serial, process-pool (`"process"`), `"dask"` or `"ray"` backend. Results
keep input order and per-item seeds depend only on `(seed, index)`, so output is identical
across backends. `fn` must be a picklable top-level function for process/dask/ray.

Optional installs: `pip install "dask[distributed]"` or `pip install ray`; a missing
package raises an `ImportError` naming it.

## Plugging into the placebo suite

`engine/uncertainty/placebo.py::in_space_placebo` refits `fit_synthetic_control` once per
donor unit in a loop. Engine files are unchanged; to parallelise, wrap one placebo fit:

```python
from groundtruth.compute import map_placebos

def fit_one(unit_index: int, seed: int) -> float:
    ...  # build the donor pool excluding the treated unit, fit, return the RMSPE ratio

ratios = map_placebos(fit_one, placebo_indices, backend="process", seed=request_seed)
```

Then compute the p-value from `ratios` and the observed statistic as `PlaceboResult` does.
For process backends, keep large arrays in module-level state or files rather than in
per-item arguments.
