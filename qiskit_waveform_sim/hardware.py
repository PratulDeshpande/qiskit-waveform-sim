"""
Control-hardware impairment model for qiskit-waveform-sim.

A :class:`HardwareProfile` describes the AWG -> mixer -> cable chain that drives
the qubits (per-channel skew, IQ imbalance, DC offset, DAC resolution,
bandwidth). It is deliberately separate from Qiskit's ``Target``, which holds
qubit-side data. The impairments are *waveform* impairments applied to
synthesized samples; they are not a gate-fidelity prediction, because the
package does not evolve a Hamiltonian.

The presets are generic and illustrative, not datasheet values of any product.
"""

from __future__ import annotations

import dataclasses
import fnmatch
import json
import math
import secrets
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

_GLOB_CHARS = "*?["

# Truncation target for the low-pass lookback: residual state a**L <= 1e-12
_LOWPASS_TOLERANCE = 1e-12


def _check_float(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a real number, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")


@dataclass(frozen=True)
class ChannelImpairments:
    """
    Deterministic impairments of one control channel.

    Parameters
    ----------
    delay_ns : float
        Channel latency in ns, ``>= 0``. Express skew relative to the earliest
        channel; a negative delay would move pulses before t = 0.
    amp_scale : float
        Digital gain error applied before the DAC, ``> 0``.
    gain_imbalance : float
        Mixer I/Q gain imbalance ``epsilon`` with ``|epsilon| < 1``:
        ``I' = (1 + e/2) I`` and ``Q' = (1 - e/2) (Q cos(phi) - I sin(phi))``.
    phase_error_deg : float
        Mixer I/Q phase error ``phi`` in degrees, ``|phi| < 90``.
    dc_i, dc_q : float
        DC offset (LO leakage) added after the mixer, in units of full scale.
    dac_bits : int or None
        DAC resolution (two's complement, ``2..32``). ``None`` disables
        quantization and clipping.
    bandwidth_mhz : float or None
        -3 dB bandwidth of a 1-pole low-pass in MHz. ``None`` disables it.
    """

    delay_ns: float = 0.0
    amp_scale: float = 1.0
    gain_imbalance: float = 0.0
    phase_error_deg: float = 0.0
    dc_i: float = 0.0
    dc_q: float = 0.0
    dac_bits: int | None = None
    bandwidth_mhz: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "delay_ns",
            "amp_scale",
            "gain_imbalance",
            "phase_error_deg",
            "dc_i",
            "dc_q",
        ):
            _check_float(name, getattr(self, name))
        if self.delay_ns < 0:
            raise ValueError(f"delay_ns must be >= 0, got {self.delay_ns}")
        if self.amp_scale <= 0:
            raise ValueError(f"amp_scale must be > 0, got {self.amp_scale}")
        if abs(self.gain_imbalance) >= 1:
            raise ValueError(f"|gain_imbalance| must be < 1, got {self.gain_imbalance}")
        if abs(self.phase_error_deg) >= 90:
            raise ValueError(
                f"|phase_error_deg| must be < 90, got {self.phase_error_deg}"
            )
        if self.dac_bits is not None and (
            isinstance(self.dac_bits, bool)
            or not isinstance(self.dac_bits, int)
            or not 2 <= self.dac_bits <= 32
        ):
            raise ValueError(
                f"dac_bits must be an integer in 2..32, got {self.dac_bits!r}"
            )
        if self.bandwidth_mhz is not None:
            _check_float("bandwidth_mhz", self.bandwidth_mhz)
            if self.bandwidth_mhz <= 0:
                raise ValueError(f"bandwidth_mhz must be > 0, got {self.bandwidth_mhz}")

    @property
    def is_ideal(self) -> bool:
        """True when every field is at its neutral default."""
        return all(getattr(self, f.name) == f.default for f in dataclasses.fields(self))

    def delay_split(self, dt: float) -> tuple[int, float]:
        """
        Split the delay into whole samples ``k`` and a fraction ``f`` in ``[0, 1)``.

        Values within 1e-9 samples of an integer snap to it, so whole-sample
        delays are exact despite floating-point rounding (a plain floor of
        ``delay_ns * 1e-9 / dt`` is off by one for some whole-sample delays).
        """
        samples = self.delay_ns * 1e-9 / dt
        nearest = round(samples)
        if abs(samples - nearest) < 1e-9:
            return int(nearest), 0.0
        whole = math.floor(samples)
        return int(whole), samples - whole


def _has_glob(key: str) -> bool:
    return any(c in key for c in _GLOB_CHARS)


