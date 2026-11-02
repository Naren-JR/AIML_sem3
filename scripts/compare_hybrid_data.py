"""Compare fixed model settings on the same Belgian holdout, then retain expanded fit."""
import json
from backend import hybrid


if __name__=='__main__':
    test='belgian-grand-prix'
    output=hybrid.OUT
    try:
        hybrid.OUT=output.with_name('hybrid_small_training.json')
        small=hybrid.run(['australian-grand-prix','austrian-grand-prix'],test)
    finally:
        hybrid.OUT=output
    expanded=hybrid.run([t['id'] for t in hybrid.catalog() if t['available'] and t['id']!=test],test)
    fields=['train_tracks','test_track','train_samples','test_samples','acceleration_metrics','speed_metrics','persistence_acceleration_baseline']
    comparison={'protocol':'Identical fixed hyperparameters; same Belgian holdout; no tuning on this comparison.',
                'small_training':{k:small[k] for k in fields},'expanded_training':{k:expanded[k] for k in fields}}
    output.with_name('hybrid_dataset_comparison.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8')
    print(json.dumps(comparison,indent=2))
