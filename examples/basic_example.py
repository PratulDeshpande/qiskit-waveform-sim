#!/usr/bin/env python3
"""
Basic example: From circuit to I/Q waveforms.

This example demonstrates the minimal workflow.
"""

import numpy as np
from qiskit import QuantumCircuit
from qiskit.providers.fake_provider import GenericBackendV2
from qiskit.transpiler import generate_preset_pass_manager

from qiskit_waveform_sim import TargetWaveformSimulator
from qiskit_waveform_sim.visualization import show_iq_oscilloscope, show_pulse_sheet


def main():
    # 1. Backend and circuit
    backend = GenericBackendV2(num_qubits=2, seed=42)

    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])

    # 2. Transpile and schedule
    pm = generate_preset_pass_manager(
        optimization_level=1, backend=backend, scheduling_method="alap"
    )
    scheduled_qc = pm.run(qc)

    # 3. Compile simulator
    sim = TargetWaveformSimulator(backend.target).compile(scheduled_qc)

    print(f"Circuit duration: {sim.total_duration_dt} dt")
    print(f"Channels: {sim.get_channels()}")

    # 4. Extract waveforms
    d0_snip = sim.get_snippet("d0", start_dt=0, length_dt=2000)
    cr_snip = sim.get_snippet("u(0,1)", start_dt=0, length_dt=2000)

    print(f"Drive d0 max amplitude: {np.max(np.abs(d0_snip.wave)):.4f}")
    print(f"Control u(0,1) max amplitude: {np.max(np.abs(cr_snip.wave)):.4f}")

    # 5. Visualize (opens in browser)
    show_pulse_sheet(sim, interactive=True)
    show_iq_oscilloscope(sim, "d0", start_dt=0, length_dt=1000, interactive=True)

    print("\nRun with interactive=True to see visualizations!")


if __name__ == "__main__":
    main()
