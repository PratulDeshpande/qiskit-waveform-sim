"""
Tests for PulseEnvelopeAnnotation and serialization.
"""

import ast

import pytest

from qiskit_waveform_sim.annotations import (
    PulseAnnotationSerializer,
    PulseEnvelopeAnnotation,
)


class TestPulseEnvelopeAnnotation:
    """Tests for PulseEnvelopeAnnotation."""

    def test_creation_defaults(self):
        """Test creation with default values."""
        ann = PulseEnvelopeAnnotation()

        assert ann.shape == "drag"
        assert ann.amp == 0.5
        assert ann.beta == 0.08
        assert ann.sigma_ratio == 0.25
        assert ann.risefall_dt == 16
        assert ann.namespace == "pulse_sim.envelope"

    def test_creation_custom(self):
        """Test creation with custom values."""
        ann = PulseEnvelopeAnnotation(
            shape="gaussian_square",
            amp=0.75,
            beta=0.15,
            sigma_ratio=0.3,
            risefall_dt=24,
        )

        assert ann.shape == "gaussian_square"
        assert ann.amp == 0.75
        assert ann.beta == 0.15
        assert ann.sigma_ratio == 0.3
        assert ann.risefall_dt == 24

    def test_invalid_shape(self):
        """Test that invalid shape raises error."""
        with pytest.raises(ValueError, match="Unsupported shape"):
            PulseEnvelopeAnnotation(shape="invalid_shape")

    def test_equality(self):
        """Test equality comparison."""
        ann1 = PulseEnvelopeAnnotation(amp=0.5, beta=0.1)
        ann2 = PulseEnvelopeAnnotation(amp=0.5, beta=0.1)
        ann3 = PulseEnvelopeAnnotation(amp=0.6, beta=0.1)

        assert ann1 == ann2
        assert ann1 != ann3
        assert ann1 != "not an annotation"

    def test_hash(self):
        """Test that annotation is hashable."""
        ann = PulseEnvelopeAnnotation(amp=0.5)
        d = {ann: "value"}
        assert d[ann] == "value"

    def test_repr(self):
        """Test string representation."""
        ann = PulseEnvelopeAnnotation(shape="drag", amp=0.55, beta=0.25)
        repr_str = repr(ann)

        assert "PulseEnvelopeAnnotation" in repr_str
        assert "drag" in repr_str
        assert "0.55" in repr_str
        assert "0.25" in repr_str

    def test_to_dict(self):
        """Test dictionary serialization."""
        ann = PulseEnvelopeAnnotation(
            shape="gaussian_square", amp=0.8, beta=0.1, sigma_ratio=0.2, risefall_dt=32
        )
        d = ann.to_dict()

        assert d == {
            "shape": "gaussian_square",
            "amp": 0.8,
            "beta": 0.1,
            "sigma_ratio": 0.2,
            "risefall_dt": 32,
        }

    def test_from_dict(self):
        """Test dictionary deserialization."""
        data = {
            "shape": "drag",
            "amp": 0.6,
            "beta": 0.12,
            "sigma_ratio": 0.22,
            "risefall_dt": 18,
        }
        ann = PulseEnvelopeAnnotation.from_dict(data)

        assert ann.shape == "drag"
        assert ann.amp == 0.6
        assert ann.beta == 0.12
        assert ann.sigma_ratio == 0.22
        assert ann.risefall_dt == 18


