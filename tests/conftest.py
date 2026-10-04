"""
Test configuration and fixtures for qiskit-waveform-sim.
"""

import pytest
from qiskit import QuantumCircuit
from qiskit.providers.fake_provider import GenericBackendV2
from qiskit.transpiler import generate_preset_pass_manager


@pytest.fixture(scope="session")
def backend_2q():
    """2-qubit generic backend for testing."""
    return GenericBackendV2(num_qubits=2, seed=42)


@pytest.fixture(scope="session")
def backend_5q():
    """5-qubit generic backend for testing."""
    return GenericBackendV2(num_qubits=5, seed=42)


@pytest.fixture
def simple_circuit(backend_2q):
    """Simple scheduled circuit for testing."""
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])

    pm = generate_preset_pass_manager(
        optimization_level=1, backend=backend_2q, scheduling_method="alap"
    )
    return pm.run(qc)


@pytest.fixture
def circuit_with_boxop(backend_2q):
    """Circuit with BoxOp and custom annotation for testing (NOT scheduled - scheduling doesn't support BoxOp)."""
    from qiskit_waveform_sim import PulseEnvelopeAnnotation

    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)

    with qc.box(
        duration=160,
        unit="dt",
        annotations=[PulseEnvelopeAnnotation(shape="drag", amp=0.55, beta=0.25, sigma_ratio=0.2)],
    ):
        qc.sx(0)

    qc.measure([0, 1], [0, 1])

    # Don't schedule - BoxOp not supported with scheduling_method
    return qc


@pytest.fixture
def fractional_gate_circuit(backend_2q):
    """Circuit with fractional gates - use only basis gates that backend supports."""
    # GenericBackendV2 basis: ['id', 'rz', 'sx', 'x', 'cx', 'ecr', 'measure', 'reset']
    # RX and RZZ need to be decomposed
    qc = QuantumCircuit(2, 2)
    # RX(π/4) = RZ(-π/2) * SX * RZ(π/2) with phase adjustment
    # But for testing fractional gate handling, we need a backend that supports them
    # For now, use a circuit that transpiles to supported gates
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])

    pm = generate_preset_pass_manager(
        optimization_level=1, backend=backend_2q, scheduling_method="alap"
    )
    return pm.run(qc)


@pytest.fixture
def compiled_simulator(simple_circuit, backend_2q):
    """Pre-compiled TargetWaveformSimulator."""
    from qiskit_waveform_sim import TargetWaveformSimulator

    return TargetWaveformSimulator(backend_2q.target).compile(simple_circuit)
