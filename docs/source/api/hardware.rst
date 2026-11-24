Hardware Impairments API Reference
==================================

.. currentmodule:: qiskit_waveform_sim.hardware

A :class:`HardwareProfile` describes the control chain (AWG, mixer, cable) that
drives the qubits. It is separate from Qiskit's ``Target``, which holds
qubit-side data. Pass it as ``TargetWaveformSimulator(target, hardware_profile=profile)``
and the samples returned by ``get_snippet()`` carry the impairments;
``get_snippet(..., ideal=True)`` returns the ideal waveform, bit-identical to a
simulator without a profile.

.. warning::
   These are **waveform impairments, not a fidelity prediction**. The package
   does not evolve a Hamiltonian, so it reports no gate fidelities. Preset values
   are generic and illustrative, not datasheet numbers of any product.
   Hardware export should always use ``ideal=True``.

Signal chain
------------

The stages run in this fixed order on every sample. A stage whose parameters
are neutral is skipped, so the ``ideal`` preset equals a simulator with no profile.

1. **Delay.** The whole ideal channel signal (envelope, IF carrier and frame
   phase) is evaluated at ``t - delay``. A whole-sample part is an exact index
   shift; a fractional part is evaluated analytically, so a pulse then spans
   ``duration + 1`` samples and its envelope is zero outside ``[0, duration)``.
   Frame changes and the phase trace shift with the channel.
2. **Digital gain** ``amp_scale``.
3. **DAC quantization and clipping** (``dac_bits``), two's complement: codes
   ``-2**(b-1) ... 2**(b-1) - 1`` with ``LSB = 2**-(b-1)``, so full scale ``+1``
   clips to ``1 - LSB``. This is the only clipping stage.
4. **Bandwidth**: a 1-pole low-pass on I and Q. It has infinite memory, so
   windows that overlap agree to ``1e-12 * max|x|``, not bit-exactly.
5. **Mixer**: ``I' = (1 + e/2) I`` and ``Q' = (1 - e/2)(Q cos(p) - I sin(p))``.
   The image sideband only exists when ``if_freq_hz`` is not zero; at baseband
   the imbalance is a static complex error.
6. **DC offset** (LO leakage) ``dc_i + 1j * dc_q``.

Channel lookup
--------------

Profile keys are exact channel names (``d0``, ``m1``, ``u(0,1)``) or globs
(``d*``, ``u(*)``), matched **case-sensitively**. Precedence: exact name, then
the first matching glob in insertion order, then ``default``. The chosen entry
is used whole. When loading a JSON or TOML file, keys left out of a channel
entry are filled from the file's ``default`` entry, and unknown keys raise
``ValueError``.

``delay_ns`` must be ``>= 0``; express skew relative to the earliest channel.

.. code-block:: python

   from qiskit_waveform_sim import (
       ChannelImpairments, HardwareProfile, TargetWaveformSimulator, show_iq_oscilloscope,
   )

   profile = HardwareProfile.from_preset("iq_mixer_uncalibrated")
   # or HardwareProfile.from_file("my_lab.toml")
   # or HardwareProfile(default=ChannelImpairments(dac_bits=14),
   #                    channels={"u(*)": ChannelImpairments(delay_ns=12.0, dac_bits=14)})

   sim = TargetWaveformSimulator(backend.target, hardware_profile=profile).compile(qc)
   sim.get_snippet("d0", 0, 1000)              # impaired
   sim.get_snippet("d0", 0, 1000, ideal=True)  # ideal
   show_iq_oscilloscope(sim, "d0", compare_ideal=True)

ChannelImpairments
------------------

.. autoclass:: ChannelImpairments
   :members:
   :show-inheritance:

HardwareProfile
---------------

.. autoclass:: HardwareProfile
   :members:
   :show-inheritance:

.. autodata:: PRESET_NAMES

Signal helpers
--------------

.. autofunction:: quantize_dac
.. autofunction:: lowpass
.. autofunction:: lowpass_lookback
.. autofunction:: apply_iq_imbalance
