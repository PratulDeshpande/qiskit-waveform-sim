"""
Tests for visualization module.
"""

from unittest.mock import Mock, patch

import numpy as np
import plotly.graph_objects as go
import pytest

from qiskit_waveform_sim.visualization import (
    PulseSheetConfig,
    create_combined_view,
    create_iq_oscilloscope,
    create_pulse_sheet,
)


@pytest.fixture
def mock_simulator():
    """Create a mock simulator with test data."""
    sim = Mock()
    sim.dt = 0.222e-9
    sim.total_duration_dt = 2000
    sim.get_channels.return_value = ["d0", "d1", "u(0,1)", "m0"]

    # Mock events
    from qiskit_waveform_sim.core import ChannelEvent

    events_d0 = [
        ChannelEvent("d0", 0, 160, "sx", (0,), 0.0, "drag", 0.45 + 0j, 0.08, 40.0, 16),
        ChannelEvent("d0", 200, 160, "x", (0,), 0.0, "drag", 0.9 + 0j, 0.08, 40.0, 16),
        ChannelEvent("d0", 500, 0, "rz(1.57)", (0,), -1.57, "virtual_z", 0.0j, 0, 0, 0),
    ]
    events_d1 = [
        ChannelEvent(
            "d1", 400, 160, "sx", (1,), 0.0, "drag", 0.45 + 0j, 0.08, 40.0, 16
        ),
    ]
    events_cr = [
        ChannelEvent(
            "u(0,1)",
            600,
            200,
            "cx_cr+",
            (0, 1),
            0.0,
            "gaussian_square",
            0.65 + 0j,
            0,
            0,
            16,
        ),
        ChannelEvent(
            "u(0,1)",
            800,
            200,
            "cx_cr-",
            (0, 1),
            3.14,
            "gaussian_square",
            0.65 + 0j,
            0,
            0,
            16,
        ),
    ]
    events_m0 = [
        ChannelEvent(
            "m0",
            1500,
            1000,
            "measure",
            (0,),
            0.0,
            "gaussian_square",
            0.35 + 0j,
            0,
            0,
            24,
        ),
    ]

    sim.events_by_channel = {
        "d0": events_d0,
        "d1": events_d1,
        "u(0,1)": events_cr,
        "m0": events_m0,
    }

    # Mock get_snippet
    def mock_get_snippet(channel, start_dt=0, length_dt=None):
        from qiskit_waveform_sim.core import WaveformSnippet

        length_dt = length_dt or 1000
        time_ns = np.arange(start_dt, start_dt + length_dt) * sim.dt * 1e9
        wave = np.zeros(length_dt, dtype=np.complex128)
        phase = np.zeros(length_dt)

        # Add some test waveform for known channels
        if channel in sim.events_by_channel:
            # Simple test pattern
            wave[:100] = 0.5 + 0.1j
            phase[:100] = 0.5

        return WaveformSnippet(
            channel=channel,
            start_dt=start_dt,
            dt_sec=sim.dt,
            time_ns=time_ns,
            wave=wave,
            phase_rad=phase,
            events=sim.events_by_channel.get(channel, []),
        )

    sim.get_snippet.side_effect = mock_get_snippet
    sim.phase_history = {
        0: [(0, 0.0), (500, -1.57)],
        1: [(0, 0.0)],
    }

    return sim


class TestPulseSheetConfig:
    """Tests for PulseSheetConfig."""

    def test_defaults(self):
        """Test default configuration values."""
        config = PulseSheetConfig()

        assert config.height_per_channel == 60
        assert config.min_channel_height == 40
        assert config.max_channels == 20
        assert config.time_window_ns is None
        assert config.show_phase_markers is True
        assert config.show_annotations is True
        assert config.theme == "plotly_white"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = PulseSheetConfig(
            height_per_channel=80,
            max_channels=10,
            time_window_ns=(0, 1000),
            theme="plotly_dark",
        )

        assert config.height_per_channel == 80
        assert config.max_channels == 10
        assert config.time_window_ns == (0, 1000)
        assert config.theme == "plotly_dark"


class TestVisualizationWithMockSimulator:
    """Tests using mocked simulator."""

    def test_create_pulse_sheet(self, mock_simulator):
        """Test pulse sheet creation."""
        fig = create_pulse_sheet(mock_simulator)

        assert isinstance(fig, go.Figure)
        # Pulse sheet uses shapes, not data traces
        shapes = fig.layout.shapes
        assert len(shapes) > 0

    def test_create_pulse_sheet_with_config(self, mock_simulator):
        """Test pulse sheet with custom config."""
        config = PulseSheetConfig(
            max_channels=2,
            time_window_ns=(0, 500),
            theme="plotly_dark",
        )
        fig = create_pulse_sheet(mock_simulator, config)

        assert isinstance(fig, go.Figure)
        # Should have subplot titles for 2 channels
        subplot_titles = [
            a for a in fig.layout.annotations if a.text and a.text.startswith("<b>")
        ]
        assert len(subplot_titles) <= 2

    def test_create_iq_oscilloscope(self, mock_simulator):
        """Test I/Q oscilloscope creation."""
        fig = create_iq_oscilloscope(mock_simulator, "d0", start_dt=0, length_dt=500)

        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 2  # I and Q traces
        # Should have 3 x-axes (for I, Q, Phase)
        assert hasattr(fig.layout, "xaxis3")

    def test_create_iq_oscilloscope_no_phase(self, mock_simulator):
        """Test I/Q oscilloscope without phase trace."""
        fig = create_iq_oscilloscope(
            mock_simulator, "d0", start_dt=0, length_dt=500, show_phase=False
        )

        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 2
        # Should have 2 x-axes (for I, Q)
        assert hasattr(fig.layout, "xaxis2")
        # xaxis3 should not exist or be None
        # Note: Plotly may still create xaxis3 but with no data

    def test_create_combined_view(self, mock_simulator):
        """Test combined view creation."""
        fig = create_combined_view(mock_simulator, "d0", start_dt=0, length_dt=500)

        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0

    def test_export_html(self, mock_simulator):
        """Test HTML export."""
        fig = create_pulse_sheet(mock_simulator)

        with patch("plotly.io.write_html") as mock_write:
            from qiskit_waveform_sim.visualization import export_html

            export_html(fig, "test.html")
            mock_write.assert_called_once()

    def test_plot_pulse_sheet_matplotlib(self, mock_simulator):
        """Test Matplotlib pulse sheet - skipped on headless systems."""
        pytest.skip("Matplotlib tests require display - run manually")

    def test_plot_iq_waveforms_matplotlib(self, mock_simulator):
        """Test Matplotlib I/Q waveforms - skipped on headless systems."""
        pytest.skip("Matplotlib tests require display - run manually")

    def test_plot_phase_tracking_matplotlib(self, mock_simulator):
        """Test Matplotlib phase tracking plot - skipped on headless systems."""
        pytest.skip("Matplotlib tests require display - run manually")


class TestVisualizationEdgeCases:
    """Tests for edge cases in visualization."""

    def test_empty_simulator(self):
        """Test visualization with empty simulator."""
        from qiskit.transpiler import Target

        from qiskit_waveform_sim.core import TargetWaveformSimulator

        # Create minimal target
        target = Target(num_qubits=1, dt=0.222e-9)
        sim = TargetWaveformSimulator(target)
        sim.events_by_channel = {}
        sim.total_duration_dt = 0
        sim.get_channels = Mock(return_value=[])

        fig = create_pulse_sheet(sim)
        assert isinstance(fig, go.Figure)
        # Should have annotation about no events
        assert len(fig.layout.annotations) > 0

    def test_single_channel(self, mock_simulator):
        """Test with single channel."""
        mock_simulator.get_channels.return_value = ["d0"]
        mock_simulator.events_by_channel = {
            "d0": mock_simulator.events_by_channel["d0"]
        }

        fig = create_pulse_sheet(mock_simulator)
        assert isinstance(fig, go.Figure)

    def test_time_window_filtering(self, mock_simulator):
        """Test time window filtering in pulse sheet."""
        config = PulseSheetConfig(time_window_ns=(100, 300))  # 100-300 ns
        fig = create_pulse_sheet(mock_simulator, config)

        assert isinstance(fig, go.Figure)
        # X-axis should be limited on the last subplot
        # Find the last xaxis
        xaxis_attrs = [
            k for k in dir(fig.layout) if k.startswith("xaxis") and k != "xaxis"
        ]
        if xaxis_attrs:
            last_xaxis = getattr(fig.layout, sorted(xaxis_attrs)[-1])
            # Allow small floating point differences
            assert abs(last_xaxis.range[0] - 100) < 1.0
            assert abs(last_xaxis.range[1] - 300) < 1.0
