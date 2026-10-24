"""
Core waveform simulation engine for qiskit-waveform-sim.

Provides lazy, windowed evaluation of sample-precise I/Q control waveforms with
Virtual-Z frame tracking. The ``get_snippet()`` API is inspired by LabOne Q's
OutputSimulator. This module synthesizes control waveforms; it does not simulate
qubit dynamics.
"""

from __future__ import annotations

import bisect
import math
import operator
import re
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from qiskit import QuantumCircuit, qasm3
from qiskit.circuit import BoxOp
from qiskit.transpiler import Target

from qiskit_waveform_sim.annotations import (
    PulseAnnotationSerializer,
    PulseEnvelopeAnnotation,
)


@dataclass(frozen=True)
class ChannelEvent:
    """
    Lightweight event record representing a scheduled hardware pulse or phase shift.

    Memory footprint ~64 bytes per gate, enabling compilation of large circuits
    without sample array allocation.
    """

    channel: str
    start_dt: int
    duration_dt: int
    op_name: str
    qubits: tuple[int, ...]
    frame_phase_rad: float
    shape: str
    amp: complex
    beta: float = 0.0
    sigma_dt: float = 16.0
    risefall_dt: int = 16

    def __post_init__(self) -> None:
        if self.duration_dt < 0:
            raise ValueError(
                f"duration_dt must be non-negative, got {self.duration_dt}"
            )
        if abs(self.amp) > 1.0 + 1e-12:
            raise ValueError(
                f"Amplitude magnitude {abs(self.amp):.6f} exceeds DAC full-scale (1.0)"
            )


@dataclass
class WaveformSnippet:
    """
    LabOne Q OutputSimulator-style snippet container.

    Contains the synthesized complex waveform for a specific time window
    on a specific channel, along with metadata for visualization.
    """

    channel: str
    start_dt: int
    dt_sec: float
    time_ns: np.ndarray
    wave: np.ndarray  # Complex I + 1j*Q array
    phase_rad: np.ndarray
    events: list[ChannelEvent] = field(default_factory=list)


