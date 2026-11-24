"""
Simulator integration tests for hardware impairment profiles (Phase 1).

Covers get_snippet(..., ideal=...), channel skew, the fixed stage order, empty
channels, window consistency and the guarantee that the ideal path is untouched.
"""

import cmath
import math

import numpy as np
import pytest
from qiskit import QuantumCircuit

from qiskit_waveform_sim import (
    AnalyticalEnvelopes,
    ChannelImpairments,
    HardwareProfile,
    PulseEnvelopeAnnotation,
    TargetWaveformSimulator,
)
from qiskit_waveform_sim.hardware import (
    apply_iq_imbalance,
    lowpass,
    quantize_dac,
)


def build_sim(
    backend,
    profile=None,
    *,
    layout=((("box", 0, 160)),),
    shape="drag",
    amp=0.5,
    if_freq_hz=0.0,
    risefall_dt=16,
):
    """
    Compile a 2-qubit circuit of annotated single-qubit boxes and virtual-Z gates.

    ``layout`` entries are ``("box", start_dt, duration_dt)`` or
    ``("rz", start_dt, angle)``; every instruction acts on qubit 0.
    """
    qc = QuantumCircuit(2)
    starts = []
    ann = PulseEnvelopeAnnotation(
        shape=shape, amp=amp, beta=0.08, sigma_ratio=0.25, risefall_dt=risefall_dt
    )
    for kind, start, arg in layout:
        starts.append(start)
        if kind == "box":
            with qc.box(duration=arg, unit="dt", annotations=[ann]):
                qc.sx(0)
        else:
            qc.rz(arg, 0)
    return TargetWaveformSimulator(
        backend.target, if_freq_hz=if_freq_hz, hardware_profile=profile
    ).compile(qc, start_times=starts)


def single(delay_ns=0.0, **kw):
    return HardwareProfile(default=ChannelImpairments(delay_ns=delay_ns, **kw), seed=1)


class TestIdealPathIsUntouched:
    def _baseline(self, backend_2q):
        return build_sim(backend_2q).get_snippet("d0", 0, 400)

    def _assert_identical(self, a, b):
        assert np.array_equal(a.wave, b.wave)
        assert np.array_equal(a.phase_rad, b.phase_rad)
        assert np.array_equal(a.time_ns, b.time_ns)
        assert a.events == b.events

    def test_ideal_flag_is_bit_identical_with_a_loud_profile(self, backend_2q):
        loud = HardwareProfile.from_preset("noisy_lab", seed=3)
        sim = build_sim(backend_2q, loud)
        self._assert_identical(
            sim.get_snippet("d0", 0, 400, ideal=True), self._baseline(backend_2q)
        )

    def test_ideal_preset_is_bit_identical(self, backend_2q):
        sim = build_sim(backend_2q, HardwareProfile.from_preset("ideal"))
        self._assert_identical(
            sim.get_snippet("d0", 0, 400), self._baseline(backend_2q)
        )

    def test_ideal_profile_keeps_the_default_window_length(self, backend_2q):
        base = build_sim(backend_2q).get_snippet("d0", 0)
        ideal = build_sim(backend_2q, HardwareProfile()).get_snippet("d0", 0)
        assert len(ideal.wave) == len(base.wave)

    def test_profile_is_stored_and_none_by_default(self, backend_2q):
        assert build_sim(backend_2q).hardware_profile is None
        p = HardwareProfile(seed=2)
        assert build_sim(backend_2q, p).hardware_profile is p

    def test_nyquist_violation_is_rejected_at_construction(self, backend_2q):
        bad = HardwareProfile(default=ChannelImpairments(bandwidth_mhz=1e6))
        with pytest.raises(ValueError, match="Nyquist"):
            TargetWaveformSimulator(backend_2q.target, hardware_profile=bad)

    def test_unknown_channel_still_raises_with_a_profile(self, backend_2q):
        sim = build_sim(backend_2q, single(delay_ns=1.0))
        with pytest.raises(ValueError, match="Unknown channel"):
            sim.get_snippet("x9", 0, 10)


