"""
Tests for core waveform simulation engine.
"""

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.transpiler import generate_preset_pass_manager

from qiskit_waveform_sim.core import (
    AnalyticalEnvelopes,
    ChannelEvent,
    TargetWaveformSimulator,
    WaveformSnippet,
)


class TestAnalyticalEnvelopes:
    """Tests for analytical envelope evaluators."""

    def test_drag_basic(self):
        """Test DRAG envelope basic properties."""
        t_dt = np.linspace(0, 160, 160)
        result = AnalyticalEnvelopes.drag(t_dt, 160, 0.5 + 0j, 40.0, 0.08)

        assert result.shape == (160,)
        assert result.dtype == np.complex128
        # Should start and end near zero (pedestal correction)
        # Allow slightly larger values due to numerical precision
        assert abs(result[0]) < 0.02
        assert abs(result[-1]) < 0.02
        # Peak should be near center
        peak_idx = np.argmax(np.abs(result))
        assert 70 < peak_idx < 90

    def test_drag_with_beta(self):
        """Test DRAG envelope with deterministic physics verification."""
        t_dt = np.linspace(0, 160, 160)
        sigma_dt = 40.0
        beta = 0.1
        amp = 0.5 + 0j
        result = AnalyticalEnvelopes.drag(t_dt, 160, amp, sigma_dt, beta)

        t_center = 80.0
        # At exactly one sigma to the left (t=40), derivative dg/dt > 0.
        # But our formula is norm_gauss + 1j*beta*deriv_term.
        # deriv_term at t=40: -((40-80)/(40**2)) * norm_gauss = (1/40) * norm_gauss.
        # So imaginary part is beta * deriv_term * amp = 0.1 * (1/40) * norm_gauss * 0.5

        idx = 40
        t_val = t_dt[idx]
        expected_gauss = np.exp(-0.5 * ((t_val - t_center) / sigma_dt) ** 2)
        pedestal = np.exp(-0.5 * (t_center / sigma_dt) ** 2)

        expected_deriv = -((t_val - t_center) / (sigma_dt**2)) * (
            expected_gauss / (1.0 - pedestal)
        )
        expected_q = beta * expected_deriv * amp.real

        np.testing.assert_allclose(result[idx].imag, expected_q, atol=1e-7)

    def test_gaussian_square_basic(self):
        """Test GaussianSquare envelope basic properties."""
        t_dt = np.linspace(0, 200, 200)
        result = AnalyticalEnvelopes.gaussian_square(t_dt, 200, 0.5 + 0j, 20)

        assert result.shape == (200,)
        assert result.dtype == np.complex128
        # Flat top region should be near amplitude
        flat_region = result[60:140]
        assert np.allclose(np.abs(flat_region), 0.5, rtol=0.05)
        # Edges should be near zero
        assert abs(result[0]) < 0.01
        assert abs(result[-1]) < 0.01

    def test_gaussian_square_zero_risefall(self):
        """Test GaussianSquare with zero risefall (should be constant)."""
        t_dt = np.linspace(0, 100, 100)
        result = AnalyticalEnvelopes.gaussian_square(t_dt, 100, 0.5 + 0j, 0)

        assert np.allclose(result, 0.5 + 0j)

    def test_envelope_scaling(self):
        """Test amplitude scaling."""
        t_dt = np.linspace(0, 160, 160)
        result = AnalyticalEnvelopes.drag(t_dt, 160, 1.0 + 0j, 40.0, 0.0)
        assert np.max(np.abs(result)) <= 1.0 + 1e-10


class TestChannelEvent:
    """Tests for ChannelEvent dataclass."""

    def test_creation(self):
        """Test ChannelEvent creation."""
        event = ChannelEvent(
            channel="d0",
            start_dt=100,
            duration_dt=160,
            op_name="sx",
            qubits=(0,),
            frame_phase_rad=0.5,
            shape="drag",
            amp=0.5 + 0j,
        )

        assert event.channel == "d0"
        assert event.start_dt == 100
        assert event.duration_dt == 160
        assert event.op_name == "sx"
        assert event.qubits == (0,)
        assert event.frame_phase_rad == 0.5
        assert event.shape == "drag"
        assert event.amp == 0.5 + 0j

    def test_immutable(self):
        """Test that ChannelEvent is frozen (immutable)."""
        event = ChannelEvent(
            channel="d0",
            start_dt=0,
            duration_dt=100,
            op_name="x",
            qubits=(0,),
            frame_phase_rad=0.0,
            shape="drag",
            amp=0.9 + 0j,
        )

        with pytest.raises(AttributeError):
            event.channel = "d1"


