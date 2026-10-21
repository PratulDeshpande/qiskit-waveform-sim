"""
Pulse Envelope Annotations for Qiskit 2.0+.

Provides custom Annotation subclasses for attaching parametric pulse specifications
to BoxOp blocks, with full OpenQASM 3 and QPY serialization support.
"""

from __future__ import annotations

import ast
from typing import Any

from qiskit.circuit.annotation import Annotation, OpenQASM3Serializer


class PulseEnvelopeAnnotation(Annotation):
    """
    Custom Qiskit 2.x Annotation attaching parametric pulse specs to a BoxOp.

    This annotation can be attached to a `qc.box()` context to override the default
    pulse envelope for gates within that box. It implements OpenQASM3Serializer
    for round-trip serialization via `qiskit.qasm3.dumps()` and `qiskit.qpy.dump()`.

    Examples
    --------
    >>> from qiskit import QuantumCircuit
    >>> from qiskit_waveform_sim import PulseEnvelopeAnnotation
    >>>
    >>> qc = QuantumCircuit(1)
    >>> with qc.box(duration=160, unit="dt",
    ...             annotations=[PulseEnvelopeAnnotation(shape="drag", amp=0.55, beta=0.25)]):
    ...     qc.sx(0)

    **QPY Round-trip Example**
    >>> from qiskit import qpy
    >>> from qiskit_waveform_sim import PulseAnnotationSerializer
    >>> import io
    >>>
    >>> qc = QuantumCircuit(1)
    >>> with qc.box(duration=160, unit="dt",
    ...             annotations=[PulseEnvelopeAnnotation(shape="drag", amp=0.55, beta=0.25)]):
    ...     qc.sx(0)
    >>>
    >>> serializer = PulseAnnotationSerializer()
    >>> buf = io.BytesIO()
    >>> qpy.dump(qc, buf, annotation_factories={"pulse_sim.envelope": serializer.as_qpy()})
    >>> buf.seek(0)
    >>> loaded = qpy.load(buf, annotation_factories={"pulse_sim.envelope": serializer.as_qpy()})[0]
    """

    namespace = "pulse_sim.envelope"

    def __init__(
        self,
        shape: str = "drag",
        amp: float = 0.5,
        beta: float = 0.08,
        sigma_ratio: float = 0.25,
        risefall_dt: int = 16,
    ):
        """
        Initialize pulse envelope annotation.

        Parameters
        ----------
        shape : str
            Pulse shape: "drag" or "gaussian_square"
        amp : float
            Peak amplitude as a fraction of DAC full-scale, -1.0 to 1.0
            (negative values flip the drive phase by pi)
        beta : float
            DRAG leakage suppression parameter (for drag shape)
        sigma_ratio : float
            Gaussian sigma as ratio of pulse duration; must be > 0 for drag
            (ignored for gaussian_square)
        risefall_dt : int
            Rise/fall duration in dt, >= 0 (for gaussian_square shape)

        Raises
        ------
        ValueError
            If the shape is unsupported or a parameter is out of range.
        """
        if shape not in ("drag", "gaussian_square"):
            raise ValueError(
                f"Unsupported shape: {shape}. Use 'drag' or 'gaussian_square'"
            )
        if abs(amp) > 1.0:
            raise ValueError(
                f"amp must be within [-1.0, 1.0] (DAC full-scale), got {amp}"
            )
        if shape == "drag" and sigma_ratio <= 0:
            raise ValueError(
                f"sigma_ratio must be > 0 for a drag pulse, got {sigma_ratio}"
            )
        if risefall_dt < 0:
            raise ValueError(f"risefall_dt must be >= 0, got {risefall_dt}")

        self.shape = shape
        self.amp = float(amp)
        self.beta = float(beta)
        self.sigma_ratio = float(sigma_ratio)
        self.risefall_dt = int(risefall_dt)

    def __repr__(self) -> str:
        return (
            f"PulseEnvelopeAnnotation(shape={self.shape!r}, amp={self.amp}, "
            f"beta={self.beta}, sigma_ratio={self.sigma_ratio}, risefall_dt={self.risefall_dt})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PulseEnvelopeAnnotation):
            return False
        return (
            self.shape == other.shape
            and self.amp == other.amp
            and self.beta == other.beta
            and self.sigma_ratio == other.sigma_ratio
            and self.risefall_dt == other.risefall_dt
        )

    def __hash__(self) -> int:
        return hash(
            (self.shape, self.amp, self.beta, self.sigma_ratio, self.risefall_dt)
        )

    def to_dict(self) -> dict[str, Any]:
        """Plain-dictionary form of the parameters (inverse of ``from_dict``)."""
        return {
            "shape": self.shape,
            "amp": self.amp,
            "beta": self.beta,
            "sigma_ratio": self.sigma_ratio,
            "risefall_dt": self.risefall_dt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PulseEnvelopeAnnotation:
        """Build an annotation from ``to_dict()`` output."""
        return cls(**data)


class PulseAnnotationSerializer(OpenQASM3Serializer):
    """
    Serializes PulseEnvelopeAnnotation to/from OpenQASM 3 and QPY.

    OpenQASM 3 Export Format::

        @pulse_sim.envelope {'shape': 'drag', 'amp': 0.5, 'beta': 0.08, 'sigma_ratio': 0.25, 'risefall_dt': 16}
        box[160dt] {
            sx $0;
        }

    QPY Serialization::

        Uses the standard QPY annotation mechanism with namespace "pulse_sim.envelope"
        via the `as_qpy()` method. Example:

        >>> from qiskit import qpy
        >>> from qiskit_waveform_sim import PulseAnnotationSerializer
        >>> import io
        >>>
        >>> serializer = PulseAnnotationSerializer()
        >>> buf = io.BytesIO()
        >>> qpy.dump(qc, buf, annotation_factories={"pulse_sim.envelope": serializer.as_qpy()})
        >>> buf.seek(0)
        >>> loaded = qpy.load(buf, annotation_factories={"pulse_sim.envelope": serializer.as_qpy()})[0]
    """

    def dump(self, annotation: Annotation) -> str:
        """
        Serialize annotation to OpenQASM 3 pragma string.

        Returns NotImplemented if namespace doesn't match.
        """
        if annotation.namespace != "pulse_sim.envelope":
            return NotImplemented  # type: ignore

        if not isinstance(annotation, PulseEnvelopeAnnotation):
            return NotImplemented  # type: ignore

        payload = {
            "shape": annotation.shape,
            "amp": annotation.amp,
            "beta": annotation.beta,
            "sigma_ratio": annotation.sigma_ratio,
            "risefall_dt": annotation.risefall_dt,
        }
        return repr(payload)

    def load(self, namespace: str, payload: str) -> Annotation:
        """
        Deserialize annotation from OpenQASM 3 pragma string.

        Returns NotImplemented if namespace doesn't match.
        """
        if namespace != "pulse_sim.envelope":
            return NotImplemented  # type: ignore

        try:
            data = ast.literal_eval(payload)
            return PulseEnvelopeAnnotation(**data)
        except (ValueError, SyntaxError, TypeError) as e:
            raise ValueError(
                f"Failed to parse PulseEnvelopeAnnotation payload: {payload}"
            ) from e