@dataclass
class HardwareProfile:
    """
    Control-hardware profile with per-channel overrides.

    Channel keys are exact channel names (``d0``, ``m1``, ``u(0,1)``) or globs
    (``d*``, ``u(*)``), matched case-sensitively. Precedence: exact name, then
    the first matching glob in insertion order, then ``default``. The chosen
    entry is used whole; entries are not merged at lookup time.

    Parameters
    ----------
    default : ChannelImpairments
        Used for channels no key matches.
    channels : dict[str, ChannelImpairments]
        Per-channel overrides.
    seed : int, optional
        Seed for the stochastic impairments (Phase 2). Drawn once from system
        entropy when omitted, and stored so a saved file reproduces the run.
    """

    default: ChannelImpairments = field(default_factory=ChannelImpairments)
    channels: dict[str, ChannelImpairments] = field(default_factory=dict)
    seed: int | None = None

    def __post_init__(self) -> None:
        from qiskit_waveform_sim.core import _parse_channel  # avoids an import cycle

        for key in self.channels:
            if not _has_glob(key):
                _parse_channel(key)  # raises ValueError for a bad channel name
        if self.seed is None:
            self.seed = secrets.randbits(63)
        elif (
            isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
            or self.seed < 0
        ):
            raise ValueError(f"seed must be a non-negative integer, got {self.seed!r}")

    def for_channel(self, channel: str) -> ChannelImpairments:
        """Impairments for ``channel``: exact name > first matching glob > default."""
        exact = self.channels.get(channel)
        if exact is not None and not _has_glob(channel):
            return exact
        for pattern, impairments in self.channels.items():
            if _has_glob(pattern) and fnmatch.fnmatchcase(channel, pattern):
                return impairments
        return self.default

    def validate_for_dt(self, dt: float) -> None:
        """Check the parameters that depend on the sample period (Nyquist)."""
        nyquist_mhz = 0.5 / dt / 1e6
        for label, imp in (("default", self.default), *self.channels.items()):
            if imp.bandwidth_mhz is not None and imp.bandwidth_mhz >= nyquist_mhz:
                raise ValueError(
                    f"bandwidth_mhz={imp.bandwidth_mhz} for {label!r} must be below "
                    f"the Nyquist frequency {nyquist_mhz:.1f} MHz (dt={dt:.3e} s)"
                )

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict form with every field written out."""
        return {
            "seed": self.seed,
            "default": dataclasses.asdict(self.default),
            "channels": {k: dataclasses.asdict(v) for k, v in self.channels.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HardwareProfile:
        """
        Build a profile from a dict (the JSON/TOML layout).

        Keys left out of a channel entry are filled from the ``default`` entry.
        Unknown keys raise ``ValueError`` so typos do not pass silently.
        """
        unknown = set(data) - {"seed", "default", "channels"}
        if unknown:
            raise ValueError(f"Unknown profile keys: {sorted(unknown)}")
        default_data = dict(data.get("default", {}))
        default = _impairments_from_dict(default_data)
        channels = {
            key: _impairments_from_dict({**default_data, **dict(entry)})
            for key, entry in data.get("channels", {}).items()
        }
        return cls(default=default, channels=channels, seed=data.get("seed"))

    @classmethod
    def from_file(cls, path: str | Path) -> HardwareProfile:
        """Load a profile from a ``.json`` or ``.toml`` file."""
        path = Path(path)
        suffix = path.suffix.lower()
        text = path.read_text(encoding="utf-8")
        if suffix == ".json":
            data = json.loads(text)
        elif suffix == ".toml":
            data = tomllib.loads(text)
        else:
            raise ValueError(
                f"Unsupported profile file suffix {path.suffix!r}; use .json or .toml"
            )
        return cls.from_dict(data)

    def to_file(self, path: str | Path) -> None:
        """Save the profile as JSON (TOML is read-only: the stdlib cannot write it)."""
        path = Path(path)
        if path.suffix.lower() != ".json":
            raise ValueError(f"Profiles are saved as .json, got {path.suffix!r}")
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def from_preset(cls, name: str, seed: int | None = None) -> HardwareProfile:
        """Build one of the generic, illustrative presets (see :data:`PRESET_NAMES`)."""
        try:
            default, channels = _PRESETS[name]
        except KeyError:
            raise ValueError(
                f"Unknown preset {name!r}; choose from {list(_PRESETS)}"
            ) from None
        return cls(default=default, channels=dict(channels), seed=seed)


def _impairments_from_dict(data: Mapping[str, Any]) -> ChannelImpairments:
    allowed = {f.name for f in dataclasses.fields(ChannelImpairments)}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(
            f"Unknown impairment keys {sorted(unknown)}; allowed: {sorted(allowed)}"
        )
    return ChannelImpairments(**data)


def _preset(
    base: ChannelImpairments, **skews: float
) -> tuple[ChannelImpairments, dict]:
    """A preset whose channel entries repeat ``base`` with a per-pattern delay."""
    return base, {
        pattern: dataclasses.replace(base, delay_ns=delay)
        for pattern, delay in skews.items()
    }


# Generic, illustrative values. Stochastic terms (noise, jitter) arrive with Phase 2.
_PRESETS: dict[str, tuple[ChannelImpairments, dict[str, ChannelImpairments]]] = {
    "ideal": (ChannelImpairments(), {}),
    "iq_mixer_uncalibrated": _preset(
        ChannelImpairments(
            gain_imbalance=0.05,
            phase_error_deg=3.0,
            dc_i=0.012,
            dc_q=-0.008,
            dac_bits=14,
            bandwidth_mhz=400.0,
        ),
        **{"u(*)": 12.0, "m*": 40.0},
    ),
    "iq_mixer_calibrated": _preset(
        ChannelImpairments(
            gain_imbalance=0.002,
            phase_error_deg=0.2,
            dc_i=0.0005,
            dc_q=-0.0003,
            dac_bits=14,
            bandwidth_mhz=400.0,
        ),
        **{"u(*)": 0.5, "m*": 2.0},
    ),
    "direct_rf": _preset(
        ChannelImpairments(dac_bits=12, bandwidth_mhz=1000.0),
        **{"u(*)": 0.3, "m*": 1.0},
    ),
    "noisy_lab": _preset(
        ChannelImpairments(
            gain_imbalance=0.03,
            phase_error_deg=2.0,
            dc_i=0.006,
            dc_q=-0.004,
            dac_bits=10,
            bandwidth_mhz=250.0,
        ),
        **{"u(*)": 8.0, "m*": 25.0},
    ),
}

PRESET_NAMES: tuple[str, ...] = tuple(_PRESETS)


# -- signal helpers (pure functions on sample arrays) --------------------------


def quantize_dac(wave: np.ndarray, bits: int) -> np.ndarray:
    """
    Quantize I and Q separately to a ``bits``-bit two's-complement DAC.

    Codes run from ``-2**(bits-1)`` to ``2**(bits-1) - 1`` with
    ``LSB = 2**-(bits-1)``, so the top code is ``1 - LSB`` and full scale ``+1``
    clips there. This is the only clipping stage of the impairment chain.
    """
    lsb = 2.0 ** -(bits - 1)
    low, high = -(2 ** (bits - 1)), 2 ** (bits - 1) - 1

    def code(x: np.ndarray) -> np.ndarray:
        return np.clip(np.round(x / lsb), low, high) * lsb

    return code(wave.real) + 1j * code(wave.imag)  # type: ignore[no-any-return]


def lowpass(wave: np.ndarray, bandwidth_hz: float, dt: float) -> np.ndarray:
    """
    1-pole low-pass ``y[n] = (1 - a) x[n] + a y[n-1]`` from zero initial state.

    ``a = exp(-2 pi f_3dB dt)``; the DC gain is 1. Evaluated with a doubling
    scan (log2(N) vectorized passes), so no SciPy is needed.
    """
    a = math.exp(-2.0 * math.pi * bandwidth_hz * dt)
    y = (1.0 - a) * np.asarray(wave, dtype=np.complex128)
    shift = 1
    while shift < y.size:
        y[shift:] = y[shift:] + (a**shift) * y[:-shift]
        shift *= 2
    return y


def lowpass_lookback(bandwidth_hz: float, dt: float) -> int:
    """
    Samples of history after which the 1-pole filter's initial state is below 1e-12.

    A 1-pole IIR has infinite memory, so starting a window this many samples
    early agrees with the full-history response to ``1e-12 * max|x|``, not
    bit-exactly.
    """
    a = math.exp(-2.0 * math.pi * bandwidth_hz * dt)
    return max(1, math.ceil(math.log(_LOWPASS_TOLERANCE) / math.log(a)))


def apply_iq_imbalance(
    wave: np.ndarray, gain_imbalance: float, phase_error_deg: float
) -> np.ndarray:
    """Apply mixer gain/phase imbalance: ``I' = (1+e/2) I``, ``Q' = (1-e/2)(Q cos(p) - I sin(p))``."""
    if gain_imbalance == 0.0 and phase_error_deg == 0.0:
        return wave
    phi = math.radians(phase_error_deg)
    i, q = wave.real, wave.imag
    i_out = (1.0 + gain_imbalance / 2.0) * i
    q_out = (1.0 - gain_imbalance / 2.0) * (q * math.cos(phi) - i * math.sin(phi))
    return i_out + 1j * q_out  # type: ignore[no-any-return]


__all__ = [
    "PRESET_NAMES",
    "ChannelImpairments",
    "HardwareProfile",
    "apply_iq_imbalance",
    "lowpass",
    "lowpass_lookback",
    "quantize_dac",
]