class TestChannelDelay:
    def test_integer_delay_shifts_by_exactly_k_samples(self, backend_2q):
        ideal_sim = build_sim(backend_2q)
        dt_ns = ideal_sim.dt * 1e9
        sim = build_sim(backend_2q, single(delay_ns=7 * dt_ns))
        ideal = ideal_sim.get_snippet("d0", 0, 400)
        imp = sim.get_snippet("d0", 0, 400)
        assert np.array_equal(imp.wave[7:], ideal.wave[:-7])
        assert np.all(imp.wave[:7] == 0)

    def test_integer_delay_shifts_the_if_carrier_too(self, backend_2q):
        if_hz = 90e6
        ideal_sim = build_sim(backend_2q, if_freq_hz=if_hz)
        dt_ns = ideal_sim.dt * 1e9
        sim = build_sim(backend_2q, single(delay_ns=5 * dt_ns), if_freq_hz=if_hz)
        ideal = ideal_sim.get_snippet("d0", 0, 400)
        imp = sim.get_snippet("d0", 0, 400)
        assert np.array_equal(imp.wave[5:], ideal.wave[:-5])

    def test_fractional_delay_matches_the_analytic_envelope(self, backend_2q):
        dur = 160
        dt_ns = build_sim(backend_2q).dt * 1e9
        sim = build_sim(
            backend_2q, single(delay_ns=2.5 * dt_ns), layout=(("box", 0, dur),)
        )
        imp = sim.get_snippet("d0", 0, 400)
        n = np.arange(400, dtype=float)
        s = n - 2.5
        inside = (s >= 0) & (s < dur)
        expected = np.zeros(400, dtype=np.complex128)
        expected[inside] = AnalyticalEnvelopes.drag(
            s[inside], dur, 0.5, dur * 0.25, 0.08
        )
        assert np.allclose(imp.wave, expected, atol=1e-15)

    def test_fractional_delay_keeps_the_last_sample(self, backend_2q):
        dur = 160
        sim = build_sim(backend_2q)
        dt_ns = sim.dt * 1e9
        sim = build_sim(backend_2q, single(delay_ns=0.4 * dt_ns))
        imp = sim.get_snippet("d0", 0, 400)
        # sample n = dur sits at s = dur - 0.4 < dur: inside the delayed pulse
        assert imp.wave[dur] != 0
        assert np.all(imp.wave[dur + 1 :] == 0)

    def test_virtual_z_phase_trace_and_waveform_shift_with_the_channel(
        self, backend_2q
    ):
        layout = (("box", 0, 160), ("rz", 160, 0.7), ("box", 160, 160))
        ideal_sim = build_sim(backend_2q, layout=layout)
        dt_ns = ideal_sim.dt * 1e9
        sim = build_sim(backend_2q, single(delay_ns=5 * dt_ns), layout=layout)
        ideal = ideal_sim.get_snippet("d0", 0, 600)
        imp = sim.get_snippet("d0", 0, 600)
        assert np.array_equal(imp.wave[5:], ideal.wave[:-5])
        assert np.array_equal(imp.phase_rad[5:], ideal.phase_rad[:-5])
        assert np.all(imp.phase_rad[:5] == 0)

    def test_fractional_delay_phase_steps_at_the_next_whole_sample(self, backend_2q):
        layout = (("box", 0, 160), ("rz", 160, 0.7), ("box", 160, 160))
        ideal_sim = build_sim(backend_2q, layout=layout)
        dt_ns = ideal_sim.dt * 1e9
        sim = build_sim(backend_2q, single(delay_ns=5.5 * dt_ns), layout=layout)
        ideal = ideal_sim.get_snippet("d0", 0, 600)
        imp = sim.get_snippet("d0", 0, 600)
        assert np.array_equal(imp.phase_rad[6:], ideal.phase_rad[:-6])

    def test_default_window_grows_by_the_delay(self, backend_2q):
        ideal_sim = build_sim(backend_2q)
        dt_ns = ideal_sim.dt * 1e9
        sim = build_sim(backend_2q, single(delay_ns=12.3 * dt_ns))
        assert (
            len(sim.get_snippet("d0", 0).wave)
            == len(ideal_sim.get_snippet("d0", 0).wave) + 13
        )
        assert sim.channel_delay_dt("d0") == 13
        assert sim.channel_delay_ns("d0") == pytest.approx(12.3 * dt_ns)

    def test_delay_accessors_are_zero_without_a_profile(self, backend_2q):
        sim = build_sim(backend_2q)
        assert sim.channel_delay_dt("d0") == 0
        assert sim.channel_delay_ns("d0") == 0.0

    def test_delayed_event_is_found_after_its_ideal_end(self, backend_2q):
        ideal_sim = build_sim(backend_2q)
        dt_ns = ideal_sim.dt * 1e9
        sim = build_sim(backend_2q, single(delay_ns=20 * dt_ns))
        # The ideal pulse ends at 160; the delayed one spans [20, 180)
        late = sim.get_snippet("d0", 170, 10)
        assert [e.op_name for e in late.events] == ["sx"]
        assert np.any(late.wave != 0)
        assert sim.get_snippet("d0", 200, 100).events == []

    def test_per_channel_skew_moves_only_that_channel(self, backend_2q):
        qc = QuantumCircuit(2)
        qc.sx(0)
        qc.sx(1)
        base = TargetWaveformSimulator(backend_2q.target).compile(
            qc, start_times=[0, 0]
        )
        dt_ns = base.dt * 1e9
        profile = HardwareProfile(
            channels={"d1": ChannelImpairments(delay_ns=4 * dt_ns)}
        )
        sim = TargetWaveformSimulator(
            backend_2q.target, hardware_profile=profile
        ).compile(qc, start_times=[0, 0])
        assert np.array_equal(
            sim.get_snippet("d0", 0, 300).wave, base.get_snippet("d0", 0, 300).wave
        )
        assert np.array_equal(
            sim.get_snippet("d1", 0, 300).wave[4:],
            base.get_snippet("d1", 0, 300).wave[:-4],
        )


