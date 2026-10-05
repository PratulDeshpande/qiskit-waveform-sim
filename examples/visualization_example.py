#!/usr/bin/env python3
"""
Example: Visualization - Pulse Sheet and I/Q Oscilloscope.

Shows both interactive (Plotly) and static (Matplotlib) visualizations.
"""

from qiskit_waveform_sim import create_combined_view
import numpy as np
from qiskit import QuantumCircuit
from qiskit.providers.fake_provider import GenericBackendV2
from qiskit.transpiler import generate_preset_pass_manager

from qiskit_waveform_sim import TargetWaveformSimulator
from qiskit_waveform_sim.visualization import (
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
    qc.rx(np.pi/4, 0)
    qc.rzz(np.pi/2, 0, 1)
    qc.measure([0, 1], [0, 1])

    pm = generate_preset_pass_manager(
        optimization_level=1, backend=backend, scheduling_method="alap"
    )
    scheduled_qc = pm.run(qc)

    sim = TargetWaveformSimulator(backend.target).compile(scheduled_qc)

    # Interactive Plotly visualizations (open in browser)
    # Uncomment to run interactively:
    show_pulse_sheet(sim, interactive=True)
    show_iq_oscilloscope(sim, "d0", start_dt=0, length_dt=1500, interactive=True)
    fig = create_combined_view(sim, "d0", start_dt=0, length_dt=1500)
    fig.show()

    # Export interactive to HTML
    pulse_fig = show_pulse_sheet(sim, interactive=False)
    export_html(pulse_fig, "pulse_sheet.html")
    print("Exported pulse sheet to pulse_sheet.html")

    iq_fig = show_iq_oscilloscope(sim, "d0", start_dt=0, length_dt=1000, interactive=False)
    export_html(iq_fig, "iq_oscilloscope.html")
    print("Exported I/Q oscilloscope to iq_oscilloscope.html")

    # Static Matplotlib visualizations (for publications)
    import matplotlib.pyplot as plt

    # Pulse sheet
    fig1 = plot_pulse_sheet(sim, figsize=(12, 6))
    fig1.savefig("pulse_sheet_static.png", dpi=150, bbox_inches="tight")
    print("Saved static pulse sheet to pulse_sheet_static.png")

    # I/Q waveforms
    d0_snip = sim.get_snippet("d0", start_dt=0, length_dt=2000)
    fig2 = plot_iq_waveforms(d0_snip, figsize=(12, 5))
    fig2.savefig("iq_waveforms_static.png", dpi=150, bbox_inches="tight")
    print("Saved static I/Q waveforms to iq_waveforms_static.png")

    # Phase tracking

    fig3 = plot_phase_tracking(sim, figsize=(12, 4))
    fig3.savefig("phase_tracking_static.png", dpi=150, bbox_inches="tight")
    print("Saved static phase tracking to phase_tracking_static.png")

    plt.close("all")


if __name__ == "__main__":
    main()
