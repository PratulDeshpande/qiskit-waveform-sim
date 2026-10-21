#!/usr/bin/env python3
"""
Example: Visualization - Pulse Sheet and I/Q Oscilloscope.

Shows both interactive (Plotly) and static (Matplotlib) visualizations.
Interactive figures open in your browser; HTML and PNG copies are written
to the current directory.
"""

import matplotlib.pyplot as plt
from qiskit import QuantumCircuit
from qiskit.providers.fake_provider import GenericBackendV2
from qiskit.transpiler import generate_preset_pass_manager

from qiskit_waveform_sim import TargetWaveformSimulator
from qiskit_waveform_sim.visualization import (
    create_combined_view,
    create_iq_oscilloscope,
    create_pulse_sheet,
    export_html,
    plot_iq_waveforms,
    plot_phase_tracking,
    plot_pulse_sheet,
    show_iq_oscilloscope,
    show_pulse_sheet,
)


def main():
    backend = GenericBackendV2(num_qubits=2, seed=42)

    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])

    pm = generate_preset_pass_manager(
        optimization_level=1, backend=backend, scheduling_method="alap"
    )
    scheduled_qc = pm.run(qc)

    sim = TargetWaveformSimulator(backend.target).compile(scheduled_qc)

    # Interactive Plotly visualizations (open in browser)
    show_pulse_sheet(sim, interactive=True)
    show_iq_oscilloscope(sim, "d0", start_dt=0, length_dt=1500, interactive=True)
    create_combined_view(sim, "d0", start_dt=0, length_dt=1500).show()

    # Export interactive figures to standalone HTML
    export_html(create_pulse_sheet(sim), "pulse_sheet.html")
    print("Exported pulse sheet to pulse_sheet.html")
    export_html(
        create_iq_oscilloscope(sim, "d0", start_dt=0, length_dt=1000),
        "iq_oscilloscope.html",
    )
    print("Exported I/Q oscilloscope to iq_oscilloscope.html")

    # Static Matplotlib visualizations (for publications)
    plot_pulse_sheet(sim, figsize=(12, 6)).savefig(
        "pulse_sheet_static.png", dpi=150, bbox_inches="tight"
    )
    print("Saved static pulse sheet to pulse_sheet_static.png")

    d0_snip = sim.get_snippet("d0", start_dt=0, length_dt=2000)
    plot_iq_waveforms(d0_snip, figsize=(12, 5)).savefig(
        "iq_waveforms_static.png", dpi=150, bbox_inches="tight"
    )
    print("Saved static I/Q waveforms to iq_waveforms_static.png")

    plot_phase_tracking(sim, figsize=(12, 4)).savefig(
        "phase_tracking_static.png", dpi=150, bbox_inches="tight"
    )
    print("Saved static phase tracking to phase_tracking_static.png")

    plt.close("all")


if __name__ == "__main__":
    main()