class AnalyticalEnvelopes:
    """
    Vectorized NumPy evaluators for physical microwave pulse envelopes.

    All methods are static and operate on time arrays in dt units,
    returning complex baseband envelopes.
    """

    @staticmethod
    def drag(
        t_dt: np.ndarray,
        duration_dt: int,
        amp: complex,
        sigma_dt: float,
        beta: float,
    ) -> np.ndarray:
        """
        DRAG (Derivative Removal by Adiabatic Gate) envelope with pedestal correction.

        The I quadrature is a pedestal-corrected Gaussian that is exactly zero at
        the pulse edges. The Q quadrature is beta times its time derivative,
        matching Qiskit's ``Drag`` definition; it is small but not exactly zero
        at the edges.

        Parameters
        ----------
        t_dt : np.ndarray
            Time points in dt units, relative to pulse start
        duration_dt : int
            Total pulse duration in dt
        amp : complex
            Complex amplitude as a fraction of DAC full scale (phase = drive phase)
        sigma_dt : float
            Gaussian standard deviation in dt units
        beta : float
            DRAG leakage suppression parameter (typically 0.05-0.15)

        Returns
        -------
        np.ndarray
            Complex baseband envelope Ω(t) = A[g_norm(t) + iβ d(g_norm)/dt].
            The Q quadrature is +β times the derivative of the I quadrature envelope.
        """
        if abs(amp) > 1.0 + 1e-12:
            raise ValueError(
                f"Amplitude magnitude {abs(amp):.6f} exceeds DAC full-scale (1.0)"
            )
        if duration_dt <= 0:
            return np.zeros_like(t_dt, dtype=np.complex128)
        if sigma_dt <= 0:
            raise ValueError(f"sigma_dt must be > 0, got {sigma_dt}")
        t_center = 0.5 * duration_dt
        gauss = np.exp(-0.5 * ((t_dt - t_center) / sigma_dt) ** 2)
        pedestal = np.exp(-0.5 * (t_center / sigma_dt) ** 2)

        # Normalized Gaussian with zero boundary conditions
        norm_gauss = np.clip((gauss - pedestal) / (1.0 - pedestal), 0.0, None)

        # True analytical derivative matching Qiskit's Drag definition
        # Derivative of norm_gauss is proportional to gauss, not norm_gauss
        deriv_term = -((t_dt - t_center) / (sigma_dt**2)) * (gauss / (1.0 - pedestal))

        # Complex DRAG: Ω(t) = A * [norm_gauss + i * β * deriv_term]
        return amp * (norm_gauss + 1j * beta * deriv_term)  # type: ignore

    @staticmethod
    def gaussian_square(
        t_dt: np.ndarray,
        duration_dt: int,
        amp: complex,
        risefall_dt: int,
    ) -> np.ndarray:
        """
        GaussianSquare (flat-top with Gaussian rise/fall) envelope with pedestal correction.

        Parameters
        ----------
        t_dt : np.ndarray
            Time points in dt units, relative to pulse start
        duration_dt : int
            Total pulse duration in dt
        amp : complex
            Complex amplitude
        risefall_dt : int
            Rise/fall duration in dt (each edge)

        Returns
        -------
        np.ndarray
            Real-valued envelope (0 to 1) scaled by amplitude
        """
        if abs(amp) > 1.0 + 1e-12:
            raise ValueError(
                f"Amplitude magnitude {abs(amp):.6f} exceeds DAC full-scale (1.0)"
            )
        if duration_dt <= 0:
            return np.zeros_like(t_dt, dtype=np.complex128)
        risefall_dt = min(risefall_dt, duration_dt // 2)
        if risefall_dt <= 0:
            return np.full_like(t_dt, amp, dtype=np.complex128)

        sigma = risefall_dt / 3.0  # 3σ ≈ risefall for ~99.7% containment
        width = duration_dt - 2 * risefall_dt
        env = np.ones_like(t_dt, dtype=np.float64)

        left_mask = t_dt < risefall_dt
        right_mask = t_dt > (risefall_dt + width)

        # Pedestal for zero boundary conditions
        pedestal = np.exp(-0.5 * (risefall_dt / sigma) ** 2)

        if np.any(left_mask):
            g_l = np.exp(-0.5 * ((t_dt[left_mask] - risefall_dt) / sigma) ** 2)
            env[left_mask] = np.clip((g_l - pedestal) / (1.0 - pedestal), 0.0, 1.0)

        if np.any(right_mask):
            g_r = np.exp(
                -0.5 * ((t_dt[right_mask] - (risefall_dt + width)) / sigma) ** 2
            )
            env[right_mask] = np.clip((g_r - pedestal) / (1.0 - pedestal), 0.0, 1.0)

        return amp * env


_SECONDS_PER_UNIT = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12}

# Operations that occupy time but legitimately emit no drive waveform
_IDLE_OPS = frozenset({"id", "reset", "delay", "barrier"})


def _float_param(op: Any) -> float:
    """First gate parameter as a float, with a clear error if it is unbound."""
    param = op.params[0]
    try:
        return float(param)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Gate '{op.name}' has an unbound parameter ({param}). "
            "Bind all parameters with QuantumCircuit.assign_parameters() before compile()."
        ) from exc


_CHANNEL_RE = re.compile(r"^(?:([dm])(\d+)|u\((\d+),(\d+)\))$")


def _parse_channel(channel: str) -> tuple[str, tuple[int, ...]]:
    """Parse ``d<q>``, ``m<q>`` or ``u(<c>,<t>)`` into ``(kind, qubit indices)``."""
    match = _CHANNEL_RE.match(channel)
    if match is None:
        raise ValueError(
            f"Unknown channel {channel!r}; expected 'd<q>', 'm<q>' or 'u(<c>,<t>)'"
        )
    if match.group(1) is not None:
        return match.group(1), (int(match.group(2)),)
    return "u", (int(match.group(3)), int(match.group(4)))


def _wrapped_angle(op: Any) -> float:
    """Rotation angle wrapped into [-pi, pi]; rotations are 2*pi periodic."""
    return math.remainder(_float_param(op), 2.0 * math.pi)


def _full_scale(amp: float, op_name: str) -> float:
    """Clip an amplitude to the DAC full-scale range, warning when it does."""
    if abs(amp) <= 1.0:
        return amp
    warnings.warn(
        f"Amplitude {amp:.3f} for '{op_name}' exceeds DAC full-scale and was clipped to 1.0",
        UserWarning,
        stacklevel=4,
    )
    return math.copysign(1.0, amp)


