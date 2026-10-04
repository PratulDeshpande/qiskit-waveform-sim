#!/usr/bin/env python3
"""
Example: Custom pulse annotations with BoxOp.

Demonstrates overriding default pulse shapes for specific gates.

Note: As of Qiskit 2.5, scheduling (ALAP/ASAP) does not support BoxOp/control flow.
This example shows the annotation attachment, but compilation requires a scheduled
circuit without BoxOp, or a backend that supports control flow scheduling.
"""

import numpy as np
from qiskit import QuantumCircuit
from qiskit.providers.fake_provider import GenericBackendV2
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_waveform_sim import (
    TargetWaveformSimulator,
    PulseEnvelopeAnnotation,
    PulseAnnotationSerializer,
)
from qiskit import qasm3


def main():
    backend = GenericBackendV2(num_qubits=2, seed=42)
    
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    
    # Custom high-beta DRAG for SX gate
    custom_drag = PulseEnvelopeAnnotation(
        shape="drag",
        amp=0.55,
        beta=0.25,       # Higher beta for better leakage suppression
        sigma_ratio=0.2, # Narrower Gaussian
    )
    
    # Apply custom pulse to SX gate via BoxOp
    with qc.box(
        duration=160,
        unit="dt",
        annotations=[custom_drag]
    ):
        qc.sx(0)
    
    # Custom GaussianSquare for RZZ (requires RZZ in basis)
    custom_gs = PulseEnvelopeAnnotation(
        shape="gaussian_square",
        amp=0.75,
        risefall_dt=30,  # Longer rise/fall
    )
    
    with qc.box(
        duration=300,
        unit="dt",
        annotations=[custom_gs]
    ):
        qc.rzz(np.pi/2, 0, 1)
    
    qc.measure([0, 1], [0, 1])
    
    # Show annotation attachment (but don't schedule - not supported with BoxOp)
    print("Circuit with BoxOp annotations:")
    for inst in qc.data:
        op = inst.operation
        if hasattr(op, 'annotations') and op.annotations:
            print(f"  BoxOp annotations: {op.annotations}")
    
    # For actual waveform simulation, use a circuit without BoxOp
    # but with the custom pulse parameters applied manually
    print("\nNote: Scheduling with BoxOp not supported in Qiskit 2.5.")
    print("For waveform simulation, use a scheduled circuit without BoxOp,")
    print("or apply custom parameters directly in the simulator.")
    
    # Export to OpenQASM 3 with pulse annotations (works without scheduling)
    qasm3_str = qasm3.dumps(
        qc,
        annotation_handlers={"pulse_sim.envelope": PulseAnnotationSerializer()}
    )
    
    print("\n--- OpenQASM 3 Export (first 50 lines) ---")
    for line in qasm3_str.splitlines()[:50]:
        print(line)
    
    print("\n... (truncated)")


if __name__ == "__main__":
    main()