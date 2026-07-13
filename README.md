# he3-pulse-sim

`he3-pulse-sim` is a staged research software project for simulating He-3 thermal-neutron
detector preamplifier pulses. The current implementation is **Phase 0 only**: packaging,
configuration contracts, data types, reproducible randomness, interface stubs, and the CLI
foundation. It does not generate physical events or waveforms.

All demonstration values are explicitly labelled `synthetic_demo`. They are not measured or
calibrated detector, preamplifier, digitizer, trigger, or oscilloscope parameters.

## Conda environment and install

The canonical project environment is the Conda environment named `signal_create`, using
Python 3.11 or newer. From an Anaconda PowerShell prompt:

```powershell
conda activate signal_create
python --version
python -m pip install -e ".[dev]"
```

The committed `environment.yml` records the same environment contract. To create or reconcile
the environment on another machine:

```powershell
conda env update -n signal_create -f environment.yml --prune
conda activate signal_create
```

Do not install this project's Pydantic and Rich dependencies into a shared Anaconda base
environment; other scientific tools may require incompatible major versions.

For validation inside `signal_create`:

```powershell
python -m pytest -q
python -m ruff format --check .
python -m ruff check .
python -m mypy src
```

## Validate configuration

```powershell
he3sim validate-config -c configs/demo_minimal.yaml
he3sim validate-config -c configs/provisional_he3.yaml
```

Successful structural validation does not mean that a provisional configuration is calibrated
or ready for physical simulation. See `docs/model_spec.md` for the scientific contracts.
