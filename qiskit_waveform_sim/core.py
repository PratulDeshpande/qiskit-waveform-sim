"""
Core waveform simulation engine for qiskit-waveform-sim.

Provides lazy, windowed evaluation of sample-precise I/Q waveforms with exact
Virtual-Z frame tracking, matching LabOne Q OutputSimulator architecture.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from qiskit import QuantumCircuit
from qiskit.circuit import BoxOp
from qiskit.transpiler import Target
from qiskit_waveform_sim.annotations import PulseEnvelopeAnnotation


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
    qubits: Tuple[int, ...]
    frame_phase_rad: float
    shape: str
    amp: complex
    beta: float = 0.0
    sigma_dt: float = 16.0
    risefall_dt: int = 16


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
    events: List[ChannelEvent] = field(default_factory=list)


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
        
        The Q quadrature is windowed by the normalized Gaussian to ensure
        zero boundary conditions on both I and Q components.
        
        Parameters
        ----------
        t_dt : np.ndarray
            Time points in dt units, relative to pulse start
        duration_dt : int
            Total pulse duration in dt
        amp : complex
            Complex amplitude (magnitude = peak Rabi rate, phase = drive phase)
        sigma_dt : float
            Gaussian standard deviation in dt units
        beta : float
            DRAG leakage suppression parameter (typically 0.05-0.15)
            
        Returns
        -------
        np.ndarray
            Complex baseband envelope Ω(t) = A[g_norm(t) - iβ g_norm(t) * g'(t)/g(t)/σ]
            with zero boundary conditions on both real and imaginary parts.
        """
        t_center = 0.5 * duration_dt
        gauss = np.exp(-0.5 * ((t_dt - t_center) / sigma_dt) ** 2)
        pedestal = np.exp(-0.5 * (t_center / sigma_dt) ** 2)
        
        # Normalized Gaussian with zero boundary conditions
        norm_gauss = np.clip((gauss - pedestal) / (1.0 - pedestal), 0.0, None)
        
        # Analytical derivative: dg/dt = -(t - t_c)/σ² * g(t)
        # Window the derivative by norm_gauss to ensure zero boundaries on Q
        deriv_term = -((t_dt - t_center) / sigma_dt) * norm_gauss
        
        # Complex DRAG: Ω(t) = A * [g_norm(t) - iβ * (1/σ) * dg/dt * window]
        # Note: β ≈ α/Δ for transmon (anharmonicity/detuning)
        return amp * (norm_gauss - 1j * beta * deriv_term)

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
            g_r = np.exp(-0.5 * ((t_dt[right_mask] - (risefall_dt + width)) / sigma) ** 2)
            env[right_mask] = np.clip((g_r - pedestal) / (1.0 - pedestal), 0.0, 1.0)
        
        return amp * env


