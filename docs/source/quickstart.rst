Quickstart
==========

This guide shows you how to go from a Qiskit 2.0 scheduled circuit to 
sample-precise I/Q waveforms and interactive pulse sheets in minutes.

Prerequisites
-------------

- Python 3.11+
- Qiskit 2.0+ (``pip install qiskit>=2.0.0``)
- qiskit-waveform-sim (``pip install qiskit-waveform-sim``)

Basic Workflow
--------------

1. **Create a backend and circuit**

.. code-block:: python

   from qiskit import QuantumCircuit
   from qiskit.providers.fake_provider import GenericBackendV2

   backend = GenericBackendV2(num_qubits=2, seed=42)

   qc = QuantumCircuit(2, 2)
   qc.h(0)                    # Decomposes to rz(π/2) → sx → rz(π/2)
   qc.cx(0, 1)
   qc.measure([0, 1], [0, 1])

2. **Transpile and schedule**

.. code-block:: python

   from qiskit.transpiler import generate_preset_pass_manager

   pm = generate_preset_pass_manager(
       optimization_level=1, 
       backend=backend, 
       scheduling_method="alap"
   )
   scheduled_qc = pm.run(qc)

3. **Compile the waveform simulator**

.. code-block:: python

   from qiskit_waveform_sim import TargetWaveformSimulator

   sim = TargetWaveformSimulator(backend.target).compile(scheduled_qc)

4. **Extract sample-precise I/Q snippets**

.. code-block:: python

   # Get drive channel 0 waveform (first 2500 dt)
   d0_snip = sim.get_snippet("d0", start_dt=0, length_dt=2500)

   # Get cross-resonance channel waveform
   cr_snip = sim.get_snippet("u(0,1)", start_dt=0, length_dt=2500)

   # Access waveform data
   print(f"Time points: {len(d0_snip.time_ns)}")
   print(f"I component: {d0_snip.wave.real[:5]}")
   print(f"Q component: {d0_snip.wave.imag[:5]}")
   print(f"Frame phase: {d0_snip.phase_rad[:5]}")

5. **Visualize interactively**

.. code-block:: python

   from qiskit_waveform_sim.visualization import show_pulse_sheet, show_iq_oscilloscope

   # Multi-channel Pulse Sheet (schedule view)
   show_pulse_sheet(sim, interactive=True)

   # Sample-precise I/Q Oscilloscope (waveform view)
   show_iq_oscilloscope(sim, "d0", start_dt=0, length_dt=1000, interactive=True)

   # Combined view
   from qiskit_waveform_sim.visualization import create_combined_view
   fig = create_combined_view(sim, "d0", start_dt=0, length_dt=1000)
   fig.show()

Custom Pulse Annotations
------------------------

Attach custom pulse shapes to specific gates using Qiskit 2.0's ``BoxOp`` and ``Annotation`` API:

.. code-block:: python

   from qiskit_waveform_sim import PulseEnvelopeAnnotation

   qc = QuantumCircuit(2, 2)
   qc.h(0)
   qc.cx(0, 1)

   # Override SX gate with custom high-beta DRAG pulse
   with qc.box(
       duration=160,
       unit="dt",
       annotations=[PulseEnvelopeAnnotation(shape="drag", amp=0.55, beta=0.25, sigma_ratio=0.2)]
   ):
       qc.sx(0)

   qc.measure([0, 1], [0, 1])

   # Transpile, schedule, and compile as before...
   # The custom annotation will be automatically applied

Export to OpenQASM 3
--------------------

Serialize circuits with pulse annotations to OpenQASM 3:

.. code-block:: python

   from qiskit_waveform_sim import PulseAnnotationSerializer
   from qiskit import qasm3

   qasm3_str = qasm3.dumps(
       scheduled_qc, 
       annotation_handlers={"pulse_sim.envelope": PulseAnnotationSerializer()}
   )
   print(qasm3_str)

Next Steps
----------

- :doc:`tutorials/quickstart` - Complete notebook tutorial
- :doc:`tutorials/annotations` - Deep dive into custom pulse annotations
- :doc:`tutorials/hardware_export` - Export to LabOne Q, RFSoC, QICK
- :doc:`api/core` - Full API reference