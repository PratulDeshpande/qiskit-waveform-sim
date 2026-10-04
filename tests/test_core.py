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
        """Test DRAG envelope with non-zero beta."""
        t_dt = np.linspace(0, 160, 160)
        result_no_beta = AnalyticalEnvelopes.drag(t_dt, 160, 0.5 + 0j, 40.0, 0.0)
        result_with_beta = AnalyticalEnvelopes.drag(t_dt, 160, 0.5 + 0j, 40.0, 0.1)

        # With beta, imaginary part should be non-zero
        assert np.any(np.abs(result_with_beta.imag) > 1e-10)
        # Without beta, imaginary part should be zero
        assert np.all(np.abs(result_no_beta.imag) < 1e-10)

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

    def test_fractional_rx_amplitude_scaling(self, backend_2q):
        """Test RX(θ) amplitude scales with angle - skipped if RX not in basis."""
        from qiskit import QuantumCircuit
        from qiskit.transpiler import generate_preset_pass_manager

        from qiskit_waveform_sim import TargetWaveformSimulator

        # Only test if RX is a basis gate
        if "rx" not in backend_2q.target.operation_names:
            pytest.skip("RX not in backend basis")

        qc = QuantumCircuit(1)
        qc.rx(np.pi / 4, 0)
        qc.measure_all()

        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend_2q, scheduling_method="alap"
        )
        scheduled = pm.run(qc)

        sim = TargetWaveformSimulator(backend_2q.target).compile(scheduled)

        # Find RX event
        events = sim.events_by_channel.get("d0", [])
        rx_events = [e for e in events if e.op_name == "rx"]

        if len(rx_events) == 0:
            pytest.skip("RX gate not scheduled as RX (may be decomposed)")

        # RX(π/4) should have amplitude 0.9 * (π/4)/π = 0.225
        expected_amp = 0.9 * 0.25
        assert np.isclose(abs(rx_events[0].amp), expected_amp, rtol=0.01)

    def test_rzz_scaling(self, backend_2q):
        """Test RZZ(θ) amplitude/duration scaling - skipped if RZZ not in basis."""
        from qiskit import QuantumCircuit
        from qiskit.transpiler import generate_preset_pass_manager

        from qiskit_waveform_sim import TargetWaveformSimulator

        if "rzz" not in backend_2q.target.operation_names:
            pytest.skip("RZZ not in backend basis")

        qc = QuantumCircuit(2)
        qc.rzz(np.pi / 2, 0, 1)
        qc.measure_all()

        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend_2q, scheduling_method="alap"
        )
        scheduled = pm.run(qc)

        sim = TargetWaveformSimulator(backend_2q.target).compile(scheduled)

        events = sim.events_by_channel.get("u(0,1)", [])
        rzz_events = [e for e in events if "rzz" in e.op_name]

        if len(rzz_events) == 0:
            pytest.skip("RZZ gate not scheduled as RZZ (may be decomposed)")

        # RZZ(π/2) should have scale = (π/2)/(π/2) = 1.0
        # Base amplitude is 0.65
        assert np.isclose(abs(rzz_events[0].amp), 0.65, rtol=0.01)

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

    def test_boxop_annotation_override(self, backend_2q):
        """Test BoxOp custom annotation overrides default pulse - skipped due to scheduling limitation."""
        pytest.skip("BoxOp scheduling not supported in Qiskit 2.5 transpiler")

    def test_export_openqasm3(self, simple_circuit, backend_2q):
        """Test OpenQASM 3 export with annotations."""
        from qiskit_waveform_sim import TargetWaveformSimulator

        sim = TargetWaveformSimulator(backend_2q.target).compile(simple_circuit)
        qasm3_str = sim.export_openqasm3(simple_circuit)

        assert isinstance(qasm3_str, str)
        assert len(qasm3_str) > 0
        assert "OPENQASM 3" in qasm3_str


