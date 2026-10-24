#!/usr/bin/env python3
"""
Example: Custom pulse annotations with BoxOp.

Attaches PulseEnvelopeAnnotation overrides to gates via ``qc.box(...)`` and
exports them to OpenQASM 3.

Note: Qiskit's preset scheduling passes reject circuits that contain boxes,
so a boxed circuit cannot go through ``generate_preset_pass_manager(...,
scheduling_method="alap")``. The annotations are fully supported for
OpenQASM 3 and QPY serialization; ``TargetWaveformSimulator.compile`` applies
them when you pass ``start_times=[...]``.
"""

import numpy as np
from qiskit import QuantumCircuit, qasm3

from qiskit_waveform_sim import (
    PulseAnnotationSerializer,
    PulseEnvelopeAnnotation,
)


def main():
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)

    # Custom high-beta DRAG for the SX gate
    custom_drag = PulseEnvelopeAnnotation(
        shape="drag",
        amp=0.55,
        beta=0.25,  # Higher beta for stronger leakage suppression
        sigma_ratio=0.2,  # Narrower Gaussian
    )
    with qc.box(duration=160, unit="dt", annotations=[custom_drag]):
        qc.sx(0)

    # Custom GaussianSquare for the RZZ cross-resonance pulses
    custom_gs = PulseEnvelopeAnnotation(
        shape="gaussian_square",
        amp=0.75,
        risefall_dt=30,  # Longer rise/fall
    )
    with qc.box(duration=300, unit="dt", annotations=[custom_gs]):
        qc.rzz(np.pi / 2, 0, 1)

    qc.measure([0, 1], [0, 1])

    print("Circuit with BoxOp annotations:")
    for inst in qc.data:
        annotations = getattr(inst.operation, "annotations", None)
        if annotations:
            print(f"  {inst.operation.name}: {list(annotations)}")

    qasm3_str = qasm3.dumps(
        qc, annotation_handlers={"pulse_sim.envelope": PulseAnnotationSerializer()}
    )
    print("\n--- OpenQASM 3 Export ---")
    print(qasm3_str)


if __name__ == "__main__":
    main()
