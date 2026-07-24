"""Phase 1 orchestration for truth-event generation without waveform synthesis."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel

from he3sim.config import (
    He3SimConfig,
    ObservationMode,
    ParameterStatus,
    ParameterValue,
    SourceModelKind,
)
from he3sim.physics.amplitude import LinearAmplitudeMapper
from he3sim.physics.arrivals import ArrivalAlgorithm, arrival_generator_for
from he3sim.physics.chains import BranchingChainGenerator
from he3sim.physics.pulse_parameters import FixedPulseParameterProvider
from he3sim.physics.rate_profiles import ConstantRateProfile
from he3sim.physics.source_model import PromptSourceModel
from he3sim.physics.spectra import ParametricHe3Spectrum
from he3sim.random import RandomContext
from he3sim.types import EVENT_LINEAGE_DTYPE, TRUE_EVENT_DTYPE

DEFAULT_MAX_EXPECTED_EVENTS = 1_000_000
UNASSIGNED_INDEX = -1


@dataclass(frozen=True, slots=True)
class TrueEventSimulation:
    """Generated truth-event table and the metadata needed to persist it."""

    events: npt.NDArray[np.void]
    duration_s: float
    true_rate_cps: float
    seed: int
    parameter_status: ParameterStatus
    arrival_algorithm: ArrivalAlgorithm
    source_model: SourceModelKind = SourceModelKind.POISSON
    lineage: npt.NDArray[np.void] | None = None
    derived_source_metadata: dict[str, float] | None = None


def _required_value(parameter: ParameterValue[float] | ParameterValue[int], name: str) -> float:
    """Return a required run value or fail explicitly."""
    if parameter.value is None:
        raise ValueError(f"{name} requires an explicit value")
    return float(parameter.value)


def resolve_source_model_kind(
    config: He3SimConfig,
    override: SourceModelKind | None = None,
) -> SourceModelKind:
    """Resolve the optional command-line source-model override."""
    kind = override or config.source_model.kind
    if kind is SourceModelKind.CORRELATED and not config.source_model.has_correlated_parameters():
        raise ValueError("correlated source model requires source_model physical parameters")
    return kind


def resolve_true_rate_cps(
    config: He3SimConfig,
    source_model: SourceModelKind | None = None,
) -> float:
    """Return the canonical expected detection rate for the selected source model."""
    kind = resolve_source_model_kind(config, source_model)
    configured = _required_value(config.simulation.true_rate_cps, "true_rate_cps")
    if kind is SourceModelKind.POISSON:
        return configured
    model = PromptSourceModel.from_config(config.source_model)
    if not np.isclose(
        configured,
        model.expected_detected_rate_cps,
        rtol=1.0e-9,
        atol=1.0e-12,
    ):
        raise ValueError("simulation.true_rate_cps must equal source_model S*epsilon/(1-k_eff)")
    return model.expected_detected_rate_cps


def resolve_duration_s(
    config: He3SimConfig,
    source_model: SourceModelKind | None = None,
) -> float:
    """Resolve a fixed duration or expected target-count observation horizon."""
    rate_cps = resolve_true_rate_cps(config, source_model)
    if config.observation.mode is ObservationMode.FIXED_DURATION:
        if config.observation.duration_s is None:
            raise ValueError("fixed_duration mode requires duration_s")
        duration_s = _required_value(config.observation.duration_s, "duration_s")
    else:
        if config.observation.target_event_count is None:
            raise ValueError("target_event_count mode requires target_event_count")
        target_count = _required_value(config.observation.target_event_count, "target_event_count")
        duration_s = target_count / rate_cps
    if config.observation.min_duration_s is not None:
        duration_s = max(
            duration_s,
            _required_value(config.observation.min_duration_s, "min_duration_s"),
        )
    if config.observation.max_duration_s is not None:
        duration_s = min(
            duration_s,
            _required_value(config.observation.max_duration_s, "max_duration_s"),
        )
    return duration_s


def _parameter_statuses(model: BaseModel) -> list[ParameterStatus]:
    """Collect parameter evidence states from one flat configuration section."""
    statuses: list[ParameterStatus] = []
    for field_name in type(model).model_fields:
        value = getattr(model, field_name)
        if isinstance(value, ParameterValue):
            statuses.append(value.status)
    return statuses


def event_parameter_status(
    config: He3SimConfig,
    source_model: SourceModelKind | None = None,
) -> ParameterStatus:
    """Return the least-validated status among parameters used by Phase 1."""
    kind = resolve_source_model_kind(config, source_model)
    statuses = [
        config.metadata.seed.status,
        *_parameter_statuses(config.simulation),
        *_parameter_statuses(config.observation),
        *_parameter_statuses(config.spectrum),
        *_parameter_statuses(config.amplitude),
        *_parameter_statuses(config.pulse_shape),
    ]
    if kind is SourceModelKind.CORRELATED:
        statuses.extend(_parameter_statuses(config.source_model))
    if ParameterStatus.SYNTHETIC_DEMO in statuses:
        return ParameterStatus.SYNTHETIC_DEMO
    if ParameterStatus.PROVISIONAL in statuses:
        return ParameterStatus.PROVISIONAL
    return ParameterStatus.VALIDATED


def simulate_true_events(
    config: He3SimConfig,
    algorithm: ArrivalAlgorithm = ArrivalAlgorithm.POISSON_UNIFORM,
    max_expected_events: int = DEFAULT_MAX_EXPECTED_EVENTS,
    source_model: SourceModelKind | None = None,
) -> TrueEventSimulation:
    """Generate a bounded in-memory truth-event table without any waveform calculation."""
    if max_expected_events <= 0:
        raise ValueError("max_expected_events must be positive")
    source_kind = resolve_source_model_kind(config, source_model)
    rate_cps = resolve_true_rate_cps(config, source_kind)
    duration_s = resolve_duration_s(config, source_kind)
    expected_events = rate_cps * duration_s
    if expected_events > max_expected_events:
        raise ValueError(
            f"expected event count {expected_events:.0f} exceeds the in-memory limit "
            f"{max_expected_events}; shorten the horizon or raise the explicit limit"
        )
    if config.metadata.seed.value is None:
        raise ValueError("seed requires an explicit value")
    seed = config.metadata.seed.value

    arrival_rng, spectrum_rng, amplitude_rng, pulse_parameter_rng = RandomContext(seed).spawn(4)
    arrival_generator = arrival_generator_for(algorithm)
    lineage: npt.NDArray[np.void] | None = None
    derived_source_metadata: dict[str, float] | None = None
    if source_kind is SourceModelKind.CORRELATED:
        prompt_model = PromptSourceModel.from_config(config.source_model)
        expected_reactions = prompt_model.source_rate_cps * duration_s / (1.0 - prompt_model.k_eff)
        if expected_reactions > config.source_model.max_total_reactions:
            raise ValueError(
                f"expected branching reactions {expected_reactions:.0f} exceed "
                f"source_model.max_total_reactions={config.source_model.max_total_reactions}"
            )
        profile = ConstantRateProfile(prompt_model.source_rate_cps)
        chain_generator = BranchingChainGenerator(
            prompt_model,
            source_generator=arrival_generator,
            max_events=max_expected_events,
            max_chain_generation=config.source_model.max_chain_generation,
            max_total_reactions=config.source_model.max_total_reactions,
        )
        batch = chain_generator.sample_with_lineage(
            profile,
            0.0,
            duration_s,
            arrival_rng,
        )
        times_s = batch.times_s
        lineage = np.empty(times_s.size, dtype=EVENT_LINEAGE_DTYPE)
        lineage["event_id"] = np.arange(times_s.size, dtype=np.int64)
        lineage["chain_id"] = batch.chain_ids
        lineage["generation"] = batch.generations
        derived_source_metadata = prompt_model.to_metadata()
    else:
        profile = ConstantRateProfile(rate_cps)
        times_s = arrival_generator.sample(profile, 0.0, duration_s, arrival_rng)
    if times_s.size > max_expected_events:
        raise ValueError("realized event count exceeds the explicit in-memory limit")

    spectrum = ParametricHe3Spectrum.from_config(config.spectrum)
    spectrum_samples = spectrum.sample(times_s.size, spectrum_rng)
    amplitude_mapper = LinearAmplitudeMapper.from_config(config.amplitude)
    amplitude_samples = amplitude_mapper.sample(spectrum_samples.energy_dep_keV, amplitude_rng)

    tau_r_s = _required_value(config.pulse_shape.tau_r_s, "tau_r_s")
    tau_d_s = _required_value(config.pulse_shape.tau_d_s, "tau_d_s")
    pulse_parameters = FixedPulseParameterProvider(tau_r_s, tau_d_s).sample(
        amplitude_samples.amplitude_peak_V,
        spectrum_samples.component_id,
        pulse_parameter_rng,
    )
    parameter_status = event_parameter_status(config, source_kind)

    events = np.empty(times_s.size, dtype=TRUE_EVENT_DTYPE)
    events["event_id"] = np.arange(times_s.size, dtype=np.int64)
    events["t_s"] = times_s
    events["energy_dep_keV"] = spectrum_samples.energy_dep_keV
    events["spectrum_component_id"] = spectrum_samples.component_id
    events["amplitude_peak_V"] = amplitude_samples.amplitude_peak_V
    events["tau_r_s"] = pulse_parameters.tau_r_s
    events["tau_d_s"] = pulse_parameters.tau_d_s
    events["polarity"] = amplitude_samples.polarity
    events["block_id"] = UNASSIGNED_INDEX
    events["sample_index"] = UNASSIGNED_INDEX
    events["pileup_group_id"] = UNASSIGNED_INDEX
    events["parameter_status"] = parameter_status.value.encode("ascii")

    if events.size:
        if np.any(np.diff(events["t_s"]) <= 0.0):
            raise RuntimeError("truth-event times are not strictly increasing")
        if np.any(events["energy_dep_keV"] < 0.0):
            raise RuntimeError("truth-event table contains negative energy")
        if np.any(events["amplitude_peak_V"] <= 0.0):
            raise RuntimeError("truth-event table contains non-positive amplitude")

    return TrueEventSimulation(
        events=events,
        duration_s=duration_s,
        true_rate_cps=rate_cps,
        seed=seed,
        parameter_status=parameter_status,
        arrival_algorithm=algorithm,
        source_model=source_kind,
        lineage=lineage,
        derived_source_metadata=derived_source_metadata,
    )
