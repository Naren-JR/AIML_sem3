import json
from backend.data import Dataset
from backend.ml_validation import run_validation

if __name__ == '__main__':
    result = run_validation(Dataset())
    print(json.dumps({'metrics': result['metrics'], 'baseline': result['baseline'], 'split': result['split']}, indent=2))