class TestWaveformSnippet:
    """Tests for WaveformSnippet dataclass."""

    def test_creation(self):
        """Test WaveformSnippet creation."""
        time_ns = np.linspace(0, 100, 100)
        wave = np.zeros(100, dtype=np.complex128)
        phase = np.zeros(100)

        snippet = WaveformSnippet(
            channel="d0",
            start_dt=0,
            dt_sec=0.222e-9,
            time_ns=time_ns,
            wave=wave,
            phase_rad=phase,
        )

        assert snippet.channel == "d0"
        assert snippet.start_dt == 0
        assert snippet.dt_sec == 0.222e-9
        assert len(snippet.wave) == 100
        assert len(snippet.time_ns) == 100
        assert len(snippet.phase_rad) == 100


class TestTargetWaveformSimulator:
    """Tests for TargetWaveformSimulator."""

    def test_compile_basic(self, simple_circuit, backend_2q):
        """Test basic compilation."""
        from qiskit_waveform_sim import TargetWaveformSimulator

        sim = TargetWaveformSimulator(backend_2q.target).compile(simple_circuit)

        assert sim.total_duration_dt > 0
        assert len(sim.events_by_channel) > 0
        assert "d0" in sim.events_by_channel
        # d1 may not have events if no gates on qubit 1
        # Check that at least drive channels or control channels exist
        assert any(
            ch.startswith("d") or ch.startswith("u") for ch in sim.events_by_channel
        )

    def test_compile_requires_scheduling(self, backend_2q):
        """Test that compilation fails without scheduling."""
        from qiskit_waveform_sim import TargetWaveformSimulator

        qc = QuantumCircuit(2)
        qc.h(0)
        qc.cx(0, 1)

        with pytest.raises(ValueError, match="must be scheduled"):
            TargetWaveformSimulator(backend_2q.target).compile(qc)

    def test_get_snippet_basic(self, compiled_simulator):
        """Test basic snippet extraction."""
        snippet = compiled_simulator.get_snippet("d0", start_dt=0, length_dt=500)

        assert isinstance(snippet, WaveformSnippet)
        assert snippet.channel == "d0"
        assert len(snippet.wave) == 500
        assert len(snippet.time_ns) == 500
        assert snippet.dt_sec > 0

    def test_get_snippet_windowed(self, compiled_simulator):
        """Test windowed snippet extraction (lazy evaluation)."""
        # Extract small window from large circuit
        snippet = compiled_simulator.get_snippet("d0", start_dt=1000, length_dt=100)

        assert len(snippet.wave) == 100
        assert snippet.start_dt == 1000
        assert snippet.time_ns[0] == 1000 * snippet.dt_sec * 1e9

    def test_get_snippet_empty_channel(self, compiled_simulator):
        """Test snippet for channel with no events."""
        snippet = compiled_simulator.get_snippet("u(1,0)", start_dt=0, length_dt=100)

        assert len(snippet.wave) == 100
        assert np.all(snippet.wave == 0)
        assert len(snippet.events) == 0

    def test_get_snippet_invalid_bounds(self, compiled_simulator):
        """Test that invalid bounds raise descriptive ValueErrors."""
        with pytest.raises(ValueError, match="start_dt must be non-negative"):
            compiled_simulator.get_snippet("d0", start_dt=-10, length_dt=100)

        with pytest.raises(ValueError, match="length_dt must be positive"):
            compiled_simulator.get_snippet("d0", start_dt=0, length_dt=0)

        with pytest.raises(ValueError, match="length_dt must be positive"):
            compiled_simulator.get_snippet("d0", start_dt=0, length_dt=-50)

    def test_multi_qubit_measure(self, backend_2q):
        """Test that measure instruction across multiple qubits creates events for all qubits."""
        qc = QuantumCircuit(2, 2)
        qc.measure([0, 1], [0, 1])

        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend_2q, scheduling_method="alap"
        )
        scheduled_qc = pm.run(qc)

        sim = TargetWaveformSimulator(backend_2q.target).compile(scheduled_qc)
        assert "m0" in sim.events_by_channel
        assert "m1" in sim.events_by_channel
        assert len(sim.events_by_channel["m0"]) == 1
        assert len(sim.events_by_channel["m1"]) == 1

    def test_get_channels(self, compiled_simulator):
        """Test channel listing."""
        channels = compiled_simulator.get_channels()

        assert isinstance(channels, list)
        assert "d0" in channels
        assert len(channels) > 0

    def test_phase_history(self, compiled_simulator):
        """Test phase history tracking."""
        history = compiled_simulator.get_phase_history(0)

        assert isinstance(history, list)
        assert len(history) > 0
        # First entry should be at time 0 with phase 0
        assert history[0] == (0, 0.0)

    def test_virtual_z_phase_accumulation(self, backend_2q):
        """Test Virtual-Z phase accumulation."""
        from qiskit import QuantumCircuit
        from qiskit.transpiler import generate_preset_pass_manager

        from qiskit_waveform_sim import TargetWaveformSimulator

        qc = QuantumCircuit(1)
        qc.rz(np.pi / 2, 0)
        qc.rz(np.pi / 4, 0)
        qc.sx(0)

        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend_2q, scheduling_method="alap"
        )
        scheduled = pm.run(qc)

        sim = TargetWaveformSimulator(backend_2q.target).compile(scheduled)
        history = sim.get_phase_history(0)

        # Should have initial + RZ gates (may be optimized to 1 or 2)
        assert len(history) >= 2
        # Final phase should be -3π/4 (or combined equivalent)
        final_phase = history[-1][1]
        assert np.isclose(final_phase, -3 * np.pi / 4, atol=1e-10)

    def test_if_frequency_modulation(self, simple_circuit, backend_2q):
        """Test digital IF carrier modulation."""
        from qiskit_waveform_sim import TargetWaveformSimulator

        if_freq = 50e6  # 50 MHz
        sim = TargetWaveformSimulator(backend_2q.target, if_freq_hz=if_freq).compile(
            simple_circuit
        )

        snippet = sim.get_snippet("d0", start_dt=0, length_dt=1000)

        # With IF modulation, waveform should have oscillating phase
        # Check that phase is not constant
        phase_diff = np.diff(np.angle(snippet.wave))
        # Should have non-zero phase evolution from IF
        assert np.any(np.abs(phase_diff) > 1e-3)

    def test_boxop_annotation_attachment(self):
        """Test BoxOp custom annotation attachment and QPY round-trip."""
        import io

        from qiskit import QuantumCircuit, qpy

        from qiskit_waveform_sim import (
            PulseAnnotationSerializer,
            PulseEnvelopeAnnotation,
        )

        qc = QuantumCircuit(1)
        ann = PulseEnvelopeAnnotation(
            shape="drag", amp=0.55, beta=0.25, sigma_ratio=0.2
        )

        with qc.box(duration=160, unit="dt", annotations=[ann]):
            qc.sx(0)

        # Verify annotation attached
        box_op = qc.data[0].operation
        assert hasattr(box_op, "annotations")
        assert len(box_op.annotations) == 1
        assert box_op.annotations[0] == ann

        # Test QPY round-trip
        serializer = PulseAnnotationSerializer()
        buf = io.BytesIO()
        qpy.dump(
            qc, buf, annotation_factories={"pulse_sim.envelope": serializer.as_qpy()}
        )
        buf.seek(0)
        loaded = qpy.load(
            buf, annotation_factories={"pulse_sim.envelope": serializer.as_qpy()}
        )[0]

        # Verify annotation survived
        loaded_box = loaded.data[0].operation
        assert len(loaded_box.annotations) == 1
        assert loaded_box.annotations[0] == ann

    def test_boxop_annotation_openqasm3_export(self):
        """Test BoxOp annotation exports to OpenQASM 3 with pulse pragmas."""
        from qiskit import QuantumCircuit, qasm3

        from qiskit_waveform_sim import (
            PulseAnnotationSerializer,
            PulseEnvelopeAnnotation,
        )

        qc = QuantumCircuit(1)
        ann = PulseEnvelopeAnnotation(shape="drag", amp=0.55, beta=0.25)

        with qc.box(duration=160, unit="dt", annotations=[ann]):
            qc.sx(0)

        qasm3_str = qasm3.dumps(
            qc, annotation_handlers={"pulse_sim.envelope": PulseAnnotationSerializer()}
        )

        assert "OPENQASM 3" in qasm3_str
        assert "pulse_sim.envelope" in qasm3_str
        assert "drag" in qasm3_str
        assert "0.55" in qasm3_str
        assert "0.25" in qasm3_str

    def test_export_openqasm3(self, simple_circuit, backend_2q):
        """Test OpenQASM 3 export with annotations."""
        from qiskit_waveform_sim import TargetWaveformSimulator

        sim = TargetWaveformSimulator(backend_2q.target).compile(simple_circuit)
        qasm3_str = sim.export_openqasm3(simple_circuit)

        assert isinstance(qasm3_str, str)
        assert len(qasm3_str) > 0
        assert "OPENQASM 3" in qasm3_str


