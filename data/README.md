# data/

Large datasets are tracked with DVC (`dvc add data/external/<file>`), never committed
to git. The only configured remote is a local directory (`.dvc/storage`, git-ignored).
No cloud remote or credentials are configured; add one locally with
`dvc remote add --local ...` (stored in `.dvc/config.local`, which is git-ignored).
