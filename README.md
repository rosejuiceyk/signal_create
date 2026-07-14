# he3-pulse-sim

`he3-pulse-sim` is a staged research software project for simulating He-3 thermal-neutron
detector preamplifier pulses. The current implementation covers **Phase 0 through Phase 3.5 and
the experimental Phase 5 network-A research path**:
packaging, configuration contracts, reproducible truth-event arrivals, a parameterized He-3
spectrum, target peak amplitudes, peak-normalized double-exponential pulses, bounded continuous
waveform blocks, noise/baseline synthesis, clipping, ADC quantization, threshold triggering,
observation-layer dead time, event windows, compressed multi-scale datasets, and a loopback-only
Streamlit interface. Phase 5 adds an isolated likelihood-trained conditional event model, checkpoint
workflow, and exact-baseline comparison without changing the default physical generator. Phase 4
oscilloscope calibration is deferred until measured data are available. The project does not implement
measured electronics recovery, remote Web hosting, network C, or hardware control.

All demonstration values are explicitly labelled `synthetic_demo`. They are not measured or
calibrated detector, preamplifier, digitizer, trigger, or oscilloscope parameters.

操作步骤和每阶段人工审核清单见 [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md)。每个阶段自动
验收完成后仍需用户人工审核，未经明确确认不得进入下一阶段。

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

## Phase 1 truth events

The demonstration configuration contains only explicitly labelled `synthetic_demo` spectrum
and amplitude parameters. Generate a bounded truth-event table or run deterministic arrival
validation with:

```powershell
he3sim simulate-events -c configs/demo_minimal.yaml -o outputs/phase01_events.h5
he3sim validate-arrivals -c configs/demo_minimal.yaml -o outputs/phase01_validation
```

The HDF5 file contains only `/events/true` and `/metadata`. Phase 1 does not create waveform,
ADC, trigger, dead-time, or observed-event datasets. The in-memory event generator rejects
configurations whose expected count exceeds its explicit safety limit.

## Phase 2 continuous waveforms

Generate a block-streamed continuous analog and ADC waveform, then inspect its structure without
loading the sample arrays:

```powershell
he3sim simulate-waveform -c configs/demo_minimal.yaml -o outputs/phase02_waveform.h5
he3sim inspect outputs/phase02_waveform.h5
he3sim plot-waveform outputs/phase02_waveform.h5 -o outputs/phase02_waveform.png
```

`plot-waveform` reads the HDF5 without modifying it and creates a three-panel PNG: a bounded
full-run min/max envelope, an event-centered analog detail, and the corresponding ADC detail.
Truth-event times and any saturated samples are marked for human review.

`direct_sparse` remains the per-event reference implementation. The default `auto` selection uses
`recursive_fixed_tau` when all events share time constants. Both paths apply a per-event discrete
sample-grid correction so an isolated pulse reaches its configured positive `A_peak` magnitude;
polarity remains separate. Waveform output is bounded by `max_samples_per_block` and the CLI's
explicit total-sample safety limit. All values in the demo configuration remain arbitrary
`synthetic_demo` values rather than detector, preamplifier, or ADC specifications.

Successful structural validation does not mean that a provisional configuration is calibrated
or ready for physical simulation. See `docs/model_spec.md` for the scientific contracts.

## Phase 3 observation datasets

Generate the complete truth/waveform/observation hierarchy and validate both ideal dead-time
relations across all thirteen standard rates:

```powershell
he3sim generate-dataset -c configs/demo_minimal.yaml -o outputs/phase03_dataset
he3sim inspect outputs/phase03_dataset/dataset.h5
he3sim validate-physics -c configs/demo_minimal.yaml -o outputs/phase03_validation
```

The event horizon and continuously rendered prefix are separate. Truth rows are appended in exact
homogeneous-Poisson time chunks; waveform, noise, trigger, and compression state remain bounded by
explicit block/sample/event guards. Dead time changes only `/events/observed`; it never deletes
`/events/true` or samples already rendered from in-region truth events.

## Phase 3.5 local Web interface

Launch the loopback-only interactive interface from the project root:

```powershell
he3sim web
```

Open `http://127.0.0.1:8501` and enter the true rate, sample rate, observation time, and seed.
Before generation, the page shows expected events, sample count, sample interval, and an explicit
payload estimate. Each run writes `run_config.yaml`, `waveform.h5`, a two-column
`waveform.csv` (`time_s,voltage_V`), `waveform.png`, and `sampling_info.json` under
`outputs/web_runs/`.

Every input displays its allowed range. The observation-time input additionally shows and enforces
the current dynamic maximum implied by both sample-count and expected-event guards. Web HDF5 files
store both pre-clipping diagnostic voltage and clipped ADC-input voltage. PNG plots prefer the
pre-clipping data, use data-driven y limits, and bound event/saturation markers so dense high-rate
runs remain interpretable without hiding that the configured ADC input is saturated.

The Web layer reuses the existing Phase 1–2 pipeline and enforces interactive event/sample limits.
It does not calibrate detector or electronics parameters, and all demo model values remain
`synthetic_demo`. See `docs/SOFTWARE_USER_MANUAL.md` for software operation and principles, and
`docs/USER_MANUAL.md` for the Phase 3.5 human-review checklist.

## Phase 5 experimental event model

Install the optional ML dependency and train network A without changing the default physical chain:

```powershell
python -m pip install -e ".[ml]"
he3sim train-event-model -c configs/ml_event.yaml
he3sim compare-event-model -c configs/ml_event_eval.yaml -o outputs/phase05_comparison
```

The model is a likelihood-trained conditional marked point process with Poisson counts, positive
mixture intervals, bounded energy densities, and positive amplitude/time-constant densities. It
supports explicit `cpu`, `cuda`, and `auto` modes, checkpoints, seeded inference, and fixed-rate plus
interpolation comparisons. PyTorch remains isolated from the physical core.

Passing the statistical report never promotes the model automatically. The exact Poisson +
parametric-spectrum generator remains the default, and every Phase 5 checkpoint/model card is
marked `experimental`, especially while Phase 4 real-data calibration is deferred.
