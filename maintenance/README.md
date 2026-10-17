# CI maintenance checks

These focused checks run in the separate **CI tooling checks** workflow when a
push or pull request changes CI workflows, actions, scripts, Linux image
configuration, or this directory. They are separate from the product test
suite and CI build gates. Run them locally with:

```sh
python -m pip install -r maintenance/requirements.txt
python -m pytest -q maintenance
```

The suite checks Python helpers and the workflow's declared structure. Some
release and image cases use synthetic artifacts or command stubs. Passing these
checks does not verify GitHub-hosted expression evaluation, event context,
permissions enforcement, runner scheduling, or actual hosted builds.