DT = 0.222e-9


def _fractional_target():
    """Target with native fractional rx/rzz (like IBM fractional-gate backends)."""
    from qiskit.circuit import Parameter
    from qiskit.circuit.library import Measure, RXGate, RZGate, RZZGate, SXGate
    from qiskit.transpiler import InstructionProperties, Target

    theta = Parameter("theta")
    one_q = {(q,): InstructionProperties(duration=160 * DT) for q in range(2)}
    target = Target(num_qubits=2, dt=DT)
    target.add_instruction(RXGate(theta), dict(one_q))
    target.add_instruction(SXGate(), dict(one_q))
    target.add_instruction(
        RZGate(theta), {(q,): InstructionProperties(duration=0.0) for q in range(2)}
    )
    target.add_instruction(
        RZZGate(theta), {(0, 1): InstructionProperties(duration=1600 * DT)}
    )
    target.add_instruction(
        Measure(), {(q,): InstructionProperties(duration=1600 * DT) for q in range(2)}
    )
    return target


def _schedule_on(target, qc):
    pm = generate_preset_pass_manager(
        optimization_level=0, target=target, scheduling_method="alap"
    )
    return pm.run(qc)


def _phase_at(sim, qubit, t_dt):
    """Frame phase of `qubit` in effect at time t_dt, read from phase history."""
    return [p for t, p in sim.get_phase_history(qubit) if t <= t_dt][-1]


