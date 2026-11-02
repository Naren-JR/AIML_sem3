# Operating-state ML experiment (readings branch)

The ML validation tab measures contemporaneous operating-state classification on supplied Australian race telemetry. It is separate from the conditional ERS estimator and energy-allocation optimizer. No classification metric is assigned to true SoC, regeneration or deployment without independent electrical labels.

Labels are defined by recorded inputs: brake=1 means braking, otherwise throttle <=5% means coasting, 5–<95% means partial throttle, >=95% means high throttle. These operational thresholds are assumptions, not manually verified semantic ground truth. Missing or invalid inputs are excluded. Current speed, RPM, gear and causal speed-derived acceleration are features. Throttle, brake, lap ID, distance and all estimated ERS outputs are excluded. This is recognition at the current sample, not forecasting driver actions in advance.

HistGradientBoostingClassifier uses 100 iterations, 15 leaf nodes, learning rate 0.1, seed 42 and no internal early-stopping validation split. Whole laps are chronologically partitioned: first floor(70% of lap count) train, one entire lap purge, remaining laps test. For the supplied 58 laps this is 1–40 training, 41 purge, 42–58 testing. There is no random adjacent-sample split. Parameters are fixed before evaluation; no tuning on test results is performed. Same-session validation is weaker than held-out driver/circuit/session evaluation. No sample-independent confidence interval is claimed because telemetry samples are correlated.

The tab shows accuracy, balanced accuracy, macro precision/recall/F1, weighted F1, per-class support, a count confusion matrix and observed versus predicted held-out samples. Most-frequent training-class predictions provide a baseline evaluated on the same test samples. Undefined class metrics use zero with support shown. High operational-state scores do not imply successful inference of hidden battery energy.

Run `python -m scripts.validate_ml` using the virtual environment, or click Train & evaluate in the new tab. GET /api/ml/validation returns not_run, stale or ready. POST /api/ml/validation/run trains/evaluates and writes results/ml_validation.json. Dataset/source fingerprints invalidate stale saved results. Results include every held-out prediction and source links; they remain ignored by Git's privacy policy. The scikit-learn dependency is declared in requirements.txt.

## External comparisons and limitations

- https://scikit-learn.org/stable/modules/model_evaluation.html documents classification metrics and averaging. We use this for evaluation definitions, not as an external performance benchmark.
- https://www.mclaren.com/racing/formula-1/2026/answering-your-questions-about-f1-regulations/ describes recovery under braking, part throttle and super-clipping. Therefore observed driver inputs are not direct measurements of electrical flow.
- https://www.formula1.com/en/latest/article/explained-the-new-key-terms-for-formula-1s-new-for-2026-rules.3T5BU6TC9quGcIpGzoWkY0. describes map/circuit-dependent harvesting. It does not provide a synchronized electrical trace for validating this dataset.

Sources reviewed 2026-11-02. No directly equivalent external numerical benchmark was established; the UI does not compare this classifier's accuracy to unrelated studies or synthetic ERS results. The real recorded telemetry holdout and simple baseline provide the quantitative comparison. External articles provide qualitative real-world context only.
