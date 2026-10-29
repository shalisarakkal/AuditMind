"""No deserialization occurs until checkpoint authenticity/context is proven."""
import pickle
from uuid import uuid4

import pytest

from app.core.config import settings
from app.services import import_staging as staging


def test_checkpoint_roundtrip_preserves_typed_state_and_rows():
    scan = uuid4()
    state = staging.ReadState("fingerprint", staging.Identifiers(20))
    state.warnings.add({"row": 3, "message": "Warning"})
    state.identifiers.hostnames.add("host")
    data = staging._seal(state, scan, "fingerprint", "state")
    assert staging._unseal(memoryview(data), scan, "fingerprint", "state") == state
    rows = [staging.StagedRow(2, None, [])]
    assert staging._unseal(staging._seal(rows, scan, "fingerprint", "chunk:1"), scan, "fingerprint", "chunk:1") == rows


@pytest.mark.parametrize("attack", ["unsigned", "truncated", "tag", "payload", "scan", "fingerprint", "slot", "key"])
def test_invalid_checkpoints_never_reach_pickle_loads(attack, monkeypatch):
    scan, fingerprint, slot = uuid4(), "fingerprint", "chunk:1"
    data = staging._seal([staging.StagedRow(2, None, [])], scan, fingerprint, slot)
    if attack == "unsigned":
        data = pickle.dumps({"legacy": True})
    elif attack == "truncated":
        data = data[:10]
    elif attack == "tag":
        data = data[:5] + bytes([data[5] ^ 1]) + data[6:]
    elif attack == "payload":
        data = data[:-1] + bytes([data[-1] ^ 1])
    elif attack == "scan":
        scan = uuid4()
    elif attack == "fingerprint":
        fingerprint = "different"
    elif attack == "slot":
        slot = "chunk:2"
    else:
        monkeypatch.setattr(settings, "SECRET_KEY", "synthetic-different-signing-key-" * 2)
    def forbidden(*args, **kwargs):
        raise AssertionError("Unauthenticated payload was deserialized")
    monkeypatch.setattr(staging.pickle, "loads", forbidden)
    with pytest.raises(staging.StagingIntegrityError, match="Unauthenticated"):
        staging._unseal(data, scan, fingerprint, slot)
