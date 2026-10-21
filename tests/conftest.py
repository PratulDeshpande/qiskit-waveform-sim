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
def compiled_simulator(simple_circuit, backend_2q):
    """Pre-compiled TargetWaveformSimulator."""
    from qiskit_waveform_sim import TargetWaveformSimulator

    return TargetWaveformSimulator(backend_2q.target).compile(simple_circuit)