class TestFramesAnglesAndWindows:
    """Regression tests for CR frame, fractional angles and snippet windows."""

    def test_cr_pulse_uses_target_frame(self, backend_2q):
        qc = QuantumCircuit(2)
        qc.rz(1.0, 0)
        qc.rz(0.3, 1)
        qc.cx(0, 1)
        sim = TargetWaveformSimulator(backend_2q.target).compile(
            generate_preset_pass_manager(
                optimization_level=1, backend=backend_2q, scheduling_method="alap"
            ).run(qc)
        )

        cr_plus = next(
            e for e in sim.events_by_channel["u(0,1)"] if e.op_name.endswith("cr+")
        )
        target_phase = _phase_at(sim, 1, cr_plus.start_dt)
        assert target_phase != _phase_at(sim, 0, cr_plus.start_dt)
        assert cr_plus.frame_phase_rad == pytest.approx(target_phase)

        snippet = sim.get_snippet("u(0,1)", cr_plus.start_dt, cr_plus.duration_dt)
        assert snippet.phase_rad[cr_plus.duration_dt // 2] == pytest.approx(
            target_phase
        )

    def test_large_rx_angle_does_not_crash(self):
        target = _fractional_target()
        qc = QuantumCircuit(1)
        qc.rx(4.0, 0)

        sim = TargetWaveformSimulator(target).compile(_schedule_on(target, qc))

        (ev,) = [e for e in sim.events_by_channel["d0"] if e.op_name == "rx"]
        # rx(4.0) == rx(4.0 - 2*pi): amplitude follows the wrapped angle
        assert ev.amp.real == pytest.approx(0.90 * (4.0 - 2 * np.pi) / np.pi)

    def test_large_rzz_angle_clipped_with_warning(self):
        target = _fractional_target()
        qc = QuantumCircuit(2)
        qc.rzz(np.pi, 0, 1)

        with pytest.warns(UserWarning, match="clipped"):
            sim = TargetWaveformSimulator(target).compile(_schedule_on(target, qc))

        amps = [abs(e.amp) for e in sim.events_by_channel["u(0,1)"]]
        assert amps and all(a == pytest.approx(1.0) for a in amps)

    def test_unbound_parameter_raises_clear_error(self):
        from qiskit.circuit import Parameter

        target = _fractional_target()
        qc = QuantumCircuit(1)
        qc.rx(Parameter("a"), 0)
        scheduled = _schedule_on(target, qc)

        with pytest.raises(ValueError, match="unbound"):
            TargetWaveformSimulator(target).compile(scheduled)

    def test_phase_trace_holds_after_circuit_end(self, backend_2q):
        qc = QuantumCircuit(1)
        qc.rz(1.0, 0)
        qc.sx(0)
        sim = TargetWaveformSimulator(backend_2q.target).compile(
            generate_preset_pass_manager(
                optimization_level=1, backend=backend_2q, scheduling_method="alap"
            ).run(qc)
        )
        final_phase = sim.get_phase_history(0)[-1][1]
        assert final_phase != 0.0

        snippet = sim.get_snippet("d0", sim.total_duration_dt + 500, 100)

        assert np.allclose(snippet.phase_rad, final_phase)

    def test_snippet_excludes_events_ending_at_window_start(self, compiled_simulator):
        pulse = next(
            e for e in compiled_simulator.events_by_channel["d0"] if e.duration_dt > 0
        )

        snippet = compiled_simulator.get_snippet(
            "d0", pulse.start_dt + pulse.duration_dt, 10
        )

        assert pulse not in snippet.events


