"""Pure-prompt one-speed source-model mapping for correlated neutron chains."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from he3sim.config import SourceModelConfig


def _required_value(parameter: object, name: str) -> float:
    """Extract one validated scalar ParameterValue without weakening its type contract."""
    value = getattr(parameter, "value", None)
    if value is None:
        raise ValueError(f"correlated source_model requires {name}")
    return float(value)


@dataclass(frozen=True, slots=True)
class PromptSourceModel:
    """Resolved rates and multiplicity law for a subcritical pure-prompt model."""

    k_eff: float
    reactivity: float
    alpha_per_s: float
    detection_efficiency: float
    nu_bar: float
    nu_pmf: npt.NDArray[np.float64]
    source_rate_cps: float
    lambda_f_per_s: float
    lambda_c_per_s: float
    lambda_d_per_s: float
    lambda_t_per_s: float
    mean_reaction_time_s: float
    generation_time_s: float
    diven_factor: float
    expected_detected_rate_cps: float

    @classmethod
    def from_config(cls, config: SourceModelConfig) -> PromptSourceModel:
        """Resolve and independently verify all pure-prompt derived quantities."""
        k_eff = config.resolved_k_eff()
        alpha = _required_value(config.alpha, "alpha")
        epsilon = _required_value(config.detection_efficiency, "detection_efficiency")
        nu_bar = _required_value(config.nu_bar, "nu_bar")
        source_rate_cps = _required_value(config.source_rate_cps, "source_rate_cps")
        if config.nu_pmf is None or config.nu_pmf.value is None:
            raise ValueError("correlated source_model requires nu_pmf")
        nu_pmf = np.asarray(config.nu_pmf.value, dtype=np.float64)

        lambda_t = alpha / (1.0 - k_eff)
        lambda_f = k_eff * lambda_t / nu_bar
        lambda_d = epsilon * lambda_t
        lambda_c = lambda_t - lambda_f - lambda_d
        if lambda_c < -1.0e-12 * lambda_t:
            raise ValueError("derived capture rate is negative")
        lambda_c = max(0.0, lambda_c)
        multiplicity = np.arange(nu_pmf.size, dtype=np.float64)
        factorial_second = float(np.sum(multiplicity * (multiplicity - 1.0) * nu_pmf))
        diven_factor = factorial_second / (nu_bar * nu_bar)

        return cls(
            k_eff=k_eff,
            reactivity=(k_eff - 1.0) / k_eff,
            alpha_per_s=alpha,
            detection_efficiency=epsilon,
            nu_bar=nu_bar,
            nu_pmf=nu_pmf,
            source_rate_cps=source_rate_cps,
            lambda_f_per_s=lambda_f,
            lambda_c_per_s=lambda_c,
            lambda_d_per_s=lambda_d,
            lambda_t_per_s=lambda_t,
            mean_reaction_time_s=1.0 / lambda_t,
            generation_time_s=1.0 / (nu_bar * lambda_f),
            diven_factor=diven_factor,
            expected_detected_rate_cps=source_rate_cps * epsilon / (1.0 - k_eff),
        )

    def to_metadata(self) -> dict[str, float]:
        """Return derived SI-valued quantities for transparent persistence."""
        return {
            "k_eff": self.k_eff,
            "reactivity": self.reactivity,
            "alpha_per_s": self.alpha_per_s,
            "lambda_f_per_s": self.lambda_f_per_s,
            "lambda_c_per_s": self.lambda_c_per_s,
            "lambda_d_per_s": self.lambda_d_per_s,
            "lambda_t_per_s": self.lambda_t_per_s,
            "mean_reaction_time_s": self.mean_reaction_time_s,
            "generation_time_s": self.generation_time_s,
            "diven_factor": self.diven_factor,
            "expected_detected_rate_cps": self.expected_detected_rate_cps,
        }
