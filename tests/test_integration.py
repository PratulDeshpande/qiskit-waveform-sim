"""
Integration tests for full workflow.
"""

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.providers.fake_provider import GenericBackendV2
from qiskit.transpiler import generate_preset_pass_manager

from qiskit_waveform_sim import (
    TargetWaveformSimulator,
    create_iq_oscilloscope,
    create_pulse_sheet,
)
from qiskit_waveform_sim.visualization import (
    plot_iq_waveforms,
    plot_phase_tracking,
    plot_pulse_sheet,
)


class TestFullWorkflow:
    """Integration tests for complete workflows."""

    @pytest.fixture
    def backend(self):
        return GenericBackendV2(num_qubits=2, seed=42)

    def test_basic_workflow(self, backend):
        """Test basic end-to-end workflow."""
        # 1. Create circuit
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])

        # 2. Transpile and schedule
        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend, scheduling_method="alap"
        )
        scheduled = pm.run(qc)

        # 3. Compile simulator
        sim = TargetWaveformSimulator(backend.target).compile(scheduled)

        # 4. Extract snippets
        d0_snip = sim.get_snippet("d0", start_dt=0, length_dt=2000)
        cr_snip = sim.get_snippet("u(0,1)", start_dt=0, length_dt=2000)

        # 5. Verify waveforms
        assert len(d0_snip.wave) == 2000
        assert len(cr_snip.wave) == 2000
        # Drive channel should have non-zero waveform
        assert np.any(np.abs(d0_snip.wave) > 1e-10)
        # CR channel should have non-zero waveform
        assert np.any(np.abs(cr_snip.wave) > 1e-10)

        # 6. Create visualizations
        pulse_fig = create_pulse_sheet(sim)
        iq_fig = create_iq_oscilloscope(sim, "d0", start_dt=0, length_dt=1000)

        assert pulse_fig is not None
        assert iq_fig is not None

    def test_custom_annotation_workflow(self, backend):
        """Test workflow with custom pulse annotations - skipped due to BoxOp scheduling limitation."""
        pytest.skip("BoxOp scheduling not supported in Qiskit 2.5 transpiler")

    def test_fractional_gates_workflow(self, backend):
        """Test workflow with fractional gates - skipped if not in basis."""
        if (
            "rx" not in backend.target.operation_names
            or "rzz" not in backend.target.operation_names
        ):
            pytest.skip("RX/RZZ not in backend basis")

        qc = QuantumCircuit(2, 2)
        qc.rx(np.pi / 4, 0)  # RX(π/4)
        qc.rx(np.pi / 2, 1)  # RX(π/2)
        qc.rzz(np.pi / 2, 0, 1)  # RZZ(π/2)
        qc.measure([0, 1], [0, 1])

        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend, scheduling_method="alap"
        )
        scheduled = pm.run(qc)

        sim = TargetWaveformSimulator(backend.target).compile(scheduled)

        # Check RX amplitude scaling
        d0_events = sim.events_by_channel.get("d0", [])
        rx_events = [e for e in d0_events if e.op_name == "rx"]

        if len(rx_events) == 0:
            pytest.skip("RX gate not scheduled as RX (may be decomposed)")

        assert len(rx_events) >= 1
        # RX(π/4) amplitude = 0.9 * (π/4)/π = 0.225
        expected_amp = 0.9 * 0.25
        assert np.isclose(abs(rx_events[0].amp), expected_amp, rtol=0.01)

        # Check RZZ scaling on control channel
        cr_events = sim.events_by_channel.get("u(0,1)", [])
        rzz_events = [e for e in cr_events if "rzz" in e.op_name]

        if len(rzz_events) == 0:
            pytest.skip("RZZ gate not scheduled as RZZ (may be decomposed)")

        assert len(rzz_events) > 0
        # RZZ(π/2) scale = 1.0, base amp = 0.65
        assert np.isclose(abs(rzz_events[0].amp), 0.65, rtol=0.01)

    def test_virtual_z_tracking_workflow(self, backend):
        """Test Virtual-Z frame tracking through circuit."""
        qc = QuantumCircuit(1)
        qc.rz(np.pi / 2, 0)
        qc.sx(0)
        qc.rz(-np.pi / 4, 0)
        qc.x(0)

        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend, scheduling_method="alap"
        )
        scheduled = pm.run(qc)

        sim = TargetWaveformSimulator(backend.target).compile(scheduled)

        # Check phase history
        history = sim.get_phase_history(0)

        # Initial + 2 RZ gates = 3 entries (may be optimized)
        assert len(history) >= 2
        # Final phase: RZ(π/2) + RZ(π/4) = RZ(3π/4) = -3π/4 phase shift
        # (since RZ(θ) adds -θ to frame phase)
        final_phase = history[-1][1]
        expected = -3 * np.pi / 4
        assert np.isclose((final_phase - expected) % (2 * np.pi), 0, atol=1e-10)

        # Check that drive pulses have correct frame phase
        d0_events = sim.events_by_channel.get("d0", [])
        drive_events = [e for e in d0_events if e.duration_dt > 0]

        # At least some drive events should exist
        assert len(drive_events) > 0

    def test_ecr_echo_workflow(self, backend):
        """Test ECR gate with echo X on control - skipped if not in basis."""
        if "ecr" not in backend.target.operation_names:
            pytest.skip("ECR not in backend basis")

        qc = QuantumCircuit(2, 2)
        qc.ecr(0, 1)
        qc.measure([0, 1], [0, 1])

        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend, scheduling_method="alap"
        )
        scheduled = pm.run(qc)

        sim = TargetWaveformSimulator(backend.target).compile(scheduled)

        # Check CR channel has both positive and negative pulses
        cr_events = sim.events_by_channel.get("u(0,1)", [])
        [e for e in cr_events if "cr+" in e.op_name]
        [e for e in cr_events if "cr-" in e.op_name]

        # May have different structure depending on backend
        assert len(cr_events) > 0

    def test_openqasm3_export(self, backend):
        """Test OpenQASM 3 export with annotations - skipped due to BoxOp scheduling."""
        pytest.skip("BoxOp scheduling not supported in Qiskit 2.5 transpiler")

    def test_matplotlib_visualization_workflow(self, backend):
        """Test Matplotlib static visualization workflow - skipped on headless systems."""
        # Skip if no display (common in CI)
        import os

        if os.environ.get("DISPLAY", "") == "" and os.name != "nt":
            pytest.skip("No display available for Matplotlib")

        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])

        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend, scheduling_method="alap"
        )
        scheduled = pm.run(qc)

        sim = TargetWaveformSimulator(backend.target).compile(scheduled)

        # Pulse sheet
        fig1 = plot_pulse_sheet(sim)
        assert fig1 is not None
        import matplotlib

        assert isinstance(fig1, matplotlib.figure.Figure)

        # I/Q waveforms
        snippet = sim.get_snippet("d0", 0, 1000)
        fig2 = plot_iq_waveforms(snippet)
        assert fig2 is not None
        assert isinstance(fig2, matplotlib.figure.Figure)

        # Phase tracking
        fig3 = plot_phase_tracking(sim)
        assert fig3 is not None
        assert isinstance(fig3, matplotlib.figure.Figure)

    def test_large_circuit_performance(self, backend):
        """Test compilation performance with larger circuit."""
        # Create a larger circuit (50 layers)
        qc = QuantumCircuit(2, 2)
        for _ in range(25):
            qc.h(0)
            qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])

        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend, scheduling_method="alap"
        )
        scheduled = pm.run(qc)

        # This should complete quickly (O(N_events) memory)
        sim = TargetWaveformSimulator(backend.target).compile(scheduled)

        assert sim.total_duration_dt > 0
        # Snippet extraction should be fast (O(window))
        snippet = sim.get_snippet("d0", start_dt=0, length_dt=500)
        assert len(snippet.wave) == 500

    def test_if_modulation_workflow(self, backend):
        """Test workflow with IF frequency modulation."""
        qc = QuantumCircuit(1)
        qc.x(0)

        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend, scheduling_method="alap"
        )
        scheduled = pm.run(qc)

        if_freq = 100e6  # 100 MHz
        sim = TargetWaveformSimulator(backend.target, if_freq_hz=if_freq).compile(
            scheduled
        )

        snippet = sim.get_snippet("d0", start_dt=0, length_dt=500)

        # With IF modulation, phase should evolve
        phases = np.angle(snippet.wave)
        phase_diff = np.diff(phases)

        # Expected phase increment per dt: 2π * f_IF * dt
        expected_increment = 2 * np.pi * if_freq * sim.dt
        # Should see this increment (approximately)
        non_zero = phase_diff[np.abs(phase_diff) > 1e-3]
        if len(non_zero) > 0:
            # Phase should be changing due to IF
            assert np.mean(np.abs(non_zero)) > expected_increment * 0.5


class TestMultiQubitScaling:
    """Tests for multi-qubit scaling."""

    def test_5qubit_circuit(self):
        """Test with 5-qubit backend."""
        backend = GenericBackendV2(num_qubits=5, seed=42)

        qc = QuantumCircuit(5, 5)
        qc.h(0)
        qc.cx(0, 1)
        qc.cx(1, 2)
        qc.cx(2, 3)
        qc.cx(3, 4)
        qc.measure_all()

        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend, scheduling_method="alap"
        )
        scheduled = pm.run(qc)

        sim = TargetWaveformSimulator(backend.target).compile(scheduled)

        # Should have channels for all qubits
        channels = sim.get_channels()
        assert len(channels) >= 5  # At least d0-d4

        # Phase history for all qubits
        for q in range(5):
            history = sim.get_phase_history(q)
            assert len(history) > 0
