import json
import argparse
from backend.hybrid import run, TRACKS, DEFAULT_TEST, catalog

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Train on installed circuits and evaluate a wholly held-out circuit.')
    parser.add_argument('--test-track',choices=list(TRACKS),default=DEFAULT_TEST)
    parser.add_argument('--train-tracks',choices=list(TRACKS),nargs='+',help='Optional explicit subset; defaults to all other installed circuits.')
    args=parser.parse_args()
    training=args.train_tracks or [t['id'] for t in catalog() if t['available'] and t['id']!=args.test_track]
    result=run(training,args.test_track)
    print(json.dumps({k:result[k] for k in ['trained_quantity','train_tracks','test_track','train_samples','test_samples','acceleration_metrics','zero_acceleration_baseline','persistence_acceleration_baseline','speed_metrics','constant_speed_baseline']},indent=2))
