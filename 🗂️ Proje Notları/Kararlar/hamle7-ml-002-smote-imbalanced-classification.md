---
type: decision
title: SMOTE for Imbalanced Classification
category: Machine Learning & Data Preparation
status: active
created: 2026-08-28
source: ml-llm-production-systems (Hamle 7)
tags: [ml, imbalanced-data, smote, class-imbalance, synthetic-data]
---

# SMOTE: Synthetic Minority Oversampling

**Pattern:** Generating synthetic minority class samples via k-NN interpolation for imbalanced datasets.

## The Problem

Class imbalance (99% negative, 1% positive) causes models to predict majority class always:
- Fraud detection: 0.1% fraud, 99.9% legitimate → model predicts "not fraud" always = 99.9% accuracy but useless
- Disease diagnosis: rare disease (1% prevalence) → model learns to ignore positives
- Naive solution (oversample minority) causes overfitting

## Solution: SMOTE (Synthetic Minority Oversampling Technique)

```python
from imblearn.over_sampling import SMOTE
import numpy as np

# Imbalanced dataset
X = np.array([[0, 0], [1, 1], [2, 2], [1, 0], [0, 1]])
y = np.array([0, 0, 0, 0, 1])  # Only one positive example

print(f"Class distribution before SMOTE: {np.bincount(y)}")
# [4, 1] → 4 negatives, 1 positive

# Apply SMOTE: Generate synthetic positives
smote = SMOTE(k_neighbors=3, sampling_strategy=0.5)
X_resampled, y_resampled = smote.fit_resample(X, y)

print(f"Class distribution after SMOTE: {np.bincount(y_resampled)}")
# [4, 2] → 4 negatives, 2 positives (one synthetic)
```

## How SMOTE Works

```
Positive examples (sparse):
  P1 [1, 1]
  P2 [2, 2]

SMOTE algorithm:
1. Find k-nearest neighbors of P1:
   Neighbors: [P2, other_pos_1, other_pos_2]

2. Randomly select one: P2

3. Interpolate: new_point = P1 + rand(0, 1) * (P2 - P1)
   = [1, 1] + 0.5 * ([2, 2] - [1, 1])
   = [1.5, 1.5]  ← Synthetic positive example

4. Repeat K times to generate K synthetic positives
```

## Production: Balanced Classification

```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from imblearn.pipeline import Pipeline as ImbPipeline

# ⚠️ Important: Apply SMOTE AFTER train-test split
# (to avoid data leakage)

from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(
  X, y, test_size=0.2, random_state=42, stratify=y
)

# Pipeline with SMOTE (only on train set)
pipeline = ImbPipeline([
  ('scaler', StandardScaler()),
  ('smote', SMOTE(sampling_strategy=0.5, k_neighbors=5)),
  ('classifier', LogisticRegression())
])

pipeline.fit(X_train, y_train)

# Evaluate on test set (no SMOTE; real distribution)
accuracy = pipeline.score(X_test, y_test)
print(f"Test accuracy: {accuracy:.3f}")
```

## When to Use

✓ **Severe imbalance** (ratio > 1:10 or 1:100)
✓ **Fraud detection** (0.1-1% fraud)
✓ **Medical diagnosis** (rare diseases, <5% prevalence)
✓ **Anomaly detection** (outliers << inliers)

✗ **Slight imbalance** (1:3 ratio; class_weight better)
✗ **High-dimensional sparse data** (k-NN breaks down; use other methods)

## Alternatives & Combinations

```python
# Option 1: Class weights (simpler, no synthetic data)
classifier = LogisticRegression(class_weight='balanced')

# Option 2: SMOTE + Tomek links (remove noisy borderline samples)
from imblearn.combine import SMOTETomek
smotetomek = SMOTETomek(sampling_strategy=0.5)

# Option 3: ADASYN (adaptive synthetic) - harder negatives weighted higher
from imblearn.over_sampling import ADASYN
adasyn = ADASYN(sampling_strategy=0.5, n_neighbors=5)
```

## Production Gotchas

**1. Overfitting Risk with SMOTE**
- Synthetic examples are interpolations (unrealistic edge cases)
- Model memorizes synthetic pattern
- **Fix:** Use with regularization (L1/L2); ensemble methods; validate on real test data

**2. Over-Generation Creates Noisy Synthetic Examples**
- SMOTE fills minority class space aggressively
- Can create unrealistic samples
- **Fix:** Use SMOTE with borderline detection (only oversample borderline instances)

```python
from imblearn.over_sampling import BorderlineSMOTE

smote = BorderlineSMOTE(kind='borderline-1', k_neighbors=5)
# Only generates synthetic samples near decision boundary
```

**3. Categorical Features Break k-NN**
- SMOTE uses Euclidean distance (only for numeric)
- **Fix:** Encode categoricals; use mixed-data k-NN or alternative methods

---

**Bağlantılar:**
- [[hamle7-ml-003-stratified-kfold]] (proper evaluation with imbalanced data)
- [[hamle6-testing-001-test-pyramid]] (testing data quality post-SMOTE)
- [[hamle5-performance-004-benchmarking-methodology]] (measuring SMOTE impact)