@dataclass(frozen=True)
class PulseDefaults:
    """
    Placeholder pulse parameters used when a gate carries no pulse annotation.

    Amplitudes are dimensionless fractions of DAC full scale in [-1, 1]. The
    defaults are **uncalibrated placeholders**, not Rabi rates; set them from
    your own calibration. ``rx(theta)`` uses ``x_amp * theta / pi`` and
    ``rzz(theta)`` scales ``cr_amp`` by ``theta / (pi / 2)``.

    Parameters
    ----------
    sx_amp : float
        Drive amplitude of ``sx`` (fraction of full scale).
    x_amp : float
        Drive amplitude of ``x`` and of the ECR echo pulse.
    cr_amp : float
        Cross-resonance / two-qubit pair-channel amplitude.
    measure_amp : float
        Readout pulse amplitude.
    drag_beta : float
        DRAG coefficient for single-qubit drive pulses.
    drag_sigma_ratio : float
        Gaussian sigma as a fraction of pulse duration (must be > 0).
    risefall_dt : int
        Rise/fall length in dt for pair-channel pulses.
    measure_risefall_dt : int
        Rise/fall length in dt for readout pulses.
    echo_x_max_dt : int
        Maximum duration in dt of the ECR echo X pulse.
    """

    sx_amp: float = 0.45
    x_amp: float = 0.90
    cr_amp: float = 0.65
    measure_amp: float = 0.35
    drag_beta: float = 0.08
    drag_sigma_ratio: float = 0.25
    risefall_dt: int = 16
    measure_risefall_dt: int = 24
    echo_x_max_dt: int = 160

    def __post_init__(self) -> None:
        for name in ("sx_amp", "x_amp", "cr_amp", "measure_amp"):
            if abs(getattr(self, name)) > 1.0:
                raise ValueError(
                    f"{name} must satisfy abs(value) <= 1.0 (fraction of DAC full "
                    f"scale), got {getattr(self, name)}"
                )
        if not self.drag_sigma_ratio > 0:
            raise ValueError(
                f"drag_sigma_ratio must be > 0, got {self.drag_sigma_ratio}"
            )
        for name in ("risefall_dt", "measure_risefall_dt", "echo_x_max_dt"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0, got {getattr(self, name)}")


class TargetWaveformSimulator:
    """
    Control-waveform synthesizer for Qiskit 2.x scheduled circuits.

    The ``get_snippet()`` API is inspired by LabOne Q's OutputSimulator. It
    synthesizes control waveforms and does not simulate qubit dynamics.

    Tracks Virtual-Z phase accumulation per qubit and synthesizes I/Q waveforms
    lazily on-demand via windowed snippet extraction.

    Memory complexity: O(N_events) for compilation, O(W) for snippet extraction,
    where W is the requested window length in dt.

    Example
    -------
    >>> backend = GenericBackendV2(num_qubits=2)
    >>> qc = QuantumCircuit(2)
    >>> qc.h(0); qc.cx(0, 1); qc.measure_all()
    >>> pm = generate_preset_pass_manager(backend=backend, scheduling_method="alap")
    >>> scheduled_qc = pm.run(qc)
    >>> sim = TargetWaveformSimulator(backend.target).compile(scheduled_qc)
    >>> snippet = sim.get_snippet("d0", start_dt=0, length_dt=1000)
    >>> print(snippet.wave.shape)  # (1000,) complex array
    """

    def __init__(
        self,
        target: Target,
        if_freq_hz: float = 0.0,
        defaults: PulseDefaults | None = None,
    ):
        """
        Initialize simulator with backend target.

        Parameters
        ----------
        target : Target
            Qiskit 2.x Target containing instruction durations and properties
        if_freq_hz : float, optional
            Intermediate frequency for digital upconversion (Hz).
            0.0 = baseband, non-zero = NCO modulation prior to DAC.
        defaults : PulseDefaults, optional
            Placeholder amplitudes and shapes for gates without a pulse
            annotation. Defaults to ``PulseDefaults()``.
        """
        self.target = target
        self.defaults = defaults if defaults is not None else PulseDefaults()
        if target.dt is None:
            warnings.warn(
                "Target has no dt; assuming 0.222 ns (4.5 GSa/s)",
                UserWarning,
                stacklevel=2,
            )
        self.dt = target.dt if target.dt is not None else 0.222e-9  # 4.5 GSa/s
        self.if_freq_hz = if_freq_hz
        self.events_by_channel: dict[str, list[ChannelEvent]] = {}
        self.phase_history: dict[int, list[tuple[int, float]]] = {}
        self.total_duration_dt: int = 0
        self._num_qubits: int = 0
        self._warned_ops: set[str] = set()

    def compile(
        self,
        scheduled_qc: QuantumCircuit,
        start_times: Sequence[int] | None = None,
    ) -> TargetWaveformSimulator:
        """
        Compile a scheduled circuit into channel events with frame tracking.

        Parameters
        ----------
        scheduled_qc : QuantumCircuit
            Circuit with op_start_times populated (via scheduling pass), or any
            circuit when ``start_times`` is given.
        start_times : Sequence[int], optional
            Start time in dt of every top-level instruction, in
            ``scheduled_qc.data`` order. Used instead of
            ``scheduled_qc.op_start_times``. Required for circuits containing
            ``BoxOp``, which Qiskit's scheduler rejects. Must have one
            non-negative integer per instruction.

        Returns
        -------
        TargetWaveformSimulator
            Self, for method chaining

        Raises
        ------
        ValueError
            If the circuit is unscheduled and ``start_times`` is not given, or
            if ``start_times`` has the wrong length or invalid entries.

        Examples
        --------
        Hand-schedule a boxed circuit whose box starts at t = 0::

            qc = QuantumCircuit(1)
            with qc.box(duration=160, unit="dt"):
                qc.sx(0)
            sim = TargetWaveformSimulator(target).compile(qc, start_times=[0])
        """
        if start_times is not None:
            if len(start_times) != len(scheduled_qc.data):
                raise ValueError(
                    f"start_times has {len(start_times)} entries but the circuit "
                    f"has {len(scheduled_qc.data)} instructions."
                )
            checked: list[int] = []
            for i, t in enumerate(start_times):
                try:
                    value = operator.index(t)
                except TypeError:
                    raise ValueError(
                        f"start_times[{i}] must be an integer number of dt, got {t!r}."
                    ) from None
                if value < 0:
                    raise ValueError(f"start_times[{i}] must be >= 0, got {value}.")
                checked.append(value)
            times: Sequence[int] = checked
        else:
            op_times = getattr(scheduled_qc, "op_start_times", None)
            if op_times is None:
                raise ValueError(
                    "Circuit must be scheduled first. "
                    "Use generate_preset_pass_manager(..., scheduling_method='alap'). "
                    "For circuits containing BoxOp (which Qiskit's scheduler "
                    "rejects), pass start_times= explicitly."
                )
            times = op_times

        self._num_qubits = scheduled_qc.num_qubits
        qubit_phase: dict[int, float] = dict.fromkeys(range(self._num_qubits), 0.0)
        self.phase_history = {q: [(0, 0.0)] for q in range(self._num_qubits)}
        self.events_by_channel.clear()
        self._warned_ops = set()
        max_stop_dt = 0

        for inst, start_dt in zip(scheduled_qc.data, times, strict=True):
            op = inst.operation
            q_indices = tuple(scheduled_qc.find_bit(q).index for q in inst.qubits)
            max_stop_dt = max(
                max_stop_dt,
                self._lower_instruction(op, q_indices, start_dt, qubit_phase),
            )

        # Sort events per channel by start_dt for O(log N) binary search
        for ch in self.events_by_channel:
            self.events_by_channel[ch].sort(key=lambda e: e.start_dt)

        self.total_duration_dt = max_stop_dt
        # Cache starts and max durations for binary search in get_snippet
        self._starts_by_channel = {
            ch: [e.start_dt for e in events]
            for ch, events in self.events_by_channel.items()
        }
        self._max_duration_by_channel = {
            ch: max((e.duration_dt for e in events), default=0)
            for ch, events in self.events_by_channel.items()
        }
        return self

    def _get_duration_dt(self, op, q_indices: tuple[int, ...]) -> int:
        """Extract instruction duration in dt from Target or BoxOp metadata."""
        if op.name in ("rz", "barrier"):
            return 0
        if op.name == "delay":
            return self._to_dt(op.duration, getattr(op, "unit", "dt"))
        if isinstance(op, BoxOp):
            return self._box_duration_dt(op) or 0
        if op.name in self.target and q_indices in self.target[op.name]:
            props = self.target[op.name][q_indices]
            if props and props.duration is not None:
                return int(round(props.duration / self.dt))

        if op.name not in (
            "measure",
            "reset",
            "id",
            "u",
            "cz",
            "cp",
            "swap",
            "ecr",
            "rzz",
            "rx",
            "ry",
            "rz",
            "sx",
            "x",
            "h",
            "cx",
            "delay",
            "barrier",
        ):
            warnings.warn(
                f"Unknown operation '{op.name}' on qubits {q_indices}, using fallback duration of 160 dt",
                UserWarning,
                stacklevel=2,
            )
        return 160  # Fallback basis duration in dt

    def _lower_instruction(
        self,
        op,
        q_indices: tuple[int, ...],
        start_dt: int,
        qubit_phase: dict[int, float],
        override_ann: Any | None = None,
        duration_override: int | None = None,
    ) -> int:
        """
        Recursively lower an operation to channel events with frame tracking.

        Handles BoxOp containers, single-qubit gates, two-qubit gates, and measurements.
        """
        # Handle Qiskit 2.x BoxOp containers and inspect custom PulseEnvelopeAnnotations
        if isinstance(op, BoxOp):
            return self._lower_box(op, q_indices, start_dt, qubit_phase, override_ann)

        dur_dt = (
            duration_override
            if duration_override is not None
            else self._get_duration_dt(op, q_indices)
        )
        stop_dt = start_dt + dur_dt

        if op.name == "rz":
            lam = _float_param(op)
            q0 = q_indices[0]
            qubit_phase[q0] -= lam
            self.phase_history[q0].append((start_dt, qubit_phase[q0]))
            self._append_event(
                ChannelEvent(
                    channel=f"d{q0}",
                    start_dt=start_dt,
                    duration_dt=0,
                    op_name=f"rz({lam:.2f})",
                    qubits=q_indices,
                    frame_phase_rad=qubit_phase[q0],
                    shape="virtual_z",
                    amp=0.0j,
                )
            )
            return stop_dt

        if op.name in ("delay", "barrier"):
            return stop_dt

        if len(q_indices) == 1 and op.name in ("sx", "x", "rx"):
            q0 = q_indices[0]

            if override_ann is not None:
                shape = override_ann.shape
                amp = override_ann.amp
                if op.name == "rx":
                    amp *= _wrapped_angle(op) / np.pi
                beta = override_ann.beta
                sigma_dt = dur_dt * override_ann.sigma_ratio
                risefall_dt = override_ann.risefall_dt
            else:
                shape = "drag"
                beta = self.defaults.drag_beta
                sigma_dt = dur_dt * self.defaults.drag_sigma_ratio
                risefall_dt = self.defaults.risefall_dt

                # Uncalibrated Analytical Fallback (since we don't parse pulse schedules)
                if op.name == "sx":
                    amp = self.defaults.sx_amp
                elif op.name == "x":
                    amp = self.defaults.x_amp
                else:
                    amp = self.defaults.x_amp * (_wrapped_angle(op) / np.pi)

            self._append_event(
                ChannelEvent(
                    channel=f"d{q0}",
                    start_dt=start_dt,
                    duration_dt=dur_dt,
                    op_name=op.name,
                    qubits=q_indices,
                    frame_phase_rad=qubit_phase[q0],
                    shape=shape,
                    amp=complex(amp),
                    beta=beta,
                    sigma_dt=sigma_dt,
                    risefall_dt=risefall_dt,
                )
            )

        elif len(q_indices) == 2 and op.name in ("cx", "ecr", "rzz", "cz"):
            c_q, t_q = q_indices
            scale = (_wrapped_angle(op) / (0.5 * np.pi)) if op.name == "rzz" else 1.0
            # Pair-channel tones are driven at the target frequency: target frame
            cr_phase = qubit_phase[t_q]
            if override_ann is not None:
                cr_shape = override_ann.shape
                cr_amp = complex(_full_scale(override_ann.amp * scale, op.name))
                cr_risefall = override_ann.risefall_dt
                cr_beta = override_ann.beta
                cr_sigma_ratio: float | None = override_ann.sigma_ratio
            else:
                # Uncalibrated Analytical Fallback for CR amplitude
                cr_shape = "gaussian_square"
                cr_amp = complex(_full_scale(self.defaults.cr_amp * scale, op.name))
                cr_risefall = self.defaults.risefall_dt
                cr_beta, cr_sigma_ratio = 0.0, None

            def pair_pulse(t0: int, dur: int, name: str, phase: float) -> None:
                self._append_event(
                    ChannelEvent(
                        channel=f"u({c_q},{t_q})",
                        start_dt=t0,
                        duration_dt=dur,
                        op_name=name,
                        qubits=q_indices,
                        frame_phase_rad=phase,
                        shape=cr_shape,
                        amp=cr_amp,
                        beta=cr_beta,
                        sigma_dt=(
                            dur * cr_sigma_ratio if cr_sigma_ratio is not None else 16.0
                        ),
                        risefall_dt=cr_risefall,
                    )
                )

            if op.name == "cz":
                # Uncalibrated flat-top stand-in for a coupler-driven CZ
                pair_pulse(start_dt, dur_dt, "cz", cr_phase)
            elif op.name == "ecr":
                x_dur = min(
                    self.defaults.echo_x_max_dt, dur_dt // 3
                )  # Echo X is a fixed short pulse
                cr_dur = (dur_dt - x_dur) // 2
                pair_pulse(start_dt, cr_dur, f"{op.name}_cr+", cr_phase)
                self._append_event(
                    ChannelEvent(
                        channel=f"d{c_q}",
                        start_dt=start_dt + cr_dur,
                        duration_dt=x_dur,
                        op_name="ecr_echo_x",
                        qubits=(c_q,),
                        frame_phase_rad=qubit_phase[c_q],
                        shape="drag",
                        amp=complex(self.defaults.x_amp),
                        beta=self.defaults.drag_beta,
                        sigma_dt=x_dur * self.defaults.drag_sigma_ratio,
                        risefall_dt=self.defaults.risefall_dt,
                    )
                )
                pair_pulse(
                    start_dt + cr_dur + x_dur,
                    dur_dt - cr_dur - x_dur,
                    f"{op.name}_cr-",
                    cr_phase + np.pi,
                )
            else:
                half_dur = dur_dt // 2
                pair_pulse(start_dt, half_dur, f"{op.name}_cr+", cr_phase)
                pair_pulse(
                    start_dt + half_dur,
                    dur_dt - half_dur,
                    f"{op.name}_cr-",
                    cr_phase + np.pi,
                )

        elif op.name == "measure":
            for q in q_indices:
                self._append_event(
                    ChannelEvent(
                        channel=f"m{q}",
                        start_dt=start_dt,
                        duration_dt=dur_dt,
                        op_name="measure",
                        qubits=(q,),
                        frame_phase_rad=0.0,
                        shape="gaussian_square",
                        amp=complex(self.defaults.measure_amp),
                        risefall_dt=self.defaults.measure_risefall_dt,
                    )
                )

        elif (
            dur_dt > 0 and op.name not in _IDLE_OPS and op.name not in self._warned_ops
        ):
            self._warned_ops.add(op.name)
            warnings.warn(
                f"Gate '{op.name}' on qubits {q_indices} has no waveform model; "
                f"its {dur_dt} dt are left empty on the pulse sheet",
                UserWarning,
                stacklevel=3,
            )

        return stop_dt

    def _box_duration_dt(self, op: BoxOp) -> int | None:
        """Static box duration in dt, or None when the box has no fixed duration."""
        if op.duration is None or op.unit == "expr":
            return None
        return self._to_dt(op.duration, op.unit)

    def _to_dt(self, duration: float, unit: str) -> int:
        """Convert a duration in `unit` (s, ms, us, ns, ps or dt) to whole dt."""
        if unit in _SECONDS_PER_UNIT:
            return int(round(duration * _SECONDS_PER_UNIT[unit] / self.dt))
        return int(duration)

    def _lower_box(
        self,
        op: BoxOp,
        q_indices: tuple[int, ...],
        start_dt: int,
        qubit_phase: dict[int, float],
        override_ann: Any | None,
    ) -> int:
        """
        Lower a BoxOp body.

        Instructions on different qubits run in parallel (one cursor per qubit).
        A box with a fixed duration around a single pulse gate sets that gate's
        duration; a box without a duration lasts as long as its contents.
        """
        box_ann = override_ann
        for ann in op.annotations:
            if isinstance(ann, PulseEnvelopeAnnotation):
                box_ann = ann
        box_dur = self._box_duration_dt(op)
        body = list(op.body.data)
        pulse_idx = [
            i
            for i, inst in enumerate(body)
            if inst.operation.name not in ("rz", "barrier", "delay")
        ]
        sized_idx = (
            pulse_idx[0] if box_dur is not None and len(pulse_idx) == 1 else None
        )

        cursors: dict[int, int] = {}
        stop_dt = start_dt
        for i, sub_inst in enumerate(body):
            sub_q = tuple(q_indices[op.body.find_bit(q).index] for q in sub_inst.qubits)
            t0 = max((cursors.get(q, start_dt) for q in sub_q), default=start_dt)
            end_dt = self._lower_instruction(
                sub_inst.operation,
                sub_q,
                t0,
                qubit_phase,
                override_ann=box_ann,
                # The sized gate gets whatever box time is left after earlier
                # instructions on its qubits (e.g. a leading delay)
                duration_override=(
                    max(0, box_dur - (t0 - start_dt))
                    if i == sized_idx and box_dur is not None
                    else None
                ),
            )
            for q in sub_q:
                cursors[q] = end_dt
            stop_dt = max(stop_dt, end_dt)

        if box_dur is not None:
            stop_dt = max(stop_dt, start_dt + box_dur)
        return stop_dt

    def _append_event(self, event: ChannelEvent) -> None:
        """Append event to channel event list."""
        self.events_by_channel.setdefault(event.channel, []).append(event)

    def get_snippet(
        self, channel: str, start_dt: int = 0, length_dt: int | None = None
    ) -> WaveformSnippet:
        """
        Synthesize the complex I(t) + 1j*Q(t) waveform strictly within [start_dt, start_dt + length_dt].

        Memory complexity is O(length_dt), independent of total circuit depth.
        Uses binary search to find only overlapping events.

        Parameters
        ----------
        channel : str
            Channel identifier (e.g., "d0", "u(0,1)", "m0")
        start_dt : int
            Start time in dt units
        length_dt : int, optional
            Window length in dt. Defaults to remaining circuit duration.

        Returns
        -------
        WaveformSnippet
            Container with time array, complex waveform, phase trace, and overlapping events
        """
        if start_dt < 0:
            raise ValueError(f"start_dt must be non-negative, got {start_dt}")
        if length_dt is not None and length_dt <= 0:
            raise ValueError(f"length_dt must be positive, got {length_dt}")

        if length_dt is None:
            length_dt = max(1, self.total_duration_dt - start_dt)
        stop_dt = start_dt + length_dt

        t_global_dt = np.arange(start_dt, stop_dt, dtype=np.float64)
        time_ns = t_global_dt * self.dt * 1e9
        wave = np.zeros(length_dt, dtype=np.complex128)
        phase_trace = np.zeros(length_dt, dtype=np.float64)

        # Resolve continuous phase tracking
        kind, indices = _parse_channel(channel)
        if self._num_qubits > 0 and any(i >= self._num_qubits for i in indices):
            raise ValueError(
                f"Channel {channel!r} references a qubit outside the "
                f"{self._num_qubits}-qubit circuit"
            )
        if kind == "d":
            phase_hist = self.phase_history.get(indices[0], [(0, 0.0)])
        elif kind == "u":
            phase_hist = self.phase_history.get(indices[1], [(0, 0.0)])
        else:
            # The measure tone has its own frame (measure events use phase 0.0)
            phase_hist = [(0, 0.0)]

        # Pre-fill phase_trace with piecewise constant frame phase
        for i in range(len(phase_hist)):
            t_change, phase_val = phase_hist[i]
            # The last frame phase holds until the end of the requested window
            t_next = phase_hist[i + 1][0] if i + 1 < len(phase_hist) else stop_dt

            w_start = max(start_dt, t_change)
            w_stop = min(stop_dt, t_next)
            if w_start < w_stop:
                phase_trace[w_start - start_dt : w_stop - start_dt] = phase_val

        events = self.events_by_channel.get(channel, [])
        if not events:
            return WaveformSnippet(
                channel=channel,
                start_dt=start_dt,
                dt_sec=self.dt,
                time_ns=time_ns,
                wave=wave,
                phase_rad=phase_trace,
                events=[],
            )
        starts = self._starts_by_channel.get(channel)
        if starts is None:
            starts = [e.start_dt for e in events]
        # Use max duration for proper lookback to catch long events that started earlier
        max_dur = self._max_duration_by_channel.get(channel, 0)
        # Search from start_dt - max_dur to catch long events spanning into window
        search_start = max(0, start_dt - max_dur)
        idx = bisect.bisect_left(starts, search_start)
        overlapping: list[ChannelEvent] = []

        for ev in events[idx:]:
            if ev.start_dt >= stop_dt:
                break
            ev_stop = ev.start_dt + ev.duration_dt
            # Pulses ending exactly at the window start do not overlap it
            if ev_stop < start_dt or (ev_stop == start_dt and ev.duration_dt > 0):
                continue
            overlapping.append(ev)
            if ev.duration_dt == 0:
                continue
            w_start = max(start_dt, ev.start_dt)
            w_stop = min(stop_dt, ev_stop)
            sl = slice(w_start - start_dt, w_stop - start_dt)
            t_local_dt = np.arange(
                w_start - ev.start_dt, w_stop - ev.start_dt, dtype=np.float64
            )

            if ev.shape == "drag":
                baseband = AnalyticalEnvelopes.drag(
                    t_local_dt, ev.duration_dt, ev.amp, ev.sigma_dt, ev.beta
                )
            elif ev.shape == "gaussian_square":
                baseband = AnalyticalEnvelopes.gaussian_square(
                    t_local_dt, ev.duration_dt, ev.amp, ev.risefall_dt
                )
            elif ev.shape == "virtual_z":
                continue
            else:
                warnings.warn(
                    f"Unknown pulse shape '{ev.shape}' on channel {channel}, skipping",
                    UserWarning,
                    stacklevel=2,
                )
                continue

            # Apply Virtual-Z frame phase rotation and digital IF carrier modulation
            carrier_phase = (
                2.0 * np.pi * self.if_freq_hz * (t_global_dt[sl] * self.dt)
                + ev.frame_phase_rad
            )
            wave[sl] += baseband * np.exp(1j * carrier_phase)

        return WaveformSnippet(
            channel=channel,
            start_dt=start_dt,
            dt_sec=self.dt,
            time_ns=time_ns,
            wave=wave,
            phase_rad=phase_trace,
            events=overlapping,
        )

    def get_channels(self) -> list[str]:
        """Return list of all channels with events."""
        return sorted(self.events_by_channel.keys())

    def get_phase_history(self, qubit: int) -> list[tuple[int, float]]:
        """Return phase history for a qubit as list of (dt, phase_rad)."""
        return self.phase_history.get(qubit, [])

    def export_openqasm3(
        self, scheduled_qc: QuantumCircuit, annotation_handlers: dict | None = None
    ) -> str:
        """
        Export scheduled circuit to OpenQASM 3 with serialized pulse annotations.

        Parameters
        ----------
        scheduled_qc : QuantumCircuit
            Scheduled circuit to export
        annotation_handlers : dict, optional
            Custom annotation serializers. Defaults to including PulseAnnotationSerializer
            for the "pulse_sim.envelope" namespace.
            e.g., {"pulse_sim.envelope": PulseAnnotationSerializer()}

        Returns
        -------
        str
            OpenQASM 3 string with pulse annotation pragmas
        """
        # annotation_handlers is available on every supported Qiskit (>= 2.5)
        handlers = {"pulse_sim.envelope": PulseAnnotationSerializer()}
        if annotation_handlers:
            handlers.update(annotation_handlers)
        return qasm3.dumps(scheduled_qc, annotation_handlers=handlers)  # type: ignore[no-any-return]
