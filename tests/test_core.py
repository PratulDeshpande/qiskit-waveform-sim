"""
Tests for core waveform simulation engine.
"""

import numpy as np
import pytest
from qiskit import QuantumCircuit

from qiskit_waveform_sim.core import (
    AnalyticalEnvelopes,
    ChannelEvent,
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
        snippet = compiled_simulator.get_snippet(
            "nonexistent", start_dt=0, length_dt=100
        )

        assert len(snippet.wave) == 100
        assert np.all(snippet.wave == 0)
        assert len(snippet.events) == 0

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