class TestPulseAnnotationSerializer:
    """Tests for PulseAnnotationSerializer (OpenQASM 3)."""

    def test_dump_valid(self):
        """Test serialization to OpenQASM 3 pragma."""
        serializer = PulseAnnotationSerializer()
        ann = PulseEnvelopeAnnotation(
            shape="drag", amp=0.5, beta=0.08, sigma_ratio=0.25, risefall_dt=16
        )

        result = serializer.dump(ann)

        # Should be a valid Python repr string
        assert isinstance(result, str)
        parsed = ast.literal_eval(result)
        assert parsed["shape"] == "drag"
        assert parsed["amp"] == 0.5
        assert parsed["beta"] == 0.08

    def test_dump_wrong_namespace(self):
        """Test that wrong namespace returns NotImplemented."""
        serializer = PulseAnnotationSerializer()

        class FakeAnnotation:
            namespace = "other.namespace"

        result = serializer.dump(FakeAnnotation())
        assert result is NotImplemented

    def test_load_valid(self):
        """Test deserialization from OpenQASM 3 pragma."""
        serializer = PulseAnnotationSerializer()
        payload = "{'shape': 'drag', 'amp': 0.55, 'beta': 0.2, 'sigma_ratio': 0.2, 'risefall_dt': 20}"

        ann = serializer.load("pulse_sim.envelope", payload)

        assert isinstance(ann, PulseEnvelopeAnnotation)
        assert ann.shape == "drag"
        assert ann.amp == 0.55
        assert ann.beta == 0.2
        assert ann.sigma_ratio == 0.2
        assert ann.risefall_dt == 20

    def test_load_wrong_namespace(self):
        """Test that wrong namespace returns NotImplemented."""
        serializer = PulseAnnotationSerializer()

        result = serializer.load("other.namespace", "{}")
        assert result is NotImplemented

    def test_load_invalid_payload(self):
        """Test that invalid payload raises ValueError."""
        serializer = PulseAnnotationSerializer()

        with pytest.raises(ValueError, match="Failed to parse"):
            serializer.load("pulse_sim.envelope", "not valid python")

    def test_roundtrip(self):
        """Test full round-trip serialization."""
        serializer = PulseAnnotationSerializer()
        original = PulseEnvelopeAnnotation(
            shape="gaussian_square", amp=0.7, beta=0.1, sigma_ratio=0.3, risefall_dt=24
        )

        # Dump to payload
        payload = serializer.dump(original)
        assert payload is not NotImplemented

        # Load back
        restored = serializer.load("pulse_sim.envelope", payload)

        assert restored == original


class TestAnnotationIntegration:
    """Integration tests with Qiskit BoxOp."""

    def test_attach_to_boxop(self):
        """Test attaching annotation to BoxOp."""
        from qiskit import QuantumCircuit
        from qiskit.circuit import BoxOp

        qc = QuantumCircuit(1)
        ann = PulseEnvelopeAnnotation(shape="drag", amp=0.6, beta=0.2)

        with qc.box(duration=160, unit="dt", annotations=[ann]):
            qc.sx(0)

        # Check that annotation is attached
        assert len(qc.data) == 1
        op = qc.data[0].operation
        assert isinstance(op, BoxOp)
        assert len(op.annotations) == 1
        assert op.annotations[0] == ann

    def test_multiple_annotations(self):
        """Test multiple annotations on same BoxOp."""
        from qiskit import QuantumCircuit

        qc = QuantumCircuit(1)
        ann1 = PulseEnvelopeAnnotation(shape="drag", amp=0.5)
        ann2 = PulseEnvelopeAnnotation(shape="drag", amp=0.6)  # Different amp

        with qc.box(duration=160, unit="dt", annotations=[ann1, ann2]):
            qc.sx(0)

        op = qc.data[0].operation
        assert len(op.annotations) == 2

    def test_qpy_roundtrip(self):
        """Test QPY serialization round-trip with annotations."""
        import io

        from qiskit import QuantumCircuit, qpy

        qc = QuantumCircuit(1)
        ann = PulseEnvelopeAnnotation(shape="drag", amp=0.55, beta=0.25)

        with qc.box(duration=160, unit="dt", annotations=[ann]):
            qc.sx(0)

        serializer = PulseAnnotationSerializer()
        buf = io.BytesIO()
        qpy.dump(
            qc, buf, annotation_factories={"pulse_sim.envelope": serializer.as_qpy()}
        )
        buf.seek(0)
        loaded = qpy.load(
            buf, annotation_factories={"pulse_sim.envelope": serializer.as_qpy()}
        )[0]

        # Check annotation survived
        for inst in loaded.data:
            op = inst.operation
            if hasattr(op, "annotations") and op.annotations:
                for a in op.annotations:
                    assert isinstance(a, PulseEnvelopeAnnotation)
                    assert a == ann
