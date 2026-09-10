---
type: decision
title: Early Stopping with Validation Monitoring
category: Machine Learning & Model Training
status: active
created: 2026-08-28
source: ml-llm-production-systems (Hamle 7)
tags: [ml, training, regularization, overfitting, validation]
---

# Early Stopping Strategy

**Pattern:** Monitor validation metric during training; stop when no improvement to prevent overfitting.

## The Problem

Training loss decreases monotonically but validation loss increases after certain epoch:
- Epoch 50: train_loss=0.05, val_loss=0.25 ✓
- Epoch 60: train_loss=0.02, val_loss=0.30 ✗ (worsened)
- Model memorizing training data; generalization suffers
- No stopping mechanism → wastes compute + deploys poor model

## Solution: Early Stopping

```python
import tensorflow as tf
from tensorflow.keras.callbacks import EarlyStopping

# Monitor validation loss; stop if no improvement
early_stop = EarlyStopping(
  monitor='val_loss',           # Metric to watch
  patience=5,                   # Stop after 5 epochs with no improvement
  min_delta=0.001,              # Minimum change to qualify as improvement
  restore_best_weights=True,    # Revert to best epoch
  mode='min'                    # Stop when val_loss stops decreasing
)

model = tf.keras.Sequential([
  tf.keras.layers.Dense(128, activation='relu'),
  tf.keras.layers.Dropout(0.2),
  tf.keras.layers.Dense(1, activation='sigmoid')
])

model.compile(optimizer='adam', loss='binary_crossentropy')

# Training with early stopping
history = model.fit(
  X_train, y_train,
  epochs=100,  # Max epochs (will stop early)
  batch_size=32,
  validation_data=(X_val, y_val),
  callbacks=[early_stop],
  verbose=1
)

# Actual epochs: ~50 (stopped before 100 due to no improvement)
print(f"Training stopped at epoch {len(history.history['loss'])}")
```

## Tuning Patience & min_delta

```python
# Example training dynamics
# Epoch 1-10: val_loss improves quickly (0.5 → 0.25)
# Epoch 11-30: val_loss plateaus around 0.25
# Epoch 31-50: val_loss starts increasing (overfitting starts)

# Patience options:
# patience=1:  Stop immediately after first worse epoch (too aggressive)
# patience=5:  Stop after 5 plateaued epochs (reasonable)
# patience=10: Allow oscillation; catch consistent degradation

# min_delta options:
# min_delta=0:      Any improvement counts (too sensitive to noise)
# min_delta=0.001:  Require 0.1% improvement (reasonable)
# min_delta=0.01:   Require 1% improvement (strict; may stop too early)
```

## Different Metrics for Different Tasks

```python
# Classification
early_stop_f1 = EarlyStopping(
  monitor='val_f1',     # F1 score for imbalanced data
  patience=5,
  mode='max'            # Maximize F1 (not minimize loss)
)

# Regression
early_stop_mape = EarlyStopping(
  monitor='val_mean_absolute_percentage_error',
  patience=10,
  mode='min'
)

# Custom metric
def custom_metric(y_true, y_pred):
  return precision_at_recall(y_true, y_pred, recall=0.9)

# Monitor custom metric
early_stop_custom = EarlyStopping(
  monitor='val_custom_metric',
  patience=5,
  mode='max'
)
```

## Visualization: When to Stop

```python
import matplotlib.pyplot as plt

# Plot training vs validation loss
epochs = range(1, len(history.history['loss']) + 1)
plt.figure(figsize=(10, 6))
plt.plot(epochs, history.history['loss'], label='Training Loss')
plt.plot(epochs, history.history['val_loss'], label='Validation Loss')

# Mark best epoch (where early stop restored)
best_epoch = np.argmin(history.history['val_loss']) + 1
plt.axvline(best_epoch, color='green', linestyle='--', label=f'Best Epoch ({best_epoch})')

# Mark where early stopping would have triggered
patience = 5
if best_epoch + patience <= len(history.history['val_loss']):
  plt.axvline(best_epoch + patience, color='red', linestyle='--', label=f'Stop Point (epoch {best_epoch + patience})')

plt.xlabel('Epoch')
plt.ylabel('Loss')
plt.legend()
plt.show()
```

## Variations & Alternatives

**Patience-Based (Standard)**
- Simplest; works well
- Risk: Oscillating validation metric triggers false stop

**Delta-Based**
- Requires absolute improvement threshold
- More stable for noisy metrics

**Learning Rate Scheduling**
- Alternative: Reduce LR on validation plateau (not stop, adapt)
- Useful when patience alone doesn't help

```python
from tensorflow.keras.callbacks import ReduceLROnPlateau

reduce_lr = ReduceLROnPlateau(
  monitor='val_loss',
  factor=0.1,           # Multiply LR by 0.1
  patience=3,
  min_lr=1e-7
)

# Use both: reduce LR first, then early stop if still no improvement
model.fit(..., callbacks=[reduce_lr, early_stop])
```

## When to Use

✓ **Deep learning** (prone to overfitting)
✓ **Limited validation data** (need to monitor carefully)
✓ **Expensive computation** (stop wasted epochs)
✓ **Production models** (better generalization)

✗ **Hand-picked stopping point** (e.g., "train for exactly 100 epochs")

## Production Gotchas

**1. Validation Data Leakage**
- Hyperparameter tuning on validation set → overfitting to validation
- **Fix:** Use separate validation set (not test set); use separate test set for final evaluation

**2. Small Validation Set → Noisy Metric**
- Oscillating validation loss → false early stops
- **Fix:** Use larger validation set; smooth metric (moving average)

```python
# Smooth validation loss with moving average
window = 3
smoothed_val_loss = pd.Series(history.history['val_loss']).rolling(window).mean()
# Re-plot and check for trend
```

**3. Metric Mismatch**
- Stop on validation loss but care about precision
- Optimal for loss != optimal for precision
- **Fix:** Monitor metric you actually care about (F1, precision, AUC)

**4. Best Weights Not Restored**
- `restore_best_weights=False` (default in older TensorFlow)
- Model at final epoch trained past best epoch
- **Fix:** Always set `restore_best_weights=True`

---

**Bağlantılar:**
- [[hamle7-ml-003-stratified-kfold]] (proper validation set creation)
- [[hamle6-testing-001-test-pyramid]] (testing early stopping logic)
- [[hamle5-performance-004-benchmarking-methodology]] (measuring training efficiency)
