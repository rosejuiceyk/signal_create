# he3-pulse-sim

`he3-pulse-sim` is a staged research package for reproducible He-3 thermal-neutron
detector signal simulation. The active codebase contains the reviewed Phase 0–3
physical pipeline, the reviewed Phase A pure-prompt correlated-arrival engine, and the Phase B
  pulse-counting noise analysis awaiting human review,
and the read-only Phase 4Q acquisition-qualification tools:

- homogeneous-Poisson baseline or source-driven pure-prompt branching-chain arrivals;
- optional event lineage sidecars plus a parameterized He-3 spectrum;
- peak-normalized double-exponential pulses and continuous waveform synthesis;
- baseline/noise, clipping, ADC quantization, triggering, and observation-layer dead time;
- compressed HDF5 datasets, inspection, plotting, and deterministic validation;
- reusable Phase A Matplotlib figures plus an offline PNG/HTML validation report;
- Rossi-alpha, Feynman-alpha, and PSD alpha recovery with bootstrap uncertainty and static reports;
- read-only acquisition hashing, provenance checks, sampling-axis evidence, and event QC.

The former local Web interface and the Phase 5/6 machine-learning routes are archived under
[`archive/`](archive/). They are no longer installed, imported, exposed by the CLI, or included in
the active test suite. The project mainline now targets a correlated-neutron-noise signal-level
digital twin; see [`docs/ROADMAP_v2.md`](docs/ROADMAP_v2.md). Phase B now implements only
  pure-prompt pulse-counting inversion; delayed neutrons and continuous-signal inversion remain
  future phases.

All demonstration values are labelled `synthetic_demo`. They are not measured or calibrated
detector, preamplifier, digitizer, trigger, or oscilloscope parameters.

操作步骤和人工审核清单见 [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md)，软件接口与数据格式见
[`docs/SOFTWARE_USER_MANUAL.md`](docs/SOFTWARE_USER_MANUAL.md)。

## Environment and validation

The canonical environment is Conda `signal_create` with Python 3.11 or newer:

```powershell
conda env update -n signal_create -f environment.yml --prune
conda activate signal_create
python -m pip install -e ".[dev]"
```

Run the repository checks with:

```powershell
python -m pytest -q
python -m ruff format --check .
python -m ruff check .
python -m mypy src
python -m pip check
git diff --check
```

## Configuration and truth events

```powershell
he3sim validate-config -c configs/demo_minimal.yaml
he3sim simulate-events -c configs/demo_minimal.yaml -o outputs/phase01_events.h5
he3sim simulate-events --source-model correlated -c configs/demo_minimal.yaml -o outputs/phaseA_events.h5
he3sim validate-arrivals -c configs/demo_minimal.yaml -o outputs/phase01_validation
he3sim validate-correlated -c configs/demo_minimal.yaml -o outputs/phaseA_report
he3sim analyze-noise -c configs/demo_minimal.yaml -o outputs/phaseB_noise
he3sim validate-alpha-recovery -c configs/demo_minimal.yaml -o outputs/phaseB_recovery
```

The truth-event HDF5 contains `/events/true` and `/metadata`; correlated outputs additionally contain
`/events/lineage` with `event_id`, `chain_id`, and `generation`. The in-memory generator enforces
explicit expected-event, chain-generation, reaction-count, and realized-event limits.
The Phase A report writes six PNG figures, an offline HTML report, and machine-readable metrics JSON;
it does not provide an interactive dashboard.
The Phase B validation report writes seven Chinese-annotated PNG figures, an offline HTML report,
and JSON metrics. Scientific names such as Rossi-alpha, Feynman-alpha, PSD, and Y-infinity remain
unchanged; no interactive dashboard is included.

## Continuous waveforms

```powershell
he3sim simulate-waveform -c configs/demo_minimal.yaml -o outputs/phase02_waveform.h5
he3sim inspect outputs/phase02_waveform.h5
he3sim plot-waveform outputs/phase02_waveform.h5 -o outputs/phase02_waveform.png
```

`direct_sparse` remains the reference renderer. The optimized fixed-time-constant path preserves
block-boundary state and is checked against the reference implementation.

## Observation datasets

```powershell
he3sim generate-dataset -c configs/demo_minimal.yaml -o outputs/phase03_dataset
he3sim inspect outputs/phase03_dataset/dataset.h5
he3sim validate-physics -c configs/demo_minimal.yaml -o outputs/phase03_validation
```

Dead time changes only `/events/observed`; it never removes truth events or already-rendered waveform
samples.

## Read-only acquisition qualification

```powershell
he3sim qualify-acquisition --input "C:\path\to\DAQ" --profile configs/acquisition_profiles/dt5790_run3.yaml -o outputs/phase04q
```

The default scan bounds event rows per run while hashing every discovered source file. Raw acquisition
directories remain read-only, and this command does not calibrate energy, fit pulses, or deduplicate
waveforms.