class TargetWaveformSimulator:
    """
    LabOne Q OutputSimulator equivalent for Qiskit 2.5+ scheduled circuits.
    
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
    
    def __init__(self, target: Target, if_freq_hz: float = 0.0):
        """
        Initialize simulator with backend target.
        
        Parameters
        ----------
        target : Target
            Qiskit 2.x Target containing instruction durations and properties
        if_freq_hz : float, optional
            Intermediate frequency for digital upconversion (Hz).
            0.0 = baseband, non-zero = NCO modulation prior to DAC.
        """
        self.target = target
        self.dt = target.dt if target.dt is not None else 0.222e-9  # Default 4.5 GSa/s
        self.if_freq_hz = if_freq_hz
        self.events_by_channel: Dict[str, List[ChannelEvent]] = {}
        self.phase_history: Dict[int, List[Tuple[int, float]]] = {}
        self.total_duration_dt: int = 0
        self._num_qubits: int = 0

    def compile(self, scheduled_qc: QuantumCircuit) -> "TargetWaveformSimulator":
        """
        Compile a scheduled circuit into channel events with frame tracking.
        
        Parameters
        ----------
        scheduled_qc : QuantumCircuit
            Circuit with op_start_times populated (via scheduling pass)
            
        Returns
        -------
        TargetWaveformSimulator
            Self, for method chaining
        """
        try:
            if scheduled_qc.op_start_times is None:
                raise ValueError(
                    "Circuit must be scheduled first. "
                    "Use generate_preset_pass_manager(..., scheduling_method='alap')."
                )
        except AttributeError:
            raise ValueError(
                "Circuit must be scheduled first. "
                "Use generate_preset_pass_manager(..., scheduling_method='alap')."
            )

        self._num_qubits = scheduled_qc.num_qubits
        qubit_phase: Dict[int, float] = {q: 0.0 for q in range(self._num_qubits)}
        self.phase_history = {q: [(0, 0.0)] for q in range(self._num_qubits)}
        self.events_by_channel.clear()
        max_stop_dt = 0

        for inst, start_dt in zip(scheduled_qc.data, scheduled_qc.op_start_times):
            op = inst.operation
            q_indices = tuple(scheduled_qc.find_bit(q).index for q in inst.qubits)
            max_stop_dt = max(max_stop_dt, self._lower_instruction(
                op, q_indices, start_dt, qubit_phase
            ))

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

    def compile_unscheduled(self, qc: QuantumCircuit) -> "TargetWaveformSimulator":
        """
        Compile an unscheduled circuit with BoxOp/control flow into channel events.
        
        This method performs a simple ALAP-like scheduling locally without requiring
        the transpiler's scheduling passes. It assigns sequential start times based on
        instruction durations, handles BoxOp by recursively lowering its body, and
        applies custom PulseEnvelopeAnnotation overrides.
        
        Note: This is a fallback for circuits with control flow (BoxOp) that cannot
        be scheduled by Qiskit's transpiler. For best results with scheduled circuits,
        use `compile()` with a properly scheduled circuit.
        
        Parameters
        ----------
        qc : QuantumCircuit
            Circuit (may contain BoxOp, annotations, fractional gates)
            
        Returns
        -------
        TargetWaveformSimulator
            Self, for method chaining
        """
        self._num_qubits = qc.num_qubits
        qubit_phase: Dict[int, float] = {q: 0.0 for q in range(self._num_qubits)}
        self.phase_history = {q: [(0, 0.0)] for q in range(self._num_qubits)}
        self.events_by_channel.clear()
        
        # Simple ALAP-style scheduling: process instructions in reverse for ASAP,
        # or forward for simple sequential scheduling
        cursor_dt = 0
        
        for inst in qc.data:
            op = inst.operation
            q_indices = tuple(qc.find_bit(q).index for q in inst.qubits)
            cursor_dt = self._lower_instruction(
                op, q_indices, cursor_dt, qubit_phase
            )
        
        # Sort events per channel by start_dt for O(log N) binary search
        for ch in self.events_by_channel:
            self.events_by_channel[ch].sort(key=lambda e: e.start_dt)
        
        self.total_duration_dt = cursor_dt
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

    def _get_duration_dt(self, op, q_indices: Tuple[int, ...]) -> int:
        """Extract instruction duration in dt from Target or BoxOp metadata."""
        if op.name in ("rz", "barrier"):
            return 0
        if op.name == "delay":
            # Handle Delay unit conversion: duration can be in s, ms, us, ns, ps, dt
            dur = op.duration
            unit = getattr(op, 'unit', 'dt')
            if unit == 'dt':
                return int(dur)
            elif unit == 's':
                return int(round(dur / self.dt))
            elif unit == 'ms':
                return int(round(dur * 1e-3 / self.dt))
            elif unit == 'us':
                return int(round(dur * 1e-6 / self.dt))
            elif unit == 'ns':
                return int(round(dur * 1e-9 / self.dt))
            elif unit == 'ps':
                return int(round(dur * 1e-12 / self.dt))
            else:
                # Default to dt if unknown unit
                return int(dur)
        if isinstance(op, BoxOp) and op.duration is not None:
            # BoxOp duration may be in different units
            if op.unit == "dt":
                return int(op.duration)
            elif op.unit == "s":
                return int(round(op.duration / self.dt))
            elif op.unit == "ms":
                return int(round(op.duration * 1e-3 / self.dt))
            elif op.unit == "us":
                return int(round(op.duration * 1e-6 / self.dt))
            elif op.unit == "ns":
                return int(round(op.duration * 1e-9 / self.dt))
            elif op.unit == "ps":
                return int(round(op.duration * 1e-12 / self.dt))
            elif op.unit == "expr":
                # Stretch/Expr - cannot determine statically, use fallback
                pass
            else:
                return int(op.duration)  # Assume dt
        if op.name in self.target and q_indices in self.target[op.name]:
            props = self.target[op.name][q_indices]
            if props and props.duration is not None:
                return int(round(props.duration / self.dt))
        # Warn for unknown ops but continue with fallback
        import warnings
        if op.name not in ("measure", "reset", "id", "u", "cz", "cp", "swap", "ecr", "rzz", "rx", "ry", "rz", "sx", "x", "h", "cx", "delay", "barrier", "rz"):
            warnings.warn(f"Unknown operation '{op.name}' on qubits {q_indices}, using fallback duration of 160 dt", UserWarning)
        return 160  # Fallback basis duration in dt

    def _lower_instruction(
        self,
        op,
        q_indices: Tuple[int, ...],
        start_dt: int,
        qubit_phase: Dict[int, float],
        override_ann: Optional[Any] = None,
    ) -> int:
        """
        Recursively lower an operation to channel events with frame tracking.
        
        Handles BoxOp containers, single-qubit gates, two-qubit gates, and measurements.
        """
        # Handle Qiskit 2.x BoxOp containers and inspect custom PulseEnvelopeAnnotations
        if isinstance(op, BoxOp):
            box_ann = override_ann
            for ann in op.annotations:
                if isinstance(ann, PulseEnvelopeAnnotation):
                    box_ann = ann
            cursor_dt = start_dt
            for sub_inst in op.body.data:
                sub_q = tuple(
                    q_indices[op.body.find_bit(q).index] for q in sub_inst.qubits
                )
                cursor_dt = self._lower_instruction(
                    sub_inst.operation, sub_q, cursor_dt, qubit_phase, override_ann=box_ann
                )
            box_dur = self._get_duration_dt(op, q_indices)
            return max(cursor_dt, start_dt + box_dur)

        dur_dt = self._get_duration_dt(op, q_indices)
        stop_dt = start_dt + dur_dt

        # 1. Virtual-Z Gate: 0 dt frame phase shift
        if op.name == "rz":
            lam = float(op.params[0])
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

        # 2. Single-Qubit Drive Gates (sx, x, rx)
        if len(q_indices) == 1 and op.name in ("sx", "x", "rx"):
            q0 = q_indices[0]
            if override_ann is not None:
                shape = override_ann.shape
                amp = override_ann.amp
                beta = override_ann.beta
                sigma_dt = dur_dt * override_ann.sigma_ratio
                risefall_dt = override_ann.risefall_dt
            else:
                shape = "drag"
                beta = 0.08
                sigma_dt = dur_dt * 0.25
                risefall_dt = 16
                if op.name == "sx":
                    amp = 0.45
                elif op.name == "x":
                    amp = 0.90
                else:  # Fractional rx(theta)
                    theta = float(op.params[0])
                    amp = 0.90 * (theta / np.pi)

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

        # 3. Two-Qubit Entangling Gates (cx, ecr, rzz) -> ControlChannel u_{c,t}
        elif len(q_indices) == 2 and op.name in ("cx", "ecr", "rzz"):
            c_q, t_q = q_indices
            scale = (float(op.params[0]) / (0.5 * np.pi)) if op.name == "rzz" else 1.0
            
            # Echoed Cross-Resonance: positive CR tone + echo X on control + negative CR tone
            half_dur = dur_dt // 2
            
            # First half: positive CR drive on control channel, phase-locked to TARGET frame
            self._append_event(
                ChannelEvent(
                    channel=f"u({c_q},{t_q})",
                    start_dt=start_dt,
                    duration_dt=half_dur,
                    op_name=f"{op.name}_cr+",
                    qubits=q_indices,
                    frame_phase_rad=qubit_phase[t_q],  # Phase-locked to target qubit frame!
                    shape="gaussian_square",
                    amp=complex(0.65 * scale),
                    risefall_dt=16,
                )
            )
            
            # Second half: negative CR drive (echoed)
            self._append_event(
                ChannelEvent(
                    channel=f"u({c_q},{t_q})",
                    start_dt=start_dt + half_dur,
                    duration_dt=dur_dt - half_dur,
                    op_name=f"{op.name}_cr-",
                    qubits=q_indices,
                    frame_phase_rad=qubit_phase[t_q] + np.pi,
                    shape="gaussian_square",
                    amp=complex(0.65 * scale),
                    risefall_dt=16,
                )
            )
            
            # Echo X on control qubit drive channel (for ecr)
            if op.name == "ecr":
                self._append_event(
                    ChannelEvent(
                        channel=f"d{c_q}",
                        start_dt=start_dt + half_dur,
                        duration_dt=dur_dt - half_dur,
                        op_name="ecr_echo_x",
                        qubits=(c_q,),
                        frame_phase_rad=qubit_phase[c_q],
                        shape="drag",
                        amp=0.90 + 0.0j,
                        beta=0.08,
                        sigma_dt=(dur_dt - half_dur) * 0.25,
                        risefall_dt=16,
                    )
                )

        # 4. Readout Measurement -> MeasureChannel m_q
        elif op.name == "measure":
            q0 = q_indices[0]
            self._append_event(
                ChannelEvent(
                    channel=f"m{q0}",
                    start_dt=start_dt,
                    duration_dt=dur_dt,
                    op_name="measure",
                    qubits=q_indices,
                    frame_phase_rad=0.0,
                    shape="gaussian_square",
                    amp=0.35 + 0.0j,
                    risefall_dt=24,
                )
            )

        return stop_dt

    def _append_event(self, event: ChannelEvent) -> None:
        """Append event to channel event list."""
        self.events_by_channel.setdefault(event.channel, []).append(event)

    def get_snippet(
        self, channel: str, start_dt: int = 0, length_dt: Optional[int] = None
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
        if length_dt is None:
            length_dt = max(1, self.total_duration_dt - start_dt)
        stop_dt = start_dt + length_dt

        t_global_dt = np.arange(start_dt, stop_dt, dtype=np.float64)
        time_ns = t_global_dt * self.dt * 1e9
        wave = np.zeros(length_dt, dtype=np.complex128)
        phase_trace = np.zeros(length_dt, dtype=np.float64)

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

        # Use cached starts for O(1) access, fallback to building if not cached
        starts = self._starts_by_channel.get(channel)
        if starts is None:
            starts = [e.start_dt for e in events]
        # Use max duration for proper lookback to catch long events that started earlier
        max_dur = self._max_duration_by_channel.get(channel, 0)
        # Search from start_dt - max_dur to catch long events spanning into window
        search_start = max(0, start_dt - max_dur)
        idx = bisect.bisect_left(starts, search_start)
        overlapping: List[ChannelEvent] = []

        for ev in events[idx:]:
            if ev.start_dt >= stop_dt:
                break
            ev_stop = ev.start_dt + ev.duration_dt
            if ev_stop < start_dt:
                continue
            overlapping.append(ev)
            if ev.duration_dt == 0:
                continue

            # Compute slice indices inside the local snippet window
            w_start = max(start_dt, ev.start_dt)
            w_stop = min(stop_dt, ev_stop)
            sl = slice(w_start - start_dt, w_stop - start_dt)
            t_local_dt = np.arange(w_start - ev.start_dt, w_stop - ev.start_dt, dtype=np.float64)

            if ev.shape == "drag":
                baseband = AnalyticalEnvelopes.drag(
                    t_local_dt, ev.duration_dt, ev.amp, ev.sigma_dt, ev.beta
                )
            elif ev.shape == "gaussian_square":
                baseband = AnalyticalEnvelopes.gaussian_square(
                    t_local_dt, ev.duration_dt, ev.amp, ev.risefall_dt
                )
            elif ev.shape == "virtual_z":
                continue  # Zero-duration, no waveform
            else:
                # Unknown shape - warn but continue without waveform
                import warnings
                warnings.warn(f"Unknown pulse shape '{ev.shape}' on channel {channel}, skipping", UserWarning)
                continue

            # Apply Virtual-Z frame phase rotation and digital IF carrier modulation
            carrier_phase = (
                2.0 * np.pi * self.if_freq_hz * (t_global_dt[sl] * self.dt) + ev.frame_phase_rad
            )
            wave[sl] += baseband * np.exp(1j * carrier_phase)
            phase_trace[sl] = ev.frame_phase_rad

        return WaveformSnippet(
            channel=channel,
            start_dt=start_dt,
            dt_sec=self.dt,
            time_ns=time_ns,
            wave=wave,
            phase_rad=phase_trace,
            events=overlapping,
        )

    def get_channels(self) -> List[str]:
        """Return list of all channels with events."""
        return sorted(self.events_by_channel.keys())

    def get_phase_history(self, qubit: int) -> List[Tuple[int, float]]:
        """Return phase history for a qubit as list of (dt, phase_rad)."""
        return self.phase_history.get(qubit, [])

    def export_openqasm3(self, scheduled_qc: QuantumCircuit, annotation_handlers: Optional[Dict] = None) -> str:
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
        from qiskit import qasm3
        from qiskit_waveform_sim import PulseAnnotationSerializer
        handlers = {"pulse_sim.envelope": PulseAnnotationSerializer()}
        if annotation_handlers:
            handlers.update(annotation_handlers)
        return qasm3.dumps(scheduled_qc, annotation_handlers=handlers)