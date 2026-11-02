"""Compute temporal and directed cross-track comparisons for all installed races."""
from backend.races import available_races
from backend.ml_experiments import experiment

if __name__ == '__main__':
    tracks=[r['id'] for r in available_races()]
    for train in tracks:
        for test in tracks:
            mode='within_track' if train==test else 'cross_track'
            r=experiment(mode,train,test)['result']
            print(f"{mode}: {train} -> {test}: accuracy={r['metrics']['accuracy']:.4f}, macro-F1={r['metrics']['macro_f1']:.4f}",flush=True)