class TestGateCoverage:
    """Every pulse-bearing gate either produces a waveform or says why not."""

    def test_cz_gate_produces_control_channel_waveform(self):
        from qiskit.providers.fake_provider import GenericBackendV2

        backend = GenericBackendV2(
            num_qubits=2, basis_gates=["cz", "id", "rz", "sx", "x"], seed=42
        )
        qc = QuantumCircuit(2)
        qc.cz(0, 1)
        scheduled = generate_preset_pass_manager(
            optimization_level=0, backend=backend, scheduling_method="alap"
        ).run(qc)

        sim = TargetWaveformSimulator(backend.target).compile(scheduled)

        cz_events = [
            e for e in sim.events_by_channel.get("u(0,1)", []) if e.op_name == "cz"
        ]
        assert len(cz_events) == 1
        ev = cz_events[0]
        snippet = sim.get_snippet("u(0,1)", ev.start_dt, ev.duration_dt)
        assert np.max(np.abs(snippet.wave)) > 0.1

    def test_gate_without_waveform_model_warns(self):
        from qiskit.circuit.library import SwapGate
        from qiskit.transpiler import InstructionProperties

        target = _fractional_target()
        target.add_instruction(
            SwapGate(), {(0, 1): InstructionProperties(duration=320 * DT)}
        )
        qc = QuantumCircuit(2)
        qc.swap(0, 1)
        scheduled = _schedule_on(target, qc)

        with pytest.warns(UserWarning, match="'swap'.*no waveform model"):
            TargetWaveformSimulator(target).compile(scheduled)

    def test_idle_gates_do_not_warn(self, backend_2q):
        import warnings

        qc = QuantumCircuit(1)
        qc.id(0)
        scheduled = generate_preset_pass_manager(
            optimization_level=0, backend=backend_2q, scheduling_method="alap"
        ).run(qc)

        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            TargetWaveformSimulator(backend_2q.target).compile(scheduled)


def _hand_scheduled(qc, start_times):
    """Attach start times directly: Qiskit's scheduler rejects circuits with boxes."""
    qc._op_start_times = list(start_times)
    return qc


