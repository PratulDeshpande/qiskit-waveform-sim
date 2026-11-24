"""
Tests for the control-hardware impairment model (qiskit_waveform_sim.hardware).

Pure data and signal-processing tests; simulator integration lives in
test_hardware_simulator.py.
"""

import cmath
import json
import math

import numpy as np
import pytest

from qiskit_waveform_sim.hardware import (
    ChannelImpairments,
    HardwareProfile,
    apply_iq_imbalance,
    lowpass,
    lowpass_lookback,
    quantize_dac,
)

DT = 1 / 4.5e9


class TestChannelImpairments:
    def test_defaults_are_ideal(self):
        assert ChannelImpairments().is_ideal

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"delay_ns": 1.0},
            {"amp_scale": 0.9},
            {"gain_imbalance": 0.01},
            {"phase_error_deg": 1.0},
            {"dc_i": 0.01},
            {"dc_q": -0.01},
            {"dac_bits": 12},
            {"bandwidth_mhz": 500.0},
        ],
    )
    def test_any_nonneutral_field_is_not_ideal(self, kwargs):
        assert not ChannelImpairments(**kwargs).is_ideal

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"delay_ns": -0.1},
            {"delay_ns": float("nan")},
            {"delay_ns": float("inf")},
            {"amp_scale": 0.0},
            {"amp_scale": -1.0},
            {"gain_imbalance": 1.0},
            {"gain_imbalance": -1.5},
            {"phase_error_deg": 90.0},
            {"dc_i": float("nan")},
            {"dac_bits": 1},
            {"dac_bits": 33},
            {"dac_bits": 8.5},
            {"dac_bits": True},
            {"bandwidth_mhz": 0.0},
            {"bandwidth_mhz": -5.0},
        ],
    )
    def test_invalid_values_raise(self, kwargs):
        with pytest.raises(ValueError):
            ChannelImpairments(**kwargs)

    def test_delay_split_is_exact_for_whole_samples(self):
        """floor(delay_ns*1e-9/dt) loses 34 of the first 1999 whole-sample delays."""
        for k in range(1, 2000):
            delay_ns = k * DT * 1e9
            assert ChannelImpairments(delay_ns=delay_ns).delay_split(DT) == (k, 0.0)

    def test_delay_split_fractional(self):
        k, f = ChannelImpairments(delay_ns=2.5 * DT * 1e9).delay_split(DT)
        assert k == 2
        assert f == pytest.approx(0.5)


class TestHardwareProfileLookup:
    def _profile(self):
        return HardwareProfile(
            default=ChannelImpairments(delay_ns=1.0),
            channels={
                "d*": ChannelImpairments(delay_ns=2.0),
                "d[0-1]": ChannelImpairments(delay_ns=3.0),
                "d0": ChannelImpairments(delay_ns=4.0),
                "u(*)": ChannelImpairments(delay_ns=5.0),
            },
            seed=1,
        )

    def test_exact_beats_glob_beats_default(self):
        p = self._profile()
        assert p.for_channel("d0").delay_ns == 4.0  # exact
        assert p.for_channel("d2").delay_ns == 2.0  # glob
        assert p.for_channel("m0").delay_ns == 1.0  # default

    def test_first_matching_glob_wins(self):
        # "d*" is listed before "d[0-1]", so it wins for d1
        assert self._profile().for_channel("d1").delay_ns == 2.0

    def test_pair_channel_glob(self):
        assert self._profile().for_channel("u(0,1)").delay_ns == 5.0

    def test_matching_is_case_sensitive(self):
        # fnmatch.fnmatch would fold case on Windows and match "D0" with "d*"
        assert self._profile().for_channel("D0").delay_ns == 1.0

    def test_exact_key_must_be_a_channel_name(self):
        with pytest.raises(ValueError, match="channel"):
            HardwareProfile(channels={"drive0": ChannelImpairments()})

    def test_glob_key_is_accepted(self):
        HardwareProfile(channels={"d*": ChannelImpairments()})

    def test_seed_is_drawn_once_when_omitted(self):
        a = HardwareProfile()
        assert isinstance(a.seed, int)
        assert a.seed == a.seed
        assert HardwareProfile(seed=7).seed == 7

    def test_validate_for_dt_rejects_bandwidth_at_nyquist(self):
        nyquist_mhz = 0.5 / DT / 1e6
        bad = HardwareProfile(default=ChannelImpairments(bandwidth_mhz=nyquist_mhz))
        with pytest.raises(ValueError, match="Nyquist"):
            bad.validate_for_dt(DT)
        ok = HardwareProfile(
            channels={"d0": ChannelImpairments(bandwidth_mhz=nyquist_mhz * 0.9)}
        )
        ok.validate_for_dt(DT)


class TestHardwareProfileFiles:
    def _profile(self):
        return HardwareProfile(
            default=ChannelImpairments(dac_bits=14, dc_i=0.002),
            channels={
                "u(*)": ChannelImpairments(delay_ns=12.0, dac_bits=14, dc_i=0.002),
                "d0": ChannelImpairments(gain_imbalance=0.02, phase_error_deg=1.5),
            },
            seed=7,
        )

    def test_json_round_trip(self, tmp_path):
        path = tmp_path / "lab.json"
        original = self._profile()
        original.to_file(path)
        assert HardwareProfile.from_file(path) == original

    def test_to_file_rejects_other_suffixes(self, tmp_path):
        with pytest.raises(ValueError, match="json"):
            self._profile().to_file(tmp_path / "lab.toml")

    def test_toml_load(self, tmp_path):
        path = tmp_path / "lab.toml"
        path.write_text(
            'seed = 3\n[default]\ndac_bits = 12\n[channels."u(*)"]\ndelay_ns = 12.0\n',
            encoding="utf-8",
        )
        p = HardwareProfile.from_file(path)
        assert p.seed == 3
        assert p.for_channel("u(0,1)").delay_ns == 12.0
        # keys left out of a channel entry come from the file's default entry
        assert p.for_channel("u(0,1)").dac_bits == 12
        assert p.for_channel("d0").dac_bits == 12

    def test_unknown_key_raises(self, tmp_path):
        path = tmp_path / "typo.json"
        path.write_text(json.dumps({"default": {"delay_nss": 1.0}}), encoding="utf-8")
        with pytest.raises(ValueError, match="delay_nss"):
            HardwareProfile.from_file(path)

    def test_unknown_top_level_key_raises(self):
        with pytest.raises(ValueError, match="chanels"):
            HardwareProfile.from_dict({"chanels": {}})

    def test_unsupported_suffix_raises(self, tmp_path):
        path = tmp_path / "lab.yaml"
        path.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="suffix"):
            HardwareProfile.from_file(path)


