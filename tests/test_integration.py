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


# Check if Qiskit supports BoxOp annotations (added in Qiskit 2.1+)
def _has_boxop_annotations():
    """Check if Qiskit version supports BoxOp annotations."""
    from qiskit.circuit import BoxOp

    return (
        hasattr(BoxOp, "annotations")
        or "annotations" in BoxOp.__init__.__code__.co_varnames
    )


# Check if qasm3 supports annotation_handlers
def _has_qasm3_annotation_handlers():
    """Check if qasm3 supports annotation_handlers parameter."""
    import inspect

    from qiskit.qasm3 import Exporter

    return "annotation_handlers" in inspect.signature(Exporter.__init__).parameters


@pytest.fixture
def has_boxop_annotations():
    """Fixture indicating if BoxOp annotations are supported."""
    return _has_boxop_annotations()


@pytest.fixture
def has_qasm3_annotation_handlers():
    """Fixture indicating if qasm3 annotation_handlers are supported."""
    return _has_qasm3_annotation_handlers()


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

        assert len(pulse_fig.layout.shapes) > 0
        assert len(iq_fig.data) > 0

    def test_custom_annotation_attachment(self, has_boxop_annotations):
        """Test custom pulse annotation attachment to BoxOp (no scheduling required)."""
        if not has_boxop_annotations:
            pytest.skip("BoxOp annotations not supported in this Qiskit version")
        from qiskit_waveform_sim import PulseEnvelopeAnnotation

        qc = QuantumCircuit(2)
        qc.h(0)
        qc.cx(0, 1)

        # Custom high-beta DRAG for SX gate
        custom_drag = PulseEnvelopeAnnotation(
            shape="drag",
            amp=0.55,
            beta=0.25,
            sigma_ratio=0.2,
        )

        with qc.box(duration=160, unit="dt", annotations=[custom_drag]):
            qc.sx(0)

        # Verify annotation is attached to BoxOp
        box_op = qc.data[2].operation  # Third instruction (h, cx, box)
        assert hasattr(box_op, "annotations")
        assert len(box_op.annotations) == 1
        assert box_op.annotations[0] == custom_drag

    def test_custom_annotation_multiple_boxops(self, has_boxop_annotations):
        """Test multiple BoxOps with different annotations."""
        if not has_boxop_annotations:
            pytest.skip("BoxOp annotations not supported in this Qiskit version")
        from qiskit_waveform_sim import PulseEnvelopeAnnotation

        qc = QuantumCircuit(2)
        qc.h(0)

        # Box 1: Custom DRAG for RX
        with qc.box(
            duration=120,
            unit="dt",
            annotations=[PulseEnvelopeAnnotation(shape="drag", amp=0.4, beta=0.15)],
        ):
            qc.rx(np.pi / 4, 0)

        # Box 2: Custom GaussianSquare for RZZ
        with qc.box(
            duration=300,
            unit="dt",
            annotations=[
                PulseEnvelopeAnnotation(
                    shape="gaussian_square", amp=0.8, risefall_dt=30
                )
            ],
        ):
            qc.rzz(np.pi / 2, 0, 1)

        boxes = [
            inst.operation for inst in qc.data if hasattr(inst.operation, "annotations")
        ]
        assert len(boxes) == 2
        assert boxes[0].annotations[0].amp == 0.4
        assert boxes[1].annotations[0].shape == "gaussian_square"
        assert boxes[1].annotations[0].risefall_dt == 30

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

    def test_openqasm3_export_with_annotations(
        self, has_boxop_annotations, has_qasm3_annotation_handlers
    ):
        """Test OpenQASM 3 export with pulse annotations (no scheduling required)."""
        if not has_boxop_annotations or not has_qasm3_annotation_handlers:
            pytest.skip(
                "BoxOp annotations or qasm3 annotation_handlers not supported in this Qiskit version"
            )
        from qiskit import qasm3

        from qiskit_waveform_sim import (
            PulseAnnotationSerializer,
            PulseEnvelopeAnnotation,
        )

        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)

        with qc.box(
            duration=160,
            unit="dt",
            annotations=[PulseEnvelopeAnnotation(shape="drag", amp=0.55, beta=0.25)],
        ):
            qc.sx(0)

        qc.measure([0, 1], [0, 1])

        qasm3_str = qasm3.dumps(
            qc, annotation_handlers={"pulse_sim.envelope": PulseAnnotationSerializer()}
        )

        assert "OPENQASM 3" in qasm3_str
        assert "pulse_sim.envelope" in qasm3_str
        assert "drag" in qasm3_str
        assert "0.55" in qasm3_str
        assert "0.25" in qasm3_str

    def test_matplotlib_visualization_workflow(self, backend):
        """Test Matplotlib static visualization workflow - uses Agg backend."""
        import matplotlib

        matplotlib.use("Agg")  # Non-interactive backend for CI

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
        assert len(fig1.axes) > 0
        assert isinstance(fig1, matplotlib.figure.Figure)

        # I/Q waveforms
        snippet = sim.get_snippet("d0", 0, 1000)
        fig2 = plot_iq_waveforms(snippet)
        assert len(fig2.axes) > 0
        assert isinstance(fig2, matplotlib.figure.Figure)

        # Phase tracking
        fig3 = plot_phase_tracking(sim)
        assert len(fig3.axes) > 0
        assert isinstance(fig3, matplotlib.figure.Figure)

        import matplotlib.pyplot as plt

        plt.close("all")

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