class TestBoxLowering:
    """BoxOp timing and annotation overrides (hand-scheduled circuits)."""

    def test_box_parallel_instructions_not_serialized(self, backend_2q):
        qc = QuantumCircuit(2)
        with qc.box():
            qc.sx(0)
            qc.sx(1)

        sim = TargetWaveformSimulator(backend_2q.target).compile(
            _hand_scheduled(qc, [0])
        )

        starts = {
            ch: [e.start_dt for e in sim.events_by_channel[ch] if e.duration_dt > 0]
            for ch in ("d0", "d1")
        }
        assert starts == {"d0": [0], "d1": [0]}

    def test_single_gate_box_uses_box_duration(self, backend_2q):
        from qiskit_waveform_sim import PulseEnvelopeAnnotation

        qc = QuantumCircuit(1)
        ann = PulseEnvelopeAnnotation(
            shape="drag", amp=0.55, beta=0.25, sigma_ratio=0.2
        )
        with qc.box(duration=160, unit="dt", annotations=[ann]):
            qc.sx(0)

        sim = TargetWaveformSimulator(backend_2q.target).compile(
            _hand_scheduled(qc, [0])
        )

        (ev,) = [e for e in sim.events_by_channel["d0"] if e.op_name == "sx"]
        assert (ev.duration_dt, ev.sigma_dt, ev.amp, ev.beta) == (160, 32.0, 0.55, 0.25)
        assert sim.total_duration_dt == 160

    def test_box_without_duration_no_unknown_warning(self, backend_2q):
        import warnings

        qc = QuantumCircuit(1)
        with qc.box():
            qc.sx(0)
        sx_dur = round(backend_2q.target["sx"][(0,)].duration / backend_2q.target.dt)

        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            sim = TargetWaveformSimulator(backend_2q.target).compile(
                _hand_scheduled(qc, [0])
            )

        assert sim.total_duration_dt == sx_dur

    def test_box_annotation_applies_to_two_qubit_gate(self, backend_2q):
        from qiskit_waveform_sim import PulseEnvelopeAnnotation

        qc = QuantumCircuit(2)
        ann = PulseEnvelopeAnnotation(shape="gaussian_square", amp=0.8, risefall_dt=30)
        with qc.box(duration=300, unit="dt", annotations=[ann]):
            qc.cx(0, 1)

        sim = TargetWaveformSimulator(backend_2q.target).compile(
            _hand_scheduled(qc, [0])
        )

        cr = sim.events_by_channel["u(0,1)"]
        assert [(e.amp, e.risefall_dt) for e in cr] == [(0.8, 30), (0.8, 30)]
        assert sum(e.duration_dt for e in cr) == 300


@pytest.mark.parametrize(
    ("duration", "unit", "expected_dt"),
    [
        (100, "dt", 100),
        (1e-6, "s", 4505),
        (1e-3, "ms", 4505),
        (1.0, "us", 4505),
        (10.0, "ns", 45),
        (10000.0, "ps", 45),
    ],
)
def test_unit_conversion_for_delay_units(backend_2q, duration, unit, expected_dt):
    assert backend_2q.target.dt == pytest.approx(0.222e-9)
    qc = QuantumCircuit(1)
    qc.delay(duration, 0, unit=unit)

    sim = TargetWaveformSimulator(backend_2q.target).compile(_hand_scheduled(qc, [0]))

    assert sim.total_duration_dt == expected_dt


def test_sized_box_gate_fits_after_leading_delay(backend_2q):
    """A delay inside a fixed-duration box shortens the gate, never the box."""
    qc = QuantumCircuit(1)
    with qc.box(duration=400, unit="dt"):
        qc.delay(100, 0)
        qc.x(0)

    sim = TargetWaveformSimulator(backend_2q.target).compile(_hand_scheduled(qc, [0]))

    (ev,) = [e for e in sim.events_by_channel["d0"] if e.op_name == "x"]
    assert (ev.start_dt, ev.duration_dt) == (100, 300)
    assert sim.total_duration_dt == 400


def test_default_cr_event_metadata_unchanged(compiled_simulator):
    """Un-annotated CR events keep the pre-refactor sigma/beta metadata."""
    cr = compiled_simulator.events_by_channel["u(0,1)"]

    assert cr and all((e.sigma_dt, e.beta) == (16.0, 0.0) for e in cr)


