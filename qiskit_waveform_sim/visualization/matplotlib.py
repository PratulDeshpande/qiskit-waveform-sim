"""
Matplotlib-based static visualization for qiskit-waveform-sim.

Provides publication-quality static plots for papers and documentation.
"""

from __future__ import annotations

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

from qiskit_waveform_sim.core import TargetWaveformSimulator, WaveformSnippet


def plot_pulse_sheet(
    sim: TargetWaveformSimulator,
    ax: plt.Axes | None = None,
    channels: list[str] | None = None,
    time_range_ns: tuple[float, float] | None = None,
    figsize: tuple[float, float] = (12, 6),
    show_phase_markers: bool = True,
) -> Figure:
    """
    Create a static Matplotlib pulse sheet (multi-channel schedule view).

    Parameters
    ----------
    sim : TargetWaveformSimulator
        Compiled waveform simulator
    ax : plt.Axes, optional
        Existing axes to plot on
    channels : List[str], optional
        Channels to display (default: all)
    time_range_ns : Tuple[float, float], optional
        Time window in ns (default: full circuit)
    figsize : Tuple[float, float]
        Figure size if creating new figure
    show_phase_markers : bool
        Show virtual Z phase markers

    Returns
    -------
    Figure
        Matplotlib figure
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure  # type: ignore

    all_channels = sim.get_channels()
    display_channels = channels or all_channels
    display_channels = [ch for ch in display_channels if ch in all_channels]

    if not display_channels:
        ax.text(
            0.5,
            0.5,
            "No events to display",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        return fig

    # Time range
    if time_range_ns:
        t_start_ns, t_stop_ns = time_range_ns
        t_start_dt = int(t_start_ns / (sim.dt * 1e9))
        t_stop_dt = int(t_stop_ns / (sim.dt * 1e9))
    else:
        t_start_dt = 0
        t_stop_dt = sim.total_duration_dt

    t_start_ns = t_start_dt * sim.dt * 1e9
    t_stop_ns = t_stop_dt * sim.dt * 1e9

    # Color scheme
    op_colors = {
        "drag": "#1f77b4",
        "gaussian_square": "#2ca02c",
        "virtual_z": "#ff7f0e",
        "measure": "#d62728",
        "ecr_echo_x": "#9467bd",
        "default": "#7f7f7f",
    }

    n_channels = len(display_channels)
    channel_height = 0.8 / n_channels

    for i, channel in enumerate(display_channels):
        y_base = 1.0 - (i + 1) * (1.0 / n_channels)
        y_top = y_base + channel_height
        y_center = (y_base + y_top) / 2

        events = sim.events_by_channel.get(channel, [])
        visible_events = [
            ev
            for ev in events
            if ev.start_dt + ev.duration_dt > t_start_dt and ev.start_dt < t_stop_dt
        ]

        for ev in visible_events:
            ev_start_ns = ev.start_dt * sim.dt * 1e9
            ev_stop_ns = (ev.start_dt + ev.duration_dt) * sim.dt * 1e9

            ev_start_ns = max(ev_start_ns, t_start_ns)
            ev_stop_ns = min(ev_stop_ns, t_stop_ns)
            ev_duration_ns = ev_stop_ns - ev_start_ns

            if ev_duration_ns <= 0:
                continue

            color = op_colors.get(ev.shape, op_colors["default"])

            # Pulse rectangle
            rect = mpatches.Rectangle(
                (ev_start_ns, y_base + 0.05 * channel_height),
                ev_duration_ns,
                0.9 * channel_height,
                facecolor=color,
                edgecolor=color,
                alpha=0.7,
                linewidth=0.5,
            )
            ax.add_patch(rect)

            # Label
            if ev.shape != "virtual_z" or ev.duration_dt > 0:
                label = ev.op_name
                ax.text(
                    (ev_start_ns + ev_stop_ns) / 2,
                    y_center,
                    label,
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white",
                    fontweight="bold" if ev.shape == "drag" else "normal",
                )

            # Virtual Z marker
            if ev.shape == "virtual_z" and show_phase_markers:
                ax.axvline(ev_start_ns, color="red", linestyle="--", linewidth=1, alpha=0.8)
                ax.text(
                    ev_start_ns,
                    y_top + 0.02,
                    f"φ={ev.frame_phase_rad:.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    color="red",
                    rotation=90,
                )

        # Channel label
        ax.text(
            t_start_ns - (t_stop_ns - t_start_ns) * 0.02,
            y_center,
            channel,
            ha="right",
            va="center",
            fontsize=10,
            fontweight="bold",
        )

    ax.set_xlim(t_start_ns, t_stop_ns)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Time (ns)", fontsize=12)
    ax.set_title("Pulse Sheet - Multi-Channel Schedule", fontsize=14, fontweight="bold")
    ax.set_yticks([])
    ax.grid(True, axis="x", alpha=0.3)

    # Legend
    legend_elements = [
        mpatches.Patch(color=op_colors["drag"], label="Single-Qubit (DRAG)"),
        mpatches.Patch(
            color=op_colors["gaussian_square"],
            label="Two-Qubit/Measure (GaussianSquare)",
        ),
        mpatches.Patch(color=op_colors["virtual_z"], label="Virtual-Z"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=9)

    plt.tight_layout()
    return fig


def plot_iq_waveforms(
    snippet: WaveformSnippet,
    ax: plt.Axes | None = None,
    figsize: tuple[float, float] = (12, 5),
    show_envelope: bool = True,
    show_phase: bool = True,
    show_events: bool = True,
) -> Figure:
    """
    Plot I/Q waveforms from a WaveformSnippet.

    Parameters
    ----------
    snippet : WaveformSnippet
        Waveform snippet from TargetWaveformSimulator.get_snippet()
    ax : plt.Axes or array of Axes, optional
        Existing axes (2 or 3 axes for I/Q/Phase)
    figsize : Tuple[float, float]
        Figure size if creating new figure
    show_envelope : bool
        Show magnitude envelope
    show_phase : bool
        Show phase trace
    show_events : bool
        Show event boundaries

    Returns
    -------
    Figure
        Matplotlib figure
    """
    time_ns = snippet.time_ns
    wave = snippet.wave
    phase_rad = snippet.phase_rad
    events = snippet.events

    n_rows = 2 + (1 if show_phase else 0)
    if ax is None:
        fig, axes = plt.subplots(n_rows, 1, figsize=figsize, sharex=True)
    else:
        axes = [ax] if not isinstance(ax, (list, np.ndarray)) else ax
        fig = axes[0].figure
        if len(axes) < n_rows:
            # Need to create more axes
            for _ in range(n_rows - len(axes)):
                new_ax = fig.add_subplot(n_rows, 1, len(axes) + 1, sharex=axes[0])
                axes.append(new_ax)

    # I component
    axes[0].plot(time_ns, wave.real, label="I (Real)", color="#1f77b4", linewidth=0.8)
    if show_envelope:
        envelope = np.abs(wave)
        axes[0].plot(time_ns, envelope, color="gray", linewidth=0.5, linestyle="--", alpha=0.5)
        axes[0].plot(time_ns, -envelope, color="gray", linewidth=0.5, linestyle="--", alpha=0.5)
    axes[0].set_ylabel("Amplitude", fontsize=10)
    axes[0].set_title(f"Channel: {snippet.channel} - I/Q Waveforms", fontsize=12, fontweight="bold")
    axes[0].legend(loc="upper right", fontsize=9)
    axes[0].grid(True, alpha=0.3)

    # Q component
    axes[1].plot(time_ns, wave.imag, label="Q (Imag)", color="#ff7f0e", linewidth=0.8)
    if show_envelope:
        envelope = np.abs(wave)
        axes[1].plot(time_ns, envelope, color="gray", linewidth=0.5, linestyle="--", alpha=0.5)
        axes[1].plot(time_ns, -envelope, color="gray", linewidth=0.5, linestyle="--", alpha=0.5)
    axes[1].set_ylabel("Amplitude", fontsize=10)
    axes[1].legend(loc="upper right", fontsize=9)
    axes[1].grid(True, alpha=0.3)

    # Phase
    if show_phase:
        axes[2].plot(time_ns, phase_rad, label="Frame Phase", color="#d62728", linewidth=0.8)
        axes[2].set_ylabel("Phase (rad)", fontsize=10)
        axes[2].set_xlabel("Time (ns)", fontsize=10)
        axes[2].legend(loc="upper right", fontsize=9)
        axes[2].grid(True, alpha=0.3)
    else:
        axes[1].set_xlabel("Time (ns)", fontsize=10)

    # Event markers
    if show_events:
        for ev in events:
            if ev.duration_dt > 0:
                ev_start = ev.start_dt * snippet.dt_sec * 1e9
                ev_stop = (ev.start_dt + ev.duration_dt) * snippet.dt_sec * 1e9
                for a in axes:
                    a.axvspan(ev_start, ev_stop, alpha=0.1, color="#2ca02c")
                axes[0].text(
                    (ev_start + ev_stop) / 2,
                    axes[0].get_ylim()[1] * 0.95,
                    ev.op_name,
                    ha="center",
                    va="top",
                    fontsize=8,
                    color="#2ca02c",
                    bbox={
                        "boxstyle": "round,pad=0.2",
                        "facecolor": "white",
                        "alpha": 0.8,
                        "edgecolor": "#2ca02c",
                    },
                )

    plt.tight_layout()
    return fig


def plot_multi_channel_iq(
    sim: TargetWaveformSimulator,
    channels: list[str],
    start_dt: int = 0,
    length_dt: int | None = None,
    figsize: tuple[float, float] = (14, 8),
) -> Figure:
    """
    Plot I/Q waveforms for multiple channels in a grid.

    Parameters
    ----------
    sim : TargetWaveformSimulator
        Compiled waveform simulator
    channels : List[str]
        Channels to plot
    start_dt : int
        Start time in dt
    length_dt : int, optional
        Window length in dt
    figsize : Tuple[float, float]
        Figure size

    Returns
    -------
    Figure
        Matplotlib figure with subplots
    """
    n_channels = len(channels)
    fig, axes = plt.subplots(n_channels, 2, figsize=figsize, sharex=True, squeeze=False)

    for i, channel in enumerate(channels):
        snippet = sim.get_snippet(channel, start_dt, length_dt)
        time_ns = snippet.time_ns
        wave = snippet.wave

        # I
        axes[i, 0].plot(time_ns, wave.real, color="#1f77b4", linewidth=0.7)
        axes[i, 0].set_ylabel(f"{channel}\nI", fontsize=9)
        axes[i, 0].grid(True, alpha=0.3)
        if i == 0:
            axes[i, 0].set_title("In-Phase (I)", fontsize=11)

        # Q
        axes[i, 1].plot(time_ns, wave.imag, color="#ff7f0e", linewidth=0.7)
        axes[i, 1].set_ylabel("Q", fontsize=9)
        axes[i, 1].grid(True, alpha=0.3)
        if i == 0:
            axes[i, 1].set_title("Quadrature (Q)", fontsize=11)

    axes[-1, 0].set_xlabel("Time (ns)", fontsize=11)
    axes[-1, 1].set_xlabel("Time (ns)", fontsize=11)

    fig.suptitle("Multi-Channel I/Q Waveforms", fontsize=14, fontweight="bold")
    plt.tight_layout()
    return fig


def plot_phase_tracking(
    sim: TargetWaveformSimulator,
    qubits: list[int] | None = None,
    ax: plt.Axes | None = None,
    figsize: tuple[float, float] = (12, 4),
) -> Figure:
    """
    Plot Virtual-Z frame phase accumulation over time for qubits.

    Parameters
    ----------
    sim : TargetWaveformSimulator
        Compiled waveform simulator
    qubits : List[int], optional
        Qubits to plot (default: all)
    ax : plt.Axes, optional
        Existing axes
    figsize : Tuple[float, float]
        Figure size if creating new figure

    Returns
    -------
    Figure
        Matplotlib figure
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure  # type: ignore

    all_qubits = list(sim.phase_history.keys())
    display_qubits = qubits or all_qubits
    display_qubits = [q for q in display_qubits if q in all_qubits]

    if not display_qubits:
        ax.text(
            0.5,
            0.5,
            "No phase history available",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        return fig

    colors = plt.cm.tab10(np.linspace(0, 1, len(display_qubits)))

    for q, color in zip(display_qubits, colors, strict=False):
        history = sim.phase_history[q]
        if not history:
            continue

        times_dt = [h[0] for h in history]
        phases = [h[1] for h in history]
        times_ns = np.array(times_dt) * sim.dt * 1e9

        # Step plot for phase changes
        ax.step(times_ns, phases, where="post", label=f"Q{q}", color=color, linewidth=1.5)
        ax.scatter(times_ns, phases, color=color, s=20, zorder=5)

    ax.set_xlabel("Time (ns)", fontsize=12)
    ax.set_ylabel("Frame Phase (rad)", fontsize=12)
    ax.set_title("Virtual-Z Frame Phase Tracking", fontsize=14, fontweight="bold")
    ax.legend(fontsize=9, loc="upper right")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    return fig
