"""
Interactive visualization for qiskit-waveform-sim.

Provides LabOne Q-style Pulse Sheet (multi-channel schedule view) and 
synchronized I/Q Oscilloscope (sample-precise waveform view) using Plotly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio

from qiskit_waveform_sim.core import TargetWaveformSimulator, WaveformSnippet, ChannelEvent


@dataclass
class PulseSheetConfig:
    """Configuration for pulse sheet visualization."""
    height_per_channel: int = 60
    min_channel_height: int = 40
    max_channels: int = 20
    time_window_ns: Optional[Tuple[float, float]] = None
    show_phase_markers: bool = True
    show_annotations: bool = True
    theme: str = "plotly_white"


def create_pulse_sheet(
    sim: TargetWaveformSimulator,
    config: Optional[PulseSheetConfig] = None,
) -> go.Figure:
    """
    Create an interactive Plotly Pulse Sheet (multi-channel schedule view).
    
    This is the primary visualization showing the logical timing structure
    across all channels, similar to LabOne Q's pulse sheet.
    
    Parameters
    ----------
    sim : TargetWaveformSimulator
        Compiled waveform simulator
    config : PulseSheetConfig, optional
        Visualization configuration
        
    Returns
    -------
    go.Figure
        Interactive Plotly figure with pulse sheet
    """
    config = config or PulseSheetConfig()
    channels = sim.get_channels()
    
    if not channels:
        fig = go.Figure()
        fig.add_annotation(text="No events to display", xref="paper", yref="paper", x=0.5, y=0.5)
        return fig
    
    # Limit channels if too many
    display_channels = channels[:config.max_channels]
    
    # Determine time range
    if config.time_window_ns:
        t_start_ns, t_stop_ns = config.time_window_ns
        t_start_dt = int(t_start_ns / (sim.dt * 1e9))
        t_stop_dt = int(t_stop_ns / (sim.dt * 1e9))
    else:
        t_start_dt = 0
        t_stop_dt = sim.total_duration_dt
    
    t_start_ns = t_start_dt * sim.dt * 1e9
    t_stop_ns = t_stop_dt * sim.dt * 1e9
    
    # Create subplots - one row per channel
    n_channels = len(display_channels)
    fig = make_subplots(
        rows=n_channels,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        subplot_titles=[f"<b>{ch}</b>" for ch in display_channels],
        row_heights=[1.0 / n_channels] * n_channels,
    )
    
    # Color scheme for different operation types
    op_colors = {
        "drag": "#1f77b4",      # Blue for single-qubit drives
        "gaussian_square": "#2ca02c",  # Green for two-qubit/measure
        "virtual_z": "#ff7f0e",  # Orange for virtual Z
        "measure": "#d62728",    # Red for measure
        "ecr_echo_x": "#9467bd", # Purple for echo
        "default": "#7f7f7f",    # Gray
    }
    
    for row_idx, channel in enumerate(display_channels, 1):
        events = sim.events_by_channel.get(channel, [])
        if not events:
            continue
            
        # Filter events in time window
        visible_events = [
            ev for ev in events
            if ev.start_dt + ev.duration_dt > t_start_dt and ev.start_dt < t_stop_dt
        ]
        
        for ev in visible_events:
            ev_start_ns = ev.start_dt * sim.dt * 1e9
            ev_stop_ns = (ev.start_dt + ev.duration_dt) * sim.dt * 1e9
            
            # Clip to window
            ev_start_ns = max(ev_start_ns, t_start_ns)
            ev_stop_ns = min(ev_stop_ns, t_stop_ns)
            ev_duration_ns = ev_stop_ns - ev_start_ns
            
            if ev_duration_ns <= 0:
                continue
            
            color = op_colors.get(ev.shape, op_colors["default"])
            
            # Add rectangle for pulse
            fig.add_shape(
                type="rect",
                x0=ev_start_ns, x1=ev_stop_ns,
                y0=0.1, y1=0.9,
                xref=f"x{row_idx}", yref=f"y{row_idx}",
                fillcolor=color,
                opacity=0.7,
                line=dict(color=color, width=1),
                layer="below",
            )
            
            # Add operation label
            label = ev.op_name
            if config.show_annotations and ev.shape != "virtual_z":
                label += f" (φ={ev.frame_phase_rad:.2f})"
            
            fig.add_annotation(
                x=(ev_start_ns + ev_stop_ns) / 2,
                y=0.5,
                xref=f"x{row_idx}", yref=f"y{row_idx}",
                text=label,
                showarrow=False,
                font=dict(size=10, color="white"),
                align="center",
            )
            
            # Add phase marker for virtual Z
            if ev.shape == "virtual_z" and config.show_phase_markers:
                fig.add_shape(
                    type="line",
                    x0=ev_start_ns, x1=ev_start_ns,
                    y0=0, y1=1,
                    xref=f"x{row_idx}", yref=f"y{row_idx}",
                    line=dict(color="red", width=2, dash="dash"),
                )
                fig.add_annotation(
                    x=ev_start_ns,
                    y=1.05,
                    xref=f"x{row_idx}", yref=f"y{row_idx}",
                    text=f"φ={ev.frame_phase_rad:.2f}",
                    showarrow=False,
                    font=dict(size=9, color="red"),
                )
    
    # Update layout
    fig.update_layout(
        title=dict(
            text="Qiskit Waveform Simulator - Pulse Sheet",
            x=0.5,
            font=dict(size=16)
        ),
        height=max(n_channels * config.height_per_channel, 400),
        showlegend=False,
        template=config.theme,
        hovermode="x unified",
        margin=dict(l=100, r=50, t=80, b=50),
    )
    
    # Update x-axes
    fig.update_xaxes(
        title_text="Time (ns)",
        row=n_channels,
        col=1,
        range=[t_start_ns, t_stop_ns],
    )
    
    # Update y-axes (hide tick labels)
    for i in range(1, n_channels + 1):
        fig.update_yaxes(visible=False, row=i, col=1)
    
    return fig


def create_iq_oscilloscope(
    sim: TargetWaveformSimulator,
    channel: str,
    start_dt: int = 0,
    length_dt: Optional[int] = None,
    show_phase: bool = True,
) -> go.Figure:
    """
    Create an interactive I/Q Oscilloscope for a specific channel and time window.
    
    This provides sample-precise waveform visualization with phase tracking,
    similar to LabOne Q's Signal tab when clicking a pulse.
    
    Parameters
    ----------
    sim : TargetWaveformSimulator
        Compiled waveform simulator
    channel : str
        Channel to display (e.g., "d0", "u(0,1)", "m0")
    start_dt : int
        Start time in dt units
    length_dt : int, optional
        Window length in dt units
    show_phase : bool
        Whether to show phase trace
        
    Returns
    -------
    go.Figure
        Interactive Plotly figure with I/Q waveforms
    """
    snippet = sim.get_snippet(channel, start_dt, length_dt)
    
    if length_dt is None:
        length_dt = len(snippet.wave)
    
    time_ns = snippet.time_ns
    wave = snippet.wave
    phase_rad = snippet.phase_rad
    
    # Create subplots
    rows = 3 if show_phase else 2
    row_heights = [0.4, 0.4, 0.2] if show_phase else [0.5, 0.5]
    subplot_titles = ("I (In-Phase)", "Q (Quadrature)", "Frame Phase (rad)") if show_phase else ("I (In-Phase)", "Q (Quadrature)")
    
    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=subplot_titles,
        row_heights=row_heights,
    )
    
    # I component
    fig.add_trace(
        go.Scatter(
            x=time_ns,
            y=wave.real,
            mode="lines",
            name="I",
            line=dict(color="#1f77b4", width=1),
            hovertemplate="Time: %{x:.2f} ns<br>I: %{y:.4f}<extra></extra>",
        ),
        row=1, col=1
    )
    
    # Q component
    fig.add_trace(
        go.Scatter(
            x=time_ns,
            y=wave.imag,
            mode="lines",
            name="Q",
            line=dict(color="#ff7f0e", width=1),
            hovertemplate="Time: %{x:.2f} ns<br>Q: %{y:.4f}<extra></extra>",
        ),
        row=2, col=1
    )
    
    # Add envelope magnitude
    envelope = np.abs(wave)
    fig.add_trace(
        go.Scatter(
            x=time_ns,
            y=envelope,
            mode="lines",
            name="|IQ|",
            line=dict(color="gray", width=1, dash="dot"),
            hovertemplate="Time: %{x:.2f} ns<br>|IQ|: %{y:.4f}<extra></extra>",
            showlegend=False,
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=time_ns,
            y=-envelope,
            mode="lines",
            name="|IQ|",
            line=dict(color="gray", width=1, dash="dot"),
            hovertemplate="Time: %{x:.2f} ns<br>|IQ|: %{y:.4f}<extra></extra>",
            showlegend=False,
        ),
        row=1, col=1
    )
    
    # Phase trace
    if show_phase:
        fig.add_trace(
            go.Scatter(
                x=time_ns,
                y=phase_rad,
                mode="lines",
                name="Phase",
                line=dict(color="#d62728", width=1),
                hovertemplate="Time: %{x:.2f} ns<br>Phase: %{y:.4f} rad<extra></extra>",
            ),
            row=3, col=1
        )
    
    # Add event markers
    for ev in snippet.events:
        if ev.duration_dt > 0:
            ev_start = ev.start_dt * sim.dt * 1e9
            ev_stop = (ev.start_dt + ev.duration_dt) * sim.dt * 1e9
            
            for row in range(1, rows + 1):
                fig.add_vrect(
                    x0=ev_start, x1=ev_stop,
                    fillcolor="rgba(0,100,80,0.1)",
                    line_width=0,
                    layer="below",
                    row=row, col=1,
                )
            
            # Add event label on top trace
            fig.add_annotation(
                x=(ev_start + ev_stop) / 2,
                y=1.02,
                xref="x", yref="paper",
                text=f"{ev.op_name}",
                showarrow=False,
                font=dict(size=10, color="#2ca02c"),
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="#2ca02c",
                borderwidth=1,
            )
    
    fig.update_layout(
        title=dict(
            text=f"I/Q Oscilloscope - Channel: {channel}",
            x=0.5,
            font=dict(size=14)
        ),
        height=600 if show_phase else 450,
        showlegend=True,
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=80, r=50, t=80, b=50),
    )
    
    fig.update_xaxes(title_text="Time (ns)", row=rows, col=1)
    fig.update_yaxes(title_text="Amplitude", row=1, col=1)
    fig.update_yaxes(title_text="Amplitude", row=2, col=1)
    if show_phase:
        fig.update_yaxes(title_text="Phase (rad)", row=3, col=1)
    
    return fig


def show_pulse_sheet(
    sim: TargetWaveformSimulator,
    interactive: bool = True,
    config: Optional[PulseSheetConfig] = None,
) -> Optional[go.Figure]:
    """
    Display the interactive pulse sheet in browser/notebook.
    
    Parameters
    ----------
    sim : TargetWaveformSimulator
        Compiled waveform simulator
    interactive : bool
        If True, opens in browser; if False, returns figure for notebook display
    config : PulseSheetConfig, optional
        Visualization configuration
        
    Returns
    -------
    go.Figure or None
        Returns the figure when interactive=False, otherwise None
    """
    fig = create_pulse_sheet(sim, config)
    if interactive:
        fig.show()
    else:
        return fig


def show_iq_oscilloscope(
    sim: TargetWaveformSimulator,
    channel: str,
    start_dt: int = 0,
    length_dt: Optional[int] = None,
    interactive: bool = True,
) -> Optional[go.Figure]:
    """
    Display the I/Q oscilloscope for a channel.
    
    Parameters
    ----------
    sim : TargetWaveformSimulator
        Compiled waveform simulator
    channel : str
        Channel to display
    start_dt : int
        Start time in dt
    length_dt : int, optional
        Window length in dt
    interactive : bool
        If True, opens in browser; if False, returns figure
        
    Returns
    -------
    go.Figure or None
        Returns the figure when interactive=False, otherwise None
    """
    fig = create_iq_oscilloscope(sim, channel, start_dt, length_dt)
    if interactive:
        fig.show()
    else:
        return fig


def create_combined_view(
    sim: TargetWaveformSimulator,
    channel: str,
    start_dt: int = 0,
    length_dt: Optional[int] = None,
    config: Optional[PulseSheetConfig] = None,
) -> go.Figure:
    """
    Create a combined view with Pulse Sheet (top) and I/Q Oscilloscope (bottom).
    
    Synchronized x-axis for coordinated exploration.
    
    Parameters
    ----------
    sim : TargetWaveformSimulator
        Compiled waveform simulator
    channel : str
        Channel for I/Q detail view
    start_dt : int
        Start time in dt
    length_dt : int, optional
        Window length in dt
    config : PulseSheetConfig, optional
        Configuration for pulse sheet
        
    Returns
    -------
    go.Figure
        Combined interactive figure
    """
    config = config or PulseSheetConfig()
    snippet = sim.get_snippet(channel, start_dt, length_dt)
    
    if length_dt is None:
        length_dt = len(snippet.wave)
    
    time_ns = snippet.time_ns
    t_start_ns = time_ns[0]
    t_stop_ns = time_ns[-1]
    
    # Create pulse sheet for the time window
    config.time_window_ns = (t_start_ns, t_stop_ns)
    pulse_fig = create_pulse_sheet(sim, config)
    
    # Create I/Q oscilloscope
    iq_fig = create_iq_oscilloscope(sim, channel, start_dt, length_dt, show_phase=True)
    
    # Combine into single figure with shared x-axis
    n_pulse_rows = len(pulse_fig.data)  # Not directly usable, reconstruct
    
    # Simpler: create fresh combined figure
    channels = sim.get_channels()
    display_channels = channels[:config.max_channels]
    n_channels = len(display_channels)
    
    total_rows = n_channels + 3  # pulse sheet rows + I + Q + Phase
    fig = make_subplots(
        rows=total_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.015,
        subplot_titles=[f"<b>{ch}</b>" for ch in display_channels] + 
                       ["I (In-Phase)", "Q (Quadrature)", "Frame Phase (rad)"],
        row_heights=[0.6 / total_rows] * n_channels + [0.4 / total_rows] * 3,
    )
    
    # Add pulse sheet traces
    op_colors = {
        "drag": "#1f77b4", "gaussian_square": "#2ca02c",
        "virtual_z": "#ff7f0e", "measure": "#d62728",
        "ecr_echo_x": "#9467bd", "default": "#7f7f7f",
    }
    
    for row_idx, ch in enumerate(display_channels, 1):
        events = sim.events_by_channel.get(ch, [])
        for ev in events:
            ev_start_ns = ev.start_dt * sim.dt * 1e9
            ev_stop_ns = (ev.start_dt + ev.duration_dt) * sim.dt * 1e9
            
            if ev_stop_ns < t_start_ns or ev_start_ns > t_stop_ns:
                continue
            
            ev_start_ns = max(ev_start_ns, t_start_ns)
            ev_stop_ns = min(ev_stop_ns, t_stop_ns)
            if ev_stop_ns <= ev_start_ns:
                continue
            
            color = op_colors.get(ev.shape, op_colors["default"])
            
            fig.add_shape(
                type="rect",
                x0=ev_start_ns, x1=ev_stop_ns,
                y0=0.1, y1=0.9,
                xref=f"x{row_idx}", yref=f"y{row_idx}",
                fillcolor=color, opacity=0.7,
                line=dict(color=color, width=1), layer="below",
            )
    
    # Add I/Q traces on last 3 rows
    iq_row = n_channels + 1
    fig.add_trace(
        go.Scatter(x=time_ns, y=snippet.wave.real, mode="lines",
                   name="I", line=dict(color="#1f77b4", width=1),
                   hovertemplate="Time: %{x:.2f} ns<br>I: %{y:.4f}<extra></extra>"),
        row=iq_row, col=1
    )
    fig.add_trace(
        go.Scatter(x=time_ns, y=snippet.wave.imag, mode="lines",
                   name="Q", line=dict(color="#ff7f0e", width=1),
                   hovertemplate="Time: %{x:.2f} ns<br>Q: %{y:.4f}<extra></extra>"),
        row=iq_row + 1, col=1
    )
    fig.add_trace(
        go.Scatter(x=time_ns, y=snippet.phase_rad, mode="lines",
                   name="Phase", line=dict(color="#d62728", width=1),
                   hovertemplate="Time: %{x:.2f} ns<br>Phase: %{y:.4f} rad<extra></extra>"),
        row=iq_row + 2, col=1
    )
    
    fig.update_layout(
        title=dict(text=f"Combined View: Pulse Sheet + I/Q Oscilloscope ({channel})", x=0.5),
        height=max(total_rows * 50, 800),
        showlegend=True,
        template="plotly_white",
        hovermode="x unified",
        margin=dict(l=100, r=50, t=80, b=50),
    )
    
    fig.update_xaxes(title_text="Time (ns)", row=total_rows, col=1, range=[t_start_ns, t_stop_ns])
    for i in range(1, n_channels + 1):
        fig.update_yaxes(visible=False, row=i, col=1)
    
    return fig


def export_html(fig: go.Figure, filename: str) -> None:
    """Export figure to standalone HTML file."""
    pio.write_html(fig, filename, include_plotlyjs="cdn", full_html=True)


def export_static(fig: go.Figure, filename: str, format: str = "png") -> None:
    """Export figure to static image (requires kaleido)."""
    fig.write_image(filename, format=format)


# Matplotlib static visualization
from qiskit_waveform_sim.visualization.matplotlib import (
    plot_pulse_sheet,
    plot_iq_waveforms,
    plot_multi_channel_iq,
    plot_phase_tracking,
)

__all__ = [
    "PulseSheetConfig",
    "create_pulse_sheet",
    "create_iq_oscilloscope",
    "show_pulse_sheet",
    "show_iq_oscilloscope",
    "create_combined_view",
    "export_html",
    "export_static",
    "plot_pulse_sheet",
    "plot_iq_waveforms",
    "plot_multi_channel_iq",
    "plot_phase_tracking",
]