class TestChannelValidation:
    """Channel parsing and the measure tone's own frame."""

    @staticmethod
    def _compiled(backend_2q):
        qc = QuantumCircuit(2, 1)
        qc.rz(1.0, 0)
        qc.sx(0)
        qc.measure(0, 0)
        scheduled = generate_preset_pass_manager(
            optimization_level=0, backend=backend_2q, scheduling_method="alap"
        ).run(qc)
        return TargetWaveformSimulator(backend_2q.target).compile(scheduled)

    def test_measure_channel_phase_is_zero(self, backend_2q):
        sim = self._compiled(backend_2q)
        snip = sim.get_snippet("m0")
        assert np.all(snip.phase_rad == 0.0)

    def test_drive_channel_phase_still_tracks_rz(self, backend_2q):
        sim = self._compiled(backend_2q)
        snip = sim.get_snippet("d0")
        assert snip.phase_rad[-1] == pytest.approx(-1.0)

    @pytest.mark.parametrize("name", ["dfoo", "zzz", "u(0 1)", "d", "u(0,1", "d-1"])
    def test_malformed_channel_raises(self, backend_2q, name):
        sim = self._compiled(backend_2q)
        with pytest.raises(ValueError, match="Unknown channel"):
            sim.get_snippet(name)

    def test_out_of_range_qubit_raises(self, backend_2q):
        sim = self._compiled(backend_2q)
        with pytest.raises(ValueError):
            sim.get_snippet("d99")
        with pytest.raises(ValueError):
            sim.get_snippet("u(0,99)")

    def test_unused_wellformed_channel_is_zero(self, backend_2q):
        sim = self._compiled(backend_2q)
        snip = sim.get_snippet("u(1,0)")
        assert np.all(snip.wave == 0)


class TestAnnotatedRxAndZeroWidth:
    def test_annotated_rx_scales_with_theta(self, backend_2q):
        from qiskit_waveform_sim import PulseEnvelopeAnnotation

        for theta, expected in [(np.pi / 4, 0.2), (np.pi / 2, 0.4), (np.pi, 0.8)]:
            qc = QuantumCircuit(1)
            ann = PulseEnvelopeAnnotation(shape="drag", amp=0.8, beta=0.1)
            with qc.box(duration=160, unit="dt", annotations=[ann]):
                qc.rx(theta, 0)
            sim = TargetWaveformSimulator(backend_2q.target).compile(
                _hand_scheduled(qc, [0])
            )
            (ev,) = [e for e in sim.events_by_channel["d0"] if e.op_name == "rx"]
            assert abs(ev.amp) == pytest.approx(expected)

    def test_annotated_sx_amp_unchanged(self, backend_2q):
        from qiskit_waveform_sim import PulseEnvelopeAnnotation

        qc = QuantumCircuit(1)
        ann = PulseEnvelopeAnnotation(shape="drag", amp=0.8, beta=0.1)
        with qc.box(duration=160, unit="dt", annotations=[ann]):
            qc.sx(0)
        sim = TargetWaveformSimulator(backend_2q.target).compile(
            _hand_scheduled(qc, [0])
        )
        (ev,) = [e for e in sim.events_by_channel["d0"] if e.op_name == "sx"]
        assert abs(ev.amp) == pytest.approx(0.8)

    def test_zero_duration_envelopes_are_zero_without_warnings(self):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            a = AnalyticalEnvelopes.drag(np.arange(0.0), 0, 0.5, 0.0, 0.1)
            b = AnalyticalEnvelopes.drag(np.arange(1.0), 0, 0.5, 4.0, 0.1)
            c = AnalyticalEnvelopes.gaussian_square(np.arange(1.0), 0, 0.5, 16)
        assert a.shape == (0,)
        assert np.all(b == 0) and b.dtype == np.complex128
        assert np.all(c == 0) and c.dtype == np.complex128

    def test_drag_nonpositive_sigma_raises(self):
        with pytest.raises(ValueError, match="sigma_dt"):
            AnalyticalEnvelopes.drag(np.arange(4.0), 4, 0.5, 0.0, 0.1)
