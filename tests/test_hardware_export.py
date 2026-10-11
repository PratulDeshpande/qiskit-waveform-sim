"""
Tests for hardware export utilities in examples/hardware_export.py.
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure repo root is on sys.path for importing examples
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.hardware_export import (  # noqa: E402
    export_csv,
    export_laboneq,
    export_rfsoc_qick,
)
from qiskit_waveform_sim import TargetWaveformSimulator  # noqa: E402


@pytest.fixture
def sample_waveforms():
    """Create a sample waveform dictionary for export testing."""
    n_samples = 128
    dt_sec = 0.222e-9
    t_ns = np.arange(n_samples) * dt_sec * 1e9

    return {
        "d0": {
            "time_ns": t_ns,
            "I": np.sin(np.linspace(0, 2 * np.pi, n_samples)),
            "Q": np.cos(np.linspace(0, 2 * np.pi, n_samples)) * 0.1,
            "phase_rad": np.zeros(n_samples),
        },
        "u(0,1)": {
            "time_ns": t_ns,
            "I": np.ones(n_samples) * 0.5,
            "Q": np.zeros(n_samples),
            "phase_rad": np.ones(n_samples) * (np.pi / 2),
        },
    }


def test_export_laboneq(sample_waveforms, tmp_path):
    """Test exporting to LabOne Q JSON format."""
    out_file = str(tmp_path / "test_laboneq.json")
    dt_sec = 0.222e-9

    export_laboneq(sample_waveforms, dt_sec, filename=out_file)

    assert os.path.exists(out_file)
    with open(out_file, encoding="utf-8") as f:
        data = json.load(f)

    assert "sampling_rate_hz" in data
    assert pytest.approx(data["sampling_rate_hz"]) == 1.0 / dt_sec
    assert "waveforms" in data
    assert "d0" in data["waveforms"]
    assert "u(0,1)" in data["waveforms"]
    assert data["waveforms"]["d0"]["length"] == 128
    assert len(data["waveforms"]["d0"]["samples"]) == 128
    assert len(data["waveforms"]["d0"]["samples"][0]) == 2  # [real, imag]


def test_export_rfsoc_qick(sample_waveforms, tmp_path):
    """Test exporting to RFSoC/QICK NPZ format."""
    out_file = str(tmp_path / "test_rfsoc.npz")
    dt_sec = 0.222e-9

    export_rfsoc_qick(sample_waveforms, dt_sec, filename=out_file)

    assert os.path.exists(out_file)
    loaded = np.load(out_file)

    assert "sampling_rate_hz" in loaded
    assert "d0_I" in loaded
    assert "d0_Q" in loaded
    assert "d0_length" in loaded
    assert loaded["d0_I"].dtype == np.int16
    assert loaded["d0_Q"].dtype == np.int16
    assert len(loaded["d0_I"]) == 128
    # Channel name sanitized
    assert "u_0_1_I" in loaded
    assert "u_0_1_Q" in loaded


def test_export_csv(sample_waveforms, tmp_path):
    """Test exporting to generic AWG CSV format."""
    prefix = str(tmp_path / "awg")
    dt_sec = 0.222e-9

    export_csv(sample_waveforms, dt_sec, prefix=prefix)

    d0_csv = str(tmp_path / "awg_d0.csv")
    cr_csv = str(tmp_path / "awg_u_0_1.csv")

    assert os.path.exists(d0_csv)
    assert os.path.exists(cr_csv)

    loaded_d0 = np.loadtxt(d0_csv, delimiter=",", skiprows=1)
    assert loaded_d0.shape == (128, 4)  # time_ns, I, Q, phase_rad


def test_hardware_export_end_to_end(simple_circuit, backend_2q, tmp_path):
    """Test end-to-end extraction from simulator and export to files."""
    sim = TargetWaveformSimulator(backend_2q.target).compile(simple_circuit)
    channels = sim.get_channels()

    waveforms = {}
    for ch in channels:
        snip = sim.get_snippet(ch, start_dt=0, length_dt=300)
        waveforms[ch] = {
            "time_ns": snip.time_ns,
            "I": snip.wave.real,
            "Q": snip.wave.imag,
            "phase_rad": snip.phase_rad,
        }

    labone_path = str(tmp_path / "e2e_labone.json")
    export_laboneq(waveforms, sim.dt, filename=labone_path)
    assert os.path.exists(labone_path)

    rfsoc_path = str(tmp_path / "e2e_rfsoc.npz")
    export_rfsoc_qick(waveforms, sim.dt, filename=rfsoc_path)
    assert os.path.exists(rfsoc_path)

    csv_prefix = str(tmp_path / "e2e_csv")
    export_csv(waveforms, sim.dt, prefix=csv_prefix)
    assert os.path.exists(f"{csv_prefix}_d0.csv")