class TestPresets:
    @pytest.mark.parametrize(
        "name",
        [
            "ideal",
            "iq_mixer_uncalibrated",
            "iq_mixer_calibrated",
            "direct_rf",
            "noisy_lab",
        ],
    )
    def test_preset_loads_and_validates(self, name):
        p = HardwareProfile.from_preset(name, seed=1)
        p.validate_for_dt(DT)
        assert p.seed == 1

    def test_ideal_preset_is_ideal(self):
        p = HardwareProfile.from_preset("ideal")
        assert p.default.is_ideal
        assert not p.channels

    def test_uncalibrated_mixer_is_worse_than_calibrated(self):
        un = HardwareProfile.from_preset("iq_mixer_uncalibrated").default
        cal = HardwareProfile.from_preset("iq_mixer_calibrated").default
        assert abs(un.gain_imbalance) > abs(cal.gain_imbalance)
        assert abs(un.phase_error_deg) > abs(cal.phase_error_deg)

    def test_unknown_preset_lists_choices(self):
        with pytest.raises(ValueError, match="iq_mixer_uncalibrated"):
            HardwareProfile.from_preset("acme_awg_9000")


class TestSignalHelpers:
    def test_quantize_error_is_at_most_half_lsb(self):
        bits = 8
        lsb = 2.0 ** -(bits - 1)
        x = np.linspace(-1.0, 1.0 - lsb / 2, 4001)
        q = quantize_dac(x.astype(np.complex128), bits)
        assert np.max(np.abs(q.real - x)) <= lsb / 2 + 1e-15
        assert np.all(q.imag == 0.0)

    def test_quantize_full_scale_clips_to_top_code(self):
        bits = 8
        lsb = 2.0 ** -(bits - 1)
        q = quantize_dac(np.array([1.0 + 1.0j, -1.0 - 1.0j, 3.0 - 3.0j]), bits)
        assert q[0] == complex(1.0 - lsb, 1.0 - lsb)
        assert q[1] == complex(-1.0, -1.0)
        assert q[2] == complex(1.0 - lsb, -1.0)

    def test_quantize_outputs_lie_on_the_code_grid(self):
        bits = 6
        lsb = 2.0 ** -(bits - 1)
        rng = np.random.default_rng(0)
        q = quantize_dac(rng.uniform(-1, 1, 500) + 1j * rng.uniform(-1, 1, 500), bits)
        assert np.allclose(q.real / lsb, np.round(q.real / lsb))
        assert np.allclose(q.imag / lsb, np.round(q.imag / lsb))

    def test_lowpass_step_response_and_dc_gain(self):
        bw_hz = 300e6
        a = math.exp(-2 * math.pi * bw_hz * DT)
        y = lowpass(np.ones(400, dtype=np.complex128), bw_hz, DT)
        n = np.arange(400)
        assert np.allclose(y.real, 1.0 - a ** (n + 1), atol=1e-12)
        assert y[-1].real == pytest.approx(1.0, abs=1e-12)

    def test_lowpass_matches_direct_recursion_on_random_input(self):
        bw_hz = 150e6
        a = math.exp(-2 * math.pi * bw_hz * DT)
        rng = np.random.default_rng(1)
        x = rng.normal(size=300) + 1j * rng.normal(size=300)
        expected = np.empty_like(x)
        state = 0.0 + 0.0j
        for i, v in enumerate(x):
            state = (1 - a) * v + a * state
            expected[i] = state
        assert np.allclose(lowpass(x, bw_hz, DT), expected, atol=1e-12)

    def test_lowpass_lookback_bounds_the_truncation_error(self):
        bw_hz = 200e6
        a = math.exp(-2 * math.pi * bw_hz * DT)
        n = lowpass_lookback(bw_hz, DT)
        assert a**n <= 1e-12
        assert a ** (n - 1) > 1e-12

    def test_iq_imbalance_image_ratio_matches_analytic(self):
        eps, phi_deg = 0.05, 2.0
        phi = math.radians(phi_deg)
        n = 4096
        cycles = 100
        tone = np.exp(2j * np.pi * cycles * np.arange(n) / n)
        out = apply_iq_imbalance(tone, eps, phi_deg)
        spec = np.fft.fft(out) / n
        measured = abs(spec[-cycles]) / abs(spec[cycles])
        g1, g2 = 1 + eps / 2, 1 - eps / 2
        alpha = g1 / 2 + g2 * cmath.exp(-1j * phi) / 2
        beta = g1 / 2 - g2 * cmath.exp(1j * phi) / 2
        assert measured == pytest.approx(abs(beta / alpha), rel=1e-9)

    def test_iq_imbalance_zero_is_identity(self):
        x = np.array([0.3 + 0.4j, -0.2 + 0.1j])
        assert np.array_equal(apply_iq_imbalance(x, 0.0, 0.0), x)
