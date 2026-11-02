from backend.circuits import catalog, definition
from backend.track_reference import load_reference
import pytest


def test_local_catalog_availability_and_scope():
    rows=catalog()
    assert len(rows)==20 and len({r['id'] for r in rows})==20
    assert [r['id'] for r in rows if r['race_telemetry_available']]==['australian-grand-prix']
    assert all(r['participation_source'].startswith('https://www.formula1.com/') for r in rows)
    assert definition('japanese-grand-prix') is None
    assert definition('spanish-grand-prix') is None
    assert definition('barcelona-grand-prix') is not None
    for r in rows:
        ref=load_reference(r['id'])
        assert ref['telemetry_aligned'] is False
        assert len(ref['geometry'])<=r['geometry_points']
    with pytest.raises(ValueError):load_reference('../australian-grand-prix')