class TestStages:
    def test_amp_scale(self, backend_2q):
        ideal = build_sim(backend_2q).get_snippet("d0", 0, 300)
        imp = build_sim(backend_2q, single(amp_scale=0.8)).get_snippet("d0", 0, 300)
        assert np.allclose(imp.wave, 0.8 * ideal.wave, atol=1e-15)

    def test_dc_offset_is_added_everywhere(self, backend_2q):
        ideal = build_sim(backend_2q).get_snippet("d0", 0, 300)
        imp = build_sim(backend_2q, single(dc_i=0.01, dc_q=-0.02)).get_snippet(
            "d0", 0, 300
        )
        assert np.allclose(imp.wave, ideal.wave + (0.01 - 0.02j), atol=1e-15)

    def test_dc_offset_shows_in_an_empty_channel(self, backend_2q):
        sim = build_sim(backend_2q, single(dc_i=0.01, dc_q=-0.02))
        assert "d1" not in sim.get_channels()
        snip = sim.get_snippet("d1", 0, 50)
        assert np.all(snip.wave == complex(0.01, -0.02))
        assert snip.events == []

    def test_empty_channel_without_dc_stays_zero(self, backend_2q):
        sim = build_sim(
            backend_2q, single(delay_ns=3.0, dac_bits=12, bandwidth_mhz=300)
        )
        assert np.all(sim.get_snippet("d1", 0, 50).wave == 0)

    def test_dac_full_scale_clips_to_the_top_code(self, backend_2q):
        bits = 8
        lsb = 2.0 ** -(bits - 1)
        sim = build_sim(
            backend_2q,
            single(dac_bits=bits),
            layout=(("box", 0, 400),),
            shape="gaussian_square",
            amp=1.0,
        )
        wave = sim.get_snippet("d0", 0, 400).wave
        assert wave.real.max() == 1.0 - lsb
        assert np.allclose(wave.real / lsb, np.round(wave.real / lsb))

    def test_bandwidth_matches_the_reference_filter(self, backend_2q):
        ideal_sim = build_sim(backend_2q, shape="gaussian_square")
        bw = 250e6
        sim = build_sim(
            backend_2q, single(bandwidth_mhz=bw / 1e6), shape="gaussian_square"
        )
        ideal = ideal_sim.get_snippet("d0", 0, 500)
        imp = sim.get_snippet("d0", 0, 500)
        assert np.allclose(imp.wave, lowpass(ideal.wave, bw, sim.dt), atol=1e-12)

    def test_overlapping_windows_agree_without_a_filter(self, backend_2q):
        sim = build_sim(backend_2q, single(delay_ns=3.3, dac_bits=10, dc_i=0.005))
        full = sim.get_snippet("d0", 0, 500).wave
        part = sim.get_snippet("d0", 120, 200).wave
        assert np.array_equal(full[120:320], part)

    def test_overlapping_windows_agree_with_a_filter_to_tolerance(self, backend_2q):
        sim = build_sim(
            backend_2q,
            single(delay_ns=3.3, bandwidth_mhz=200.0),
            shape="gaussian_square",
        )
        full = sim.get_snippet("d0", 0, 500).wave
        part = sim.get_snippet("d0", 120, 200).wave
        scale = np.max(np.abs(full))
        assert np.max(np.abs(full[120:320] - part)) <= 1e-12 * scale

    def test_image_ratio_matches_the_analytic_formula(self, backend_2q):
        eps, phi_deg = 0.05, 2.0
        n_fft, cycles = 2048, 100
        probe = build_sim(backend_2q)
        if_hz = cycles / (n_fft * probe.dt)
        sim = build_sim(
            backend_2q,
            single(gain_imbalance=eps, phase_error_deg=phi_deg),
            layout=(("box", 0, 4352),),
            shape="gaussian_square",
            if_freq_hz=if_hz,
        )
        wave = sim.get_snippet("d0", 1024, n_fft).wave
        spec = np.fft.fft(wave) / n_fft
        measured = abs(spec[-cycles]) / abs(spec[cycles])
        phi = math.radians(phi_deg)
        g1, g2 = 1 + eps / 2, 1 - eps / 2
        alpha = g1 / 2 + g2 * cmath.exp(-1j * phi) / 2
        beta = g1 / 2 - g2 * cmath.exp(1j * phi) / 2
        assert measured == pytest.approx(abs(beta / alpha), rel=1e-6)

    def test_stage_order_is_gain_dac_filter_mixer_dc(self, backend_2q):
        ideal_sim = build_sim(backend_2q, shape="gaussian_square")
        imp = ChannelImpairments(
            amp_scale=0.9,
            dac_bits=6,
            bandwidth_mhz=300.0,
            gain_imbalance=0.04,
            phase_error_deg=2.0,
            dc_i=0.003,
            dc_q=-0.002,
        )
        sim = build_sim(
            backend_2q, HardwareProfile(default=imp, seed=1), shape="gaussian_square"
        )
        ideal = ideal_sim.get_snippet("d0", 0, 400).wave
        expected = lowpass(quantize_dac(0.9 * ideal, 6), 300e6, sim.dt)
        expected = apply_iq_imbalance(expected, 0.04, 2.0) + complex(0.003, -0.002)
        assert np.allclose(sim.get_snippet("d0", 0, 400).wave, expected, atol=1e-12)

    def test_time_axis_is_unchanged_by_impairments(self, backend_2q):
        base = build_sim(backend_2q).get_snippet("d0", 0, 300)
        imp = build_sim(backend_2q, single(delay_ns=5.0)).get_snippet("d0", 0, 300)
        assert np.array_equal(base.time_ns, imp.time_ns)
