#!/usr/bin/env python3
"""
Example: Hardware Export - LabOne Q, RFSoC/QICK, Generic AWG.

Shows how to export waveforms for various hardware platforms.
"""

import numpy as np
import json
from qiskit import QuantumCircuit
from qiskit.providers.fake_provider import GenericBackendV2
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_waveform_sim import TargetWaveformSimulator


def export_laboneq(waveforms, dt_sec, filename="waveforms_laboneq.json"):
    """Export to LabOne Q compatible JSON format."""
    export_data = {
        "sampling_rate_hz": 1.0 / dt_sec,
        "waveforms": {},
    }
    
    for ch, data in waveforms.items():
        # Convert complex to [real, imag] pairs for JSON serialization
        wave_complex = data["I"] + 1j * data["Q"]
        samples_list = [[float(s.real), float(s.imag)] for s in wave_complex.astype(np.complex64)]
        export_data["waveforms"][ch] = {
            "samples": samples_list,
            "length": len(wave_complex),
            "markers": np.zeros(len(wave_complex), dtype=np.uint8).tolist(),
        }
    
    with open(filename, 'w') as f:
        json.dump(export_data, f, indent=2)
    print(f"Exported LabOne Q format to {filename}")


def export_rfsoc_qick(waveforms, dt_sec, filename="waveforms_rfsoc.npz"):
    """Export to RFSoC/QICK format (int16 DAC values)."""
    DAC_MAX = 32767
    
    # Flatten channel data for proper npz storage (avoid object arrays)
    export_dict = {
        "sampling_rate_hz": np.array(1.0 / dt_sec),
    }
    
    for ch, data in waveforms.items():
        I_dac = np.clip(np.round(data["I"] * DAC_MAX), -DAC_MAX, DAC_MAX).astype(np.int16)
        Q_dac = np.clip(np.round(data["Q"] * DAC_MAX), -DAC_MAX, DAC_MAX).astype(np.int16)
        # Sanitize channel name for npz key
        safe_ch = ch.replace("(", "_").replace(")", "").replace(",", "_")
        export_dict[f"{safe_ch}_I"] = I_dac
        export_dict[f"{safe_ch}_Q"] = Q_dac
        export_dict[f"{safe_ch}_length"] = np.array(len(I_dac), dtype=np.int32)
    
    np.savez_compressed(filename, **export_dict)
    print(f"Exported RFSoC/QICK format to {filename}")


def export_csv(waveforms, dt_sec, prefix="waveform"):
    """Export to CSV for generic AWG."""
    for ch, data in waveforms.items():
        # Sanitize channel name for filesystem safety
        safe_ch = ch.replace("(", "_").replace(")", "").replace(",", "_")
        filename = f"{prefix}_{safe_ch}.csv"
        csv_data = np.column_stack([
            data["time_ns"],
            data["I"],
            data["Q"],
            data["phase_rad"],
        ])
        header = "time_ns,I,Q,phase_rad"
        np.savetxt(filename, csv_data, delimiter=",", header=header, comments='')
        print(f"Exported {ch} to {filename} ({len(csv_data)} rows)")


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
    
    # Extract all channels for full duration
    total_dt = sim.total_duration_dt
    dt_sec = sim.dt
    
    waveforms = {}
    for ch in sim.get_channels():
        snip = sim.get_snippet(ch, start_dt=0, length_dt=total_dt)
        waveforms[ch] = {
            "time_ns": snip.time_ns,
            "I": snip.wave.real,
            "Q": snip.wave.imag,
            "phase_rad": snip.phase_rad,
            "dt_sec": snip.dt_sec,
        }
        print(f"{ch}: {len(snip.wave)} samples")
    
    # Export to various formats
    export_laboneq(waveforms, dt_sec)
    export_rfsoc_qick(waveforms, dt_sec)
    export_csv(waveforms, dt_sec)
    
    print("\nAll exports complete!")
    print("Files created:")
    print("  - waveforms_laboneq.json (LabOne Q)")
    print("  - waveforms_rfsoc.npz (RFSoC/QICK)")
    print("  - waveform_d0.csv, waveform_d1.csv, etc. (Generic AWG)")


if __name__ == "__main__":
    main()