---
type: decision
title: Stratified K-Fold Cross-Validation
category: Machine Learning & Model Evaluation
status: active
created: 2026-08-28
source: ml-llm-production-systems (Hamle 7)
tags: [ml, validation, cross-validation, imbalanced-data, metrics]
---

# Stratified K-Fold Cross-Validation

**Pattern:** Partitioning data into k folds while preserving class distribution for stable evaluation.

## The Problem

Standard k-fold on imbalanced datasets creates inconsistent splits:
- Dataset: 95% negative, 5% positive
- Fold 1: 92% negative, 8% positive (lucky)
- Fold 2: 98% negative, 2% positive (unlucky)
- Model metrics vary wildly across folds; scores unreliable

## Solution: Stratified K-Fold

Ensures each fold has approximately same class distribution as full dataset:

```python
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.ensemble import RandomForestClassifier
import numpy as np

# Imbalanced dataset
X = np.random.randn(1000, 10)
y = np.array([0]*950 + [1]*50)  # 95% negative, 5% positive

# Stratified 5-fold
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

# Each fold preserves 95%-5% split
for fold_idx, (train_idx, test_idx) in enumerate(skf.split(X, y)):
  y_train = y[train_idx]
  y_test = y[test_idx]
  
  print(f"Fold {fold_idx}:")
  print(f"  Train: {(y_train == 0).sum()} neg, {(y_train == 1).sum()} pos")
  # Output: Train: 760 neg, 40 pos (same 95%-5% ratio)
  print(f"  Test:  {(y_test == 0).sum()} neg, {(y_test == 1).sum()} pos")
  # Output: Test:  190 neg, 10 pos (same ratio)

# Cross-validation with stratified folds
clf = RandomForestClassifier()
scores = cross_val_score(
  clf, X, y,
  cv=StratifiedKFold(n_splits=5),
  scoring='f1'  # F1 is better than accuracy for imbalanced
)

print(f"F1 scores per fold: {scores}")
print(f"Mean F1: {scores.mean():.3f} ± {scores.std():.3f}")
```

## When to Use

✓ **Imbalanced classification** (ratio > 1:10)
✓ **Small datasets** (<10k samples; need stable estimates)
✓ **Rare event prediction** (fraud, disease diagnosis)
✓ **Any supervised learning** (better to use stratified by default)

✗ **Balanced datasets** (standard k-fold is fine)
✗ **Time-series data** (use time-aware splitting, not shuffle)

## Metrics Matter with Imbalanced Data

```python
from sklearn.metrics import precision_recall_curve, f1_score, roc_auc_score

# ❌ Accuracy is misleading
# 95% negative dataset: predict all negatives → 95% accuracy but useless

# ✓ Use these metrics:
# - F1 score (harmonic mean of precision & recall)
# - Precision-Recall AUC (better than ROC for imbalanced)
# - Recall @ fixed precision (e.g., "catch 90% fraud at >99% precision")

for fold_idx, (train_idx, test_idx) in enumerate(skf.split(X, y)):
  X_train, X_test = X[train_idx], X[test_idx]
  y_train, y_test = y[train_idx], y[test_idx]
  
  clf.fit(X_train, y_train)
  y_pred = clf.predict(X_test)
  y_pred_proba = clf.predict_proba(X_test)[:, 1]
  
  print(f"Fold {fold_idx}:")
  print(f"  Accuracy: {(y_pred == y_test).mean():.3f}")
  print(f"  F1: {f1_score(y_test, y_pred):.3f}")
  print(f"  ROC-AUC: {roc_auc_score(y_test, y_pred_proba):.3f}")
```

## Multiclass Stratification

```python
from sklearn.model_selection import StratifiedKFold

# Multiclass dataset (3 classes)
y = np.array([0]*100 + [1]*30 + [2]*20)  # Imbalanced: 100-30-20

skf = StratifiedKFold(n_splits=5)

for train_idx, test_idx in skf.split(X, y):
  y_train = y[train_idx]
  
  # Check: all 3 classes present in each fold
  print(f"Train class distribution: {np.bincount(y_train)}")
  # Output: [80, 24, 16] (preserves 100:30:20 ratio)
```

## Production Gotchas

**1. Stratification Doesn't Handle All Complexities**
- Multilabel classification (sample has multiple labels)
- Hierarchical classes (class imbalance at different levels)
- **Fix:** Use custom stratification; check fold distributions manually

**2. Time-Series Data Shuffled ❌**
- Stratified k-fold shuffles data (breaks temporal order)
- Time series requires time-aware splitting
- **Fix:** Use TimeSeriesSplit instead

```python
from sklearn.model_selection import TimeSeriesSplit

# Correct for time series (no shuffle)
tscv = TimeSeriesSplit(n_splits=5)

for train_idx, test_idx in tscv.split(X):
  # Train: [0, 1, 2, ..., 800]
  # Test:  [801, 802, ..., 1000]
  # (No data leakage; test is after train temporally)
  pass
```

**3. Small Positive Class Can't Stratify**
- Only 2 positive examples; 5-fold → some fold has 0 positives
- **Fix:** Use fewer folds (2-3) or increase minority class size

---

**Bağlantılar:**
- [[hamle7-ml-002-smote-imbalanced]] (generating synthetic minority examples)
- [[hamle7-ml-004-early-stopping]] (using stratified folds for validation)
- [[hamle6-testing-001-test-pyramid]] (testing evaluation procedures)
