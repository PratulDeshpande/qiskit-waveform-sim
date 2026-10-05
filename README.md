# qiskit-waveform-sim

[![PyPI](https://img.shields.io/pypi/v/qiskit-waveform-sim.svg?cache=clear)](https://pypi.org/project/qiskit-waveform-sim/)
[![Python](https://img.shields.io/pypi/pyversions/qiskit-waveform-sim.svg?cache=clear)](https://pypi.org/project/qiskit-waveform-sim/)
[![License](https://img.shields.io/pypi/l/qiskit-waveform-sim.svg?cache=clear)](https://www.apache.org/licenses/LICENSE-2.0)
[![Tests](https://github.com/PratulDeshpande/qiskit-waveform-sim/actions/workflows/tests.yml/badge.svg)](https://github.com/PratulDeshpande/qiskit-waveform-sim/actions)

**Classical Control Waveform Simulator & Interactive Pulse Sheet Viewer**

`qiskit-waveform-sim` bridges the post-Pulse waveform gap in Qiskit by providing a native, offline, lazy-evaluated waveform simulator that works directly with Qiskit's modern `Target`, `op_start_times`, `BoxOp`, fractional gates (`RX`, `RZZ`), and the new `qiskit.circuit.annotation.Annotation` API.

## Overview

`qiskit-waveform-sim` bridges the post-Pulse waveform gap in Qiskit by providing a native, offline, lazy-evaluated waveform simulator that works directly with Qiskit's modern `Target` and `QuantumCircuit` APIs.

With the deprecation and removal of `qiskit.pulse` in Qiskit 2.0, users need a way to inspect scheduled waveforms. This package provides an **analytical envelope generator** that synthesizes waveforms directly from instruction durations and gate names, overriding hardware calibrations with idealized standard physics (DRAG, GaussianSquare).

| Tool | Offline? | Dynamic Circuits | Fractional Gates | Virtual-Z Tracking | Sample-Precise I/Q |
|------|----------|------------------|------------------|--------------------|---------------------|
| `qiskit.visualization.timeline` | Yes | No | No | No (markers only) | No |
| `qiskit-ibm-runtime` `CircuitSchedule` | No (cloud only) | Yes (server) | No | No | No |
| **qiskit-waveform-sim** | Yes | Yes | Yes | Yes Exact | Yes Lazy/Windowed |

## Features

- **Lazy Windowed Evaluation**: `O(W)` memory for snippet extraction, independent of total circuit depth
- **Exact Virtual-Z Frame Tracking**: Per-qubit phase accumulation propagated to drive and cross-resonance channels
- **Analytical Envelope Synthesis**: DRAG (with leakage suppression), GaussianSquare (flat-top with pedestal correction)
- **Fractional Gate Support**: Continuous parametric amplitude/duration scaling for `RX(θ)`, `RZZ(θ)`
- **BoxOp & Annotation Native**: Custom `PulseEnvelopeAnnotation` with OpenQASM 3 & QPY serialization
- **Interactive Visualization**: Plotly-based Pulse Sheet + synchronized I/Q Oscilloscope
- **LabOne Q Compatible Architecture**: `OutputSimulator.get_snippet()`-style API

---

## Installation

```bash
pip install qiskit-waveform-sim
```

For development:
```bash
git clone https://github.com/PratulDeshpande/qiskit-waveform-sim
cd qiskit-waveform-sim
pip install -e ".[dev,test,docs]"
```

Requires Python 3.11+ and Qiskit 1.0+.

---

## Quickstart

```python
from qiskit import QuantumCircuit
from qiskit.providers.fake_provider import GenericBackendV2
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_waveform_sim import TargetWaveformSimulator

# 1. Create backend and circuit
backend = GenericBackendV2(num_qubits=2, seed=42)

qc = QuantumCircuit(2, 2)
qc.h(0)                    # Decomposes to rz(π/2) → sx → rz(π/2)
qc.cx(0, 1)
qc.measure([0, 1], [0, 1])

# 2. Transpile & schedule (ALAP)
pm = generate_preset_pass_manager(optimization_level=1, backend=backend, scheduling_method="alap")
scheduled_qc = pm.run(qc)

# 3. Compile waveform simulator
sim = TargetWaveformSimulator(backend.target).compile(scheduled_qc)

# 4. Extract sample-precise I/Q snippets (lazy, windowed)
d0_snip = sim.get_snippet("d0", start_dt=0, length_dt=2500)
cr_snip = sim.get_snippet("u(0,1)", start_dt=0, length_dt=2500)

# 5. Plot interactive Pulse Sheet + I/Q Oscilloscope
from qiskit_waveform_sim.visualization import show_pulse_sheet, show_iq_oscilloscope
show_pulse_sheet(sim, interactive=True)
show_iq_oscilloscope(sim, "d0", start_dt=0, length_dt=1000, interactive=True)
```

### Custom Pulse Annotations (Unscheduled Preview)

For custom pulse shapes, use `BoxOp` with `PulseEnvelopeAnnotation`. Note: scheduling with `BoxOp` is not yet supported in Qiskit 2.0's transpiler. Use the unscheduled circuit for OpenQASM 3 export and manual waveform compilation.

```python
from qiskit_waveform_sim import PulseEnvelopeAnnotation, PulseAnnotationSerializer
from qiskit import qasm3

qc = QuantumCircuit(2, 2)
qc.h(0)
qc.cx(0, 1)

# Custom high-beta DRAG for SX gate
with qc.box(
    duration=160,
    unit="dt",
    annotations=[PulseEnvelopeAnnotation(shape="drag", amp=0.55, beta=0.25, sigma_ratio=0.2)]
):
    qc.sx(0)

qc.measure([0, 1], [0, 1])

# Export to OpenQASM 3 with pulse annotations (works without scheduling)
qasm3_str = qasm3.dumps(
    qc, annotation_handlers={"pulse_sim.envelope": PulseAnnotationSerializer()}
)
print(qasm3_str)
```

---

## Architecture

**Input:** Scheduled `QuantumCircuit` + `Target`

**Pillar 1: Target Parametric Binding**
- `sx`/`x` → DRAG envelope (σ = D/4, β leakage suppression)
- `rx(θ)` → DRAG with A(θ) = A_π · (θ/π)
- `ecr`/`cx`/`rzz` → GaussianSquare on ControlChannel
- `measure` → GaussianSquare on MeasureChannel + Acquire

**Pillar 2: PulseAnnotation Override (OpenQASM 3 + QPY)**
- `@pulse_sim.drag(amp=0.5, beta=0.1, σ_ratio=0.25)`
- `box { sx q[0]; }`

**Engine: FrameTracker + AnalyticalEnvelopes + Interval Indexing**
- Virtual-Z: φ_q(t⁺) = φ_q(t⁻) - λ
- CR phase-locked to target qubit frame φ_t
- I(t) + iQ(t) = Ω_env(t) · e^{i(2πf_IF t + φ_q)}
- Binary search over ChannelEvent start_dt (O(log N))

**Output:** `WaveformSnippet(channel, time_ns, wave=I+iQ, phase)`
**Visualization:** Pulse Sheet (Plotly/HTML) + I/Q Oscilloscope

---

## Documentation

- [Quickstart Tutorial](https://pratuldeshpande.github.io/qiskit-waveform-sim/tutorials/quickstart.html)
- [Custom Pulse Annotations & OpenQASM 3 Export](https://pratuldeshpande.github.io/qiskit-waveform-sim/tutorials/annotations.html)
- [LabOne Q / RFSoC Integration](https://pratuldeshpande.github.io/qiskit-waveform-sim/tutorials/hardware_export.html)
- [API Reference](https://pratuldeshpande.github.io/qiskit-waveform-sim/api.html)

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch
3. Run tests: `pytest -v`
4. Run linters: `ruff check . && black --check . && mypy .`
5. Submit a PR

---

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

---

## Citation

If you use `qiskit-waveform-sim` in your research, please cite:

```bibtex
@software{qiskit_waveform_sim,
  author       = {Pratul Deshpande},
  title        = {qiskit-waveform-sim: Classical Control Waveform Simulator},
  year         = {2026},
  url          = {https://github.com/PratulDeshpande/qiskit-waveform-sim},
  version      = {0.1.2}
}
```