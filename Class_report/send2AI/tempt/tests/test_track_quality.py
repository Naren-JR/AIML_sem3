import json
import zipfile
import pytest
from backend.track_quality import track_quality
from backend.track_reference import load_reference
from scripts.reconcile_tracks import restore_assets


def test_all_report_warnings_are_accounted_for():
    report = track_quality()
    assert len(report['warnings']) == 103
    assert len(report['candidates']) == 49
    assert len({w['id'] for w in report['warnings']}) == 103
    assert all(w['action'] and w['disposition']=='guarded_pending_source_evidence' for w in report['warnings'])
    assert all(c['usable_in_model'] is False for c in report['candidates'])
    assert report['local_checkout_reproduced'] is False


def test_conflicting_distances_cannot_be_used_as_anchors():
    reference = load_reference()
    assert reference['source_version_conflict']
    assert reference['telemetry_aligned'] is False
    assert all(c['source_distance'] is None and c['reported_source_distance'] is not None for c in reference['corners'])
    assert len(reference['quality']['warnings']) == 5
    assert len(reference['quality']['candidates']) == 6


def test_archive_restore_is_idempotent_and_preserves_changes(tmp_path):
    folder = tmp_path/'trackData/raw/images'
    folder.mkdir(parents=True)
    with zipfile.ZipFile(folder/'svg.zip','w') as z:
        z.writestr('svg/test.svg','<svg/>')
    assert len(restore_assets(tmp_path)) == 1
    assert len(restore_assets(tmp_path)) == 1
    target = folder/'svg/test.svg'
    target.write_text('edited')
    with pytest.raises(ValueError,match='differs'):
        restore_assets(tmp_path)
    assert target.read_text() == 'edited'


def test_archive_traversal_rejected(tmp_path):
    folder = tmp_path/'trackData/raw/images'
    folder.mkdir(parents=True)
    with zipfile.ZipFile(folder/'svg.zip','w') as z:
        z.writestr('../escape.svg','bad')
    with pytest.raises(ValueError,match='Unsafe'):
        restore_assets(tmp_path)
