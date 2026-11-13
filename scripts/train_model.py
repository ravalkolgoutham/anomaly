"""Train and evaluate XGBoost on the CodeXGLUE JSONL splits."""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.extract_features import FEATURE_NAMES, extract_ast_features


DATA_DIR = ROOT / "CodeXGLUE" / "Code-Code" / "Defect-detection" / "dataset"


def load_split(path: Path):
    rows, labels = [], []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            item = json.loads(line)
            rows.append(extract_ast_features(item["func"]))
            labels.append(int(item["target"]))
            if line_number % 5000 == 0:
                print(f"  parsed {line_number:,} rows from {path.name}", flush=True)
    return pd.DataFrame(rows, columns=FEATURE_NAMES), np.asarray(labels)


def main():
    print("Parsing train split...")
    X_train, y_train = load_split(DATA_DIR / "train.jsonl")
    print("Parsing validation split...")
    X_valid, y_valid = load_split(DATA_DIR / "valid.jsonl")

    candidates = []
    for depth in (2, 3, 4):
        for learning_rate in (0.03, 0.1):
            model = XGBClassifier(
                n_estimators=250,
                max_depth=depth,
                learning_rate=learning_rate,
                min_child_weight=3,
                subsample=0.9,
                colsample_bytree=1.0,
                reg_lambda=2.0,
                eval_metric="logloss",
                random_state=42,
                n_jobs=4,
            )
            model.fit(X_train, y_train)
            valid_probs = model.predict_proba(X_valid)[:, 1]
            auc = roc_auc_score(y_valid, valid_probs)
            acc = accuracy_score(y_valid, valid_probs >= 0.5)
            candidates.append((auc, acc, depth, learning_rate, model))
            print(f"validation depth={depth}, lr={learning_rate}: accuracy={acc:.4f}, ROC-AUC={auc:.4f}")

    best_auc, _, best_depth, best_lr, _ = max(candidates, key=lambda row: row[0])
    print(f"Selected using validation ROC-AUC={best_auc:.4f}: depth={best_depth}, learning_rate={best_lr}")

    X_fit = pd.concat([X_train, X_valid], ignore_index=True)
    y_fit = np.concatenate([y_train, y_valid])
    final_model = XGBClassifier(
        n_estimators=250,
        max_depth=best_depth,
        learning_rate=best_lr,
        min_child_weight=3,
        subsample=0.9,
        colsample_bytree=1.0,
        reg_lambda=2.0,
        eval_metric="logloss",
        random_state=42,
        n_jobs=4,
    )
    final_model.fit(X_fit, y_fit)

    print("Parsing test split for final evaluation...")
    X_test, y_test = load_split(DATA_DIR / "test.jsonl")
    test_probs = final_model.predict_proba(X_test)[:, 1]
    print(f"Test accuracy: {accuracy_score(y_test, test_probs >= 0.5):.4f}")
    print(f"Test ROC-AUC:  {roc_auc_score(y_test, test_probs):.4f}")

    out = ROOT / "models" / "xgboost_defect_model.pkl"
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_model, out)
    print(f"Saved model: {out}")


if __name__ == "__main__":
    main()
