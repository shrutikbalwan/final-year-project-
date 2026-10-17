# Python dependency lock

The primary Windows development/test environment used CPython 3.13.15. The original requirements remain range-constrained inputs: `requirements-dev.txt` includes core dependencies through `requirements.txt`, ML packages through `requirements-ml.txt`, plus test packages. Computer-vision YOLO (`requirements-cv.txt`) and AWS (`requirements-aws.txt`) remain optional profiles and are not included in the development lock. The working environment had boto3 installed separately; this lock deliberately does not make AWS a default dependency.

`requirements-dev-py313-win.lock` is a version-exact lock for the declared dev/ML dependency graph, compiled with pip-tools 7.6.2 while constraining resolution to the versions already installed in the passing CPython 3.13.15 Windows environment. This avoided upgrading packages just to create a lock. Requirements source files and React/Flutter lockfiles were left unchanged.

## Fresh environment on Windows

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements-dev-py313-win.lock
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

The lock targets Windows with CPython 3.13 and includes the core, ML, and test dependency closure. Optional YOLO/CV and AWS dependencies require separate installs from `requirements-cv.txt` and `requirements-aws.txt`; they do not have exact locks in this change.

## Regenerate after a reviewed dependency change

Do not run an unconstrained upgrade to refresh the lock. First install and test the intended source requirement set in a clean environment, then compile while using that environment's installed versions as constraints. Keep the freeze file outside the repository because it can include unrelated local packages.

```powershell
py -3.13 -m venv .venv-locktools
.\.venv-locktools\Scripts\python.exe -m pip install pip-tools==7.6.2
$constraints = Join-Path $env:TEMP "helmet-requirements-constraints.txt"
.\.venv\Scripts\python.exe -m pip freeze --exclude-editable | Set-Content -Encoding ascii $constraints
.\.venv-locktools\Scripts\pip-compile.exe `
  --no-header --no-annotate --no-emit-options --no-emit-index-url --no-strip-extras `
  --constraint $constraints `
  --output-file .\requirements-dev-py313-win.lock `
  .\requirements-dev.txt
Remove-Item -LiteralPath $constraints
```

Review lock changes, run the full suite and `pip check`, and confirm the lock contains no unrelated optional packages before accepting an update.

## Reproducibility boundaries

This lock pins package versions, not downloaded wheel hashes. It is specific to the Windows CPython 3.13 environment; native packages such as OpenCV, NumPy and scikit-learn distribute platform-specific wheels. Python patch version, architecture, pip behavior, package index availability, and wheel artifacts still matter. A separate lock should be generated and validated for other Python versions or operating systems. The broad source constraints remain unchanged so existing optional profiles keep their declared dependency ranges.

