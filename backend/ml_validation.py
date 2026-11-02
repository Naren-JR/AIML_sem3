"""Reproducible, temporally held-out operating-state classification; not ERS ground truth."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .data import ROOT

CLASSES = ['braking', 'coasting', 'partial_throttle', 'high_throttle']
FEATURES = ['speed_kmh', 'rpm', 'gear', 'causal_acceleration_mps2']
RESULT = ROOT / 'results/ml_validation.json'
SOURCES = [
    {'title': 'scikit-learn: classification metrics', 'url': 'https://scikit-learn.org/stable/modules/model_evaluation.html', 'comparison': 'Defines accuracy, precision, recall and F1. Macro averages weight classes equally; scores here are computed from this race, not copied from documentation.'},
    {'title': 'McLaren: 2026 energy management', 'url': 'https://www.mclaren.com/racing/formula-1/2026/answering-your-questions-about-f1-regulations/', 'comparison': 'Describes braking, part-throttle and full-throttle harvesting. Driver-input classes cannot establish actual electrical recovery.'},
    {'title': 'Formula 1: 2026 terminology', 'url': 'https://www.formula1.com/en/latest/article/explained-the-new-key-terms-for-formula-1s-new-for-2026-rules.3T5BU6TC9quGcIpGzoWkY0.', 'comparison': 'Recharge depends on engine maps and circuit allowance. No independent synchronized SoC/power reference is supplied by this article.'}
]


def target(recorded):
    brake, throttle = recorded.get('brake'), recorded.get('throttle')
    if brake not in (0, 1) or throttle is None or not 0 <= throttle <= 100:
        return None
    if brake == 1:
        return 0
    return 1 if throttle <= 5 else 2 if throttle < 95 else 3


def run_validation(dataset):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.dummy import DummyClassifier
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix
    import sklearn
    samples, x, y = [], [], []
    for s in dataset.samples:
        r = s['recorded']
        label = target(r)
        values = [r.get('speed'), r.get('rpm'), r.get('gear'), s['calculated']['acceleration_mps2']]
        if label is None or any(v is None or not np.isfinite(v) for v in values):
            continue
        samples.append(s); x.append(values); y.append(label)
    x, y = np.array(x), np.array(y)
    laps = sorted({s['lap'] for s in samples})
    if len(laps) < 10:
        raise ValueError('Need at least ten laps for a meaningful blocked holdout')
    cut = int(len(laps)*.7)
    train_laps, purge_laps, test_laps = laps[:cut], laps[cut:cut+1], laps[cut+1:]
    train = np.array([s['lap'] in train_laps for s in samples])
    test = np.array([s['lap'] in test_laps for s in samples])
    model = HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=15, learning_rate=.1,
                                           early_stopping=False, random_state=42)
    model.fit(x[train], y[train])
    predictions = model.predict(x[test])
    baseline = DummyClassifier(strategy='most_frequent').fit(x[train], y[train]).predict(x[test])
    def metrics(pred):
        report = classification_report(y[test], pred, labels=list(range(4)), target_names=CLASSES, output_dict=True, zero_division=0)
        return {'accuracy': float(accuracy_score(y[test], pred)), 'balanced_accuracy': float(balanced_accuracy_score(y[test], pred)),
                'macro_precision': report['macro avg']['precision'], 'macro_recall': report['macro avg']['recall'],
                'macro_f1': report['macro avg']['f1-score'], 'weighted_f1': report['weighted avg']['f1-score'],
                'per_class': {name: report[name] for name in CLASSES},
                'confusion_matrix': confusion_matrix(y[test], pred, labels=list(range(4))).tolist()}
    selected = [s for s, keep in zip(samples, test) if keep]
    result = {'task': 'Operating-state classification from contemporaneous telemetry, not future forecasting or ERS-state reconstruction',
              'label_definition': 'Brake=1: braking; otherwise throttle <=5%: coasting; 5–<95%: partial throttle; >=95%: high throttle. Labels are operational rules, not independently annotated ERS labels.',
              'classes': CLASSES, 'features': FEATURES, 'excluded_features': ['throttle', 'brake', 'distance', 'lap', 'estimated ERS outputs'],
              'split': {'train_laps': train_laps, 'purged_laps': purge_laps, 'test_laps': test_laps,
                        'train_samples': int(train.sum()), 'test_samples': int(test.sum()),
                        'excluded_or_purged_samples': len(dataset.samples)-int(train.sum())-int(test.sum())},
              'model': 'HistGradientBoostingClassifier', 'seed': 42, 'sklearn_version': sklearn.__version__,
              'dataset_sha256': dataset.sha256, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'metrics': metrics(predictions), 'baseline': metrics(baseline),
              'sources': SOURCES, 'source_review_date': '2026-11-02',
              'limitations': ['Single driver, circuit and session; no independent-session generalization established.',
                             'Later laps are held out with one entire lap purged; adjacent samples remain correlated, so no sample-independent confidence intervals are claimed.',
                             'No hyperparameter tuning on the test set. Undefined class metrics use zero and include support counts.',
                             'These scores do not validate estimated SoC, energy deployment, or real-world harvesting. No external numerical benchmark with equivalent task/data was found.'],
              'predictions': [{'sample_id': s['sample_id'], 'lap': s['lap'], 'distance_m': s['recorded']['distance'],
                               'observed_class': CLASSES[int(actual)], 'predicted_class': CLASSES[int(pred)]}
                              for s, actual, pred in zip(selected, y[test], predictions)]}
    RESULT.parent.mkdir(exist_ok=True)
    temp = RESULT.with_suffix('.tmp'); temp.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8'); temp.replace(RESULT)
    return result


def saved_validation(dataset):
    if not RESULT.exists():
        return {'status': 'not_run', 'sources': SOURCES}
    result = json.loads(RESULT.read_text(encoding='utf-8'))
    if result['dataset_sha256'] != dataset.sha256 or result['source_sha256'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        return {'status': 'stale', 'sources': SOURCES}
    return {'status': 'ready', 'result': result}
