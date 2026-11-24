"""
Visualization tests for hardware impairment profiles (Phase 1).

The pulse sheet shows skewed blocks plus a ghost at the ideal position; the I/Q
oscilloscope can overlay the ideal waveform on the impaired one.
"""

import numpy as np
import pytest

from qiskit_waveform_sim import (
    ChannelImpairments,
    HardwareProfile,
    PulseSheetConfig,
    TargetWaveformSimulator,
    create_combined_view,
    create_iq_oscilloscope,
    create_pulse_sheet,
    show_iq_oscilloscope,
)

DELAY_NS = 10.0


@pytest.fixture
def skewed(simple_circuit, backend_2q):
    """d0 delayed by 10 ns, every other channel (m0, m1, u(0,1)) untouched."""
    profile = HardwareProfile(
        channels={"d0": ChannelImpairments(delay_ns=DELAY_NS)}, seed=1
    )
    return TargetWaveformSimulator(backend_2q.target, hardware_profile=profile).compile(
        simple_circuit
    )


def row_shapes(fig, sim, channel, *, shape_type="rect"):
    idx = sim.get_channels().index(channel) + 1
    yref = "y" if idx == 1 else f"y{idx}"
    return [s for s in fig.layout.shapes if s.type == shape_type and s.yref == yref]


def is_ghost(shape):
    return shape.line.dash == "dot"


class TestPulseSheetSkew:
    def test_titles_show_the_skew_only_on_delayed_channels(self, skewed):
        titles = [a.text for a in create_pulse_sheet(skewed).layout.annotations]
        assert "<b>d0</b> (+10.0 ns)" in titles
        assert "<b>m0</b>" in titles

    def test_blocks_move_by_the_delay(self, skewed, compiled_simulator):
        base = create_pulse_sheet(compiled_simulator)
        fig = create_pulse_sheet(skewed)
        expected = sorted(
            s.x0 + DELAY_NS for s in row_shapes(base, compiled_simulator, "d0")
        )
        solid = [s for s in row_shapes(fig, skewed, "d0") if not is_ghost(s)]
        assert sorted(s.x0 for s in solid) == pytest.approx(expected)

    def test_ghost_marks_the_ideal_position(self, skewed, compiled_simulator):
        base = create_pulse_sheet(compiled_simulator)
        fig = create_pulse_sheet(skewed)
        ghosts = [s for s in row_shapes(fig, skewed, "d0") if is_ghost(s)]
        ideal = [s.x0 for s in row_shapes(base, compiled_simulator, "d0")]
        assert sorted(s.x0 for s in ghosts) == pytest.approx(sorted(ideal))

    def test_no_ghost_without_a_delay(self, skewed):
        fig = create_pulse_sheet(skewed)
        assert row_shapes(fig, skewed, "m0")  # the channel does have blocks
        assert not [s for s in row_shapes(fig, skewed, "m0") if is_ghost(s)]

    def test_ghost_can_be_disabled(self, skewed):
        fig = create_pulse_sheet(skewed, PulseSheetConfig(show_ideal_ghost=False))
        assert not [
            s
            for ch in skewed.get_channels()
            for s in row_shapes(fig, skewed, ch)
            if is_ghost(s)
        ]

    def test_ideal_simulator_is_drawn_exactly_as_before(self, compiled_simulator):
        fig = create_pulse_sheet(compiled_simulator)
        assert not [s for s in fig.layout.shapes if is_ghost(s)]
        assert all("ns)" not in a.text for a in fig.layout.annotations)

    def test_virtual_z_markers_move_with_the_channel(self, skewed, compiled_simulator):
        def marker_x(fig, sim):
            return sorted(s.x0 for s in row_shapes(fig, sim, "d0", shape_type="line"))

        base = marker_x(create_pulse_sheet(compiled_simulator), compiled_simulator)
        moved = marker_x(create_pulse_sheet(skewed), skewed)
        assert base  # h(0) lowers to rz-sx-rz
        assert moved == pytest.approx([x + DELAY_NS for x in base])

    def test_time_axis_extends_to_show_the_delayed_tail(self, skewed):
        fig = create_pulse_sheet(skewed)
        stops = [
            fig.layout[k].range[1]
            for k in fig.layout
            if k.startswith("xaxis") and fig.layout[k].range
        ]
        end_ns = (skewed.total_duration_dt + skewed.channel_delay_dt("d0")) * (
            skewed.dt * 1e9
        )
        assert max(stops) == pytest.approx(end_ns)


class TestOscilloscopeCompare:
    def test_compare_ideal_overlays_dashed_ideal_traces(self, skewed):
        fig = create_iq_oscilloscope(skewed, "d0", 0, 600, compare_ideal=True)
        by_name = {t.name: t for t in fig.data}
        ideal = skewed.get_snippet("d0", 0, 600, ideal=True)
        impaired = skewed.get_snippet("d0", 0, 600)
        assert by_name["I (ideal)"].line.dash == "dash"
        assert np.array_equal(by_name["I (ideal)"].y, ideal.wave.real)
        assert np.array_equal(by_name["Q (ideal)"].y, ideal.wave.imag)
        assert np.array_equal(by_name["I"].y, impaired.wave.real)

    def test_default_has_no_ideal_traces(self, skewed):
        fig = create_iq_oscilloscope(skewed, "d0", 0, 600)
        assert "I (ideal)" not in {t.name for t in fig.data}

    def test_compare_ideal_is_a_noop_without_a_profile(self, compiled_simulator):
        fig = create_iq_oscilloscope(
            compiled_simulator, "d0", 0, 600, compare_ideal=True
        )
        assert "I (ideal)" not in {t.name for t in fig.data}

    def test_show_function_passes_compare_ideal_through(self, skewed):
        fig = show_iq_oscilloscope(
            skewed, "d0", 0, 600, interactive=False, compare_ideal=True
        )
        assert fig is not None
        assert "Q (ideal)" in {t.name for t in fig.data}

    def test_event_bands_sit_on_the_delayed_pulse(self, skewed):
        fig = create_iq_oscilloscope(skewed, "d0", 0, 600)
        snippet = skewed.get_snippet("d0", 0, 600)
        pulse = next(e for e in snippet.events if e.duration_dt > 0)
        x0 = pulse.start_dt * skewed.dt * 1e9 + DELAY_NS
        assert any(abs(s.x0 - x0) < 1e-9 for s in fig.layout.shapes if s.type == "rect")


class TestCombinedView:
    def test_blocks_move_with_the_delay(self, skewed, compiled_simulator):
        def d0_x0(sim):
            fig = create_combined_view(sim, "d0", 0, 1500)
            return sorted(s.x0 for s in row_shapes(fig, sim, "d0"))

        assert d0_x0(skewed) == pytest.approx(
            [x + DELAY_NS for x in d0_x0(compiled_simulator)]
        )
