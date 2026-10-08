"""
Pulse Envelope Annotations for Qiskit 2.0+.

Provides custom Annotation subclasses for attaching parametric pulse specifications
to BoxOp blocks, with full OpenQASM 3 and QPY serialization support.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

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
            Peak amplitude (normalized, 0.0-1.0)
        beta : float
            DRAG leakage suppression parameter (for drag shape)
        sigma_ratio : float
            Gaussian sigma as ratio of pulse duration (for drag shape)
        risefall_dt : int
            Rise/fall duration in dt (for gaussian_square shape)
        """
        if shape not in ("drag", "gaussian_square"):
            raise ValueError(
                f"Unsupported shape: {shape}. Use 'drag' or 'gaussian_square'"
            )

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
        """Serialize to dictionary for QPY."""
        return {
            "shape": self.shape,
            "amp": self.amp,
            "beta": self.beta,
            "sigma_ratio": self.sigma_ratio,
            "risefall_dt": self.risefall_dt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PulseEnvelopeAnnotation:
        """Deserialize from dictionary (QPY)."""
        return cls(**data)


class PulseAnnotationSerializer(OpenQASM3Serializer):
    """
    Serializes PulseEnvelopeAnnotation to/from OpenQASM 3 and QPY.

    OpenQASM 3 Export Format::

        @pulse_sim.drag(amp=0.5, beta=0.08, sigma_ratio=0.25, risefall_dt=16)
        box {
            sx q[0];
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


# Register the serializer with Qiskit's annotation system
# This happens automatically when the module is imported and qiskit.qasm3 is used
# with annotation_handlers={"pulse_sim.envelope": PulseAnnotationSerializer()}
