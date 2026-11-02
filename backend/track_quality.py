"""Reconcile historical processing evidence with available local source artifacts."""
import csv
import hashlib
import json
from .data import ROOT


def classify(message):
    if 'differ between' in message:
        return 'distance_anchor_conflict', 'Keep source distances reference-only; do not use for race alignment.'
    if 'layout year' in message:
        return 'historical_layout', 'Obtain current-layout compatibility evidence before enabling alignment.'
    if 'duplicate coordinate' in message:
        return 'duplicate_geometry', 'Preserve source; remove consecutive duplicates in display geometry only.'
    if 'Layout array' in message:
        return 'array_length_mismatch', 'Do not pair mismatched arrays by index; use independently valid percent sections.'
    if 'eventMap.json' in message:
        return 'missing_image_mapping', 'Keep unmapped graphic unavailable; do not substitute another circuit.'
    if 'No corner' in message or 'No valid geometry' in message:
        return 'missing_source_geometry', 'Supply original event session geometry; report alone cannot reconstruct it.'
    return 'source_warning', 'Retain warning pending source-level verification.'


def track_quality(event=None):
    path = ROOT / 'reports/process_tracks_report.json'
    if not path.exists():
        return {'available': False, 'warnings': [], 'candidates': [], 'reason': 'Processing report not installed'}
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    warnings = []
    for i, warning in enumerate(report.get('warnings', []), 1):
        if event and warning.get('event') != event:
            continue
        message = warning.get('warning', '')
        category, action = classify(message)
        warnings.append({'id': f'TRACK-{i:03d}', **warning, 'category': category,
                         'disposition': 'guarded_pending_source_evidence', 'action': action})
    candidates = []
    candidate_path = ROOT / 'reports/straight_mode_map_candidates.csv'
    if candidate_path.exists():
        with candidate_path.open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                if event and row.get('event_name') != event:
                    continue
                candidates.append({'annotation_id': row['annotation_id'], 'event': row['event_name'],
                                   'classification': row['annotation_class'],
                                   'verification': 'unverified_image_space_only', 'usable_in_model': False})
    return {'available': True, 'generated_at_utc': report.get('generated_at_utc'),
            'source_report_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'scope': event or 'all reported events', 'reported_summary': report.get('summary'),
            'report_input_root': report.get('input_root'),
            'local_checkout_reproduced': False,
            'warning': 'Historical report from another checkout. Its file references and selected session are not proof of local source availability. All image candidates remain unverified.',
            'warnings': warnings, 'candidates': candidates,
            'event_summaries': [e for e in report.get('events', []) if not event or e.get('event_name') == event],
            'excluded_events': report.get('excluded_events', []),
            'review_sheet_available': (ROOT / 'reports/straight_mode_map_review_sheet.png').exists()}
