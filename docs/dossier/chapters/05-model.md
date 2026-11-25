# Chapter 5 — The model: architecture, training, mining, calibration, quantisation

## The constraint that designed the network

The network must run on **TensorFlow Lite Micro** on an ESP32-S3, in a fixed tensor arena, in
about a tenth of a second. TFLM is not TensorFlow: it has a small, fixed set of kernels, no dynamic
shapes, no control flow, and no allocator that can grow at runtime.

So the model zoo was restricted, before any training, to ops that TFLM demonstrably implements:
`Conv2D`, `DepthwiseConv2D`, `BatchNormalization` (folded at conversion), `ReLU`, `MaxPool2D`,
`GlobalAveragePooling2D` (which becomes `MEAN`), `Dense` (which becomes `FULLY_CONNECTED`), `Softmax`.

**No attention. No RNN. No GRU.** The legacy system used a 6.15 MB FP32 attention+GRU network called
TinyCryNet. That is 45× larger than the deployed model and contains ops TFLM cannot execute at all.
The rebuild's network is 122,770 parameters and **137,384 bytes** as INT8.

And this is not taken on trust — the export cell enumerates the converted model's operators and
asserts every one has a TFLM kernel:

```python
TFLM_KERNELS = {"CONV_2D", "DEPTHWISE_CONV_2D", "AVERAGE_POOL_2D", "MAX_POOL_2D",
                "MEAN", "FULLY_CONNECTED", "SOFTMAX", "LOGISTIC", "RELU", "TANH",
                "RESHAPE", "PAD", "SQUEEZE", "LEAKY_RELU"}
ops_for_tflm = [o for o in model_ops if o != "DELEGATE"]   # XNNPACK is host-only
missing = [o for o in ops_for_tflm if o not in TFLM_KERNELS]
```

The deployed model's operator set is `CONV_2D, FULLY_CONNECTED, MAX_POOL_2D, MEAN, SOFTMAX`. Five
operators, all present. `DELEGATE` is filtered out because it appears only when the *host* interpreter
runs XNNPACK; TFLM has no delegate.

## The four candidates

Four architectures were defined, deliberately different in *shape* so that the comparison would be
informative rather than a hyperparameter sweep.

### `conv_cnn` — the one that won

```python
inp = Input(shape=(81, 64, 1))
for f in (16, 32, 64, 64, 96):
    x = Conv2D(f, 3, padding="same", use_bias=False)(x)
    x = BatchNormalization()(x)
    x = ReLU()(x)
    x = MaxPool2D((2, 2))(x)
x = GlobalAveragePooling2D()(x)
x = Dense(64, activation="relu")(x)
x = Dropout(0.3)(x)
out = Dense(2, activation="softmax", name="probs")(x)
```

**122,770 parameters.** A plain 2-D CNN over the log-Mel plane. Five conv blocks halve both axes each
time: 81 × 64 → 40 × 32 → 20 × 16 → 10 × 8 → 5 × 4 → 2 × 2. Global average pooling then collapses the
surviving 2 × 2 × 96 to a 96-vector, so the classifier head sees a *summary* of the whole two seconds
rather than a flattened snapshot of one corner of it.

`use_bias=False` before every BatchNorm is not a style choice: BN's own β already provides the bias,
so a preceding bias term is redundant parameters that quantisation then has to represent.

### `sep_cnn` — the smallest

```python
for f in (24, 48, 96, 128):
    x = DepthwiseConv2D(3, padding="same", use_bias=False)(x)
    x = BatchNormalization()(x); x = ReLU()(x)
    x = Conv2D(f, 1, use_bias=False)(x)          # pointwise
    x = BatchNormalization()(x); x = ReLU()(x)
    x = MaxPool2D((2, 2))(x)
```

**29,839 parameters** — 4.1× smaller. Depthwise-separable convolution factorises a 3 × 3 × C_in × C_out
kernel into a per-channel 3 × 3 and a 1 × 1 mix, which is the standard MobileNet trick. It is the
fastest on the ESP32 and the obvious choice if memory were the binding constraint. It was not.

### `temporal_cnn` — 1-D over time

```python
x = Conv2D(64, (5, 1), padding="same", use_bias=False)(x)   # time only
... MaxPool2D((2, 1))                                        # pool time, keep all 64 Mels
for f in (96, 128): Conv2D(f, (3, 1)) ... MaxPool2D((2, 1))
```

**65,154 parameters.** Treats Mel bins as channels and convolves only along time — the shape that wins
keyword-spotting tasks. It was a serious candidate, not a straw man.

### `bsc_cnn` — optional fourth

Four blocks (32, 64, 128, 128), a 96-unit head. Available via `CRYNET_KINDS` but not in the default
three.

## Training

| Setting | Value | Note |
|---|---|---|
| Optimiser | Adam, lr **1e-3** | |
| Loss | sparse categorical crossentropy | two classes, integer labels |
| Batch | **128** (64 in FAST mode) | |
| Epochs | **35** (3 in FAST) | `CRYNET_EPOCHS` overrides |
| LR schedule | `ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3, min_lr=1e-5)` | |
| Early stopping | `patience=5`, `restore_best_weights=True` | |
| Class weights | `len(y) / (2 · count_c)` for each class | balances the 13,330 / 15,148 split |
| Selection | **highest validation AUC**, not accuracy | AUC is threshold-free; the threshold is chosen afterwards |
| Seed | 1337, `tf.keras.utils.set_random_seed` per variant | so the comparison is not a lottery |

Selecting on **AUC** rather than accuracy is deliberate. Accuracy at threshold 0.5 conflates the
model's ranking ability with an arbitrary cut point. The project needs the best *ranking*, and then
picks the cut point separately against a recall target. Those are two different jobs and they are done
in that order.

## Hard-example mining — the second round

After the first round, the model's own mistakes are the most valuable training signal available. A
cough it rates as a cry is exactly what turns a monitor into a nuisance; a cry it rates as noise is
exactly what a caregiver needs to hear about.

```python
p_train = score(X_train)                     # chunked, 4096 at a time
hard_neg = negatives sorted by -p_cry [:600] # the most cry-like non-cries
hard_pos = positives sorted by  p_cry [:600] # the least cry-like cries
ds_mine = sample_from_datasets([ds_train, ds_hard], weights=[1.0, 0.014])
model.compile(Adam(3e-4))                    # a third of the original rate
model.fit(ds_mine, epochs=6, EarlyStopping(patience=3, restore_best_weights=True))
```

Three details worth defending:

1. **Only training rows are mined.** The held-out folds are never scored for selection, so they stay
   honest. Mining on validation would be training on validation.
2. **The hard examples are mixed in by weighted sampling, not duplicated into a new matrix.** The old
   implementation duplicated each hard row, so 1.4 % of rows appeared twice; `weights=[1.0, 0.014]`
   reproduces that proportion exactly without allocating a second 900 MB copy on a machine with no
   page file.
3. **The learning rate drops to 3e-4.** Fine-tuning at the original 1e-3 on a set deliberately
   enriched in hard cases would overshoot and undo the first round.

This is the mechanism behind the README's `coughing` finding: ESC-50's coughing class produced a
**57 % false-positive rate** in the first false-alarm map, and hard-example mining is the tool that
class of failure is fed back into.

## Threshold calibration

The threshold is not 0.5 and it is not chosen by taste. It is swept:

```python
for t in np.arange(0.05, 0.96, 0.01):
    recall = (p_val[y_val == 1] >= t).mean()
    fpr    = (p_val[y_val == 0] >= t).mean()
ok = [t for t in rows if recall >= 0.95]
THRESHOLD = max(ok) if ok else 0.5
```

**The highest threshold that still reaches 95 % recall on the validation fold.** Highest, because
every increment above the recall floor is free specificity — false alarms removed at no cost in
missed cries. That single line is the whole alarm-policy philosophy of the project in miniature.

The sweep is printed every 0.05 so the recall/FPR trade-off is on the record, and the selected
threshold is then used for *every* subsequent number: test fold, cross-corpus, per-corpus breakdown,
per-subclass recall, and the deployed firmware.

## INT8 quantisation

```python
converter = TFLiteConverter.from_keras_model(BEST_MODEL)
converter.optimizations = [Optimize.DEFAULT]
converter.representative_dataset = representative_gen   # up to 512 seeded TRAIN windows
converter.target_spec.supported_ops = [OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type  = tf.int8
converter.inference_output_type = tf.int8
```

**Full-integer** quantisation, not the hybrid "weights INT8, activations float" default. That is
required for two reasons: ESP-NN's SIMD kernels are integer kernels, and a float activation path would
pull in the software floating-point reference kernels and blow the 100 ms budget.

The representative dataset is drawn from **training** windows with a fixed seed, one array per input
tensor with the exact `(1, 81, 64, 1)` shape — the converter is strict about both.

A float32 TFLite model is exported alongside, as the parity reference.

### The parity test, and the bug in its first version

```python
n_check = min(4000, len(X_val))
_sel = np.random.default_rng(SEED + 21).permutation(len(X_val))[:n_check]
```

The comment above that line is a small masterpiece of experimental hygiene:

> `X_val` is ordered by the ICD manifest, which lists every positive clip before every negative one,
> so the first `n_check` windows of the validation fold would be ALL cry (the fold's 2,665 positive
> clips alone contribute 5,330 windows). A prefix is therefore not a sample: on the full run it
> produced a single-class slice, whose AUC is undefined, and the parity numbers were reported as NaN.

The first version took a prefix. It reported `NaN`. The fix is a seeded random subset. **A test that
silently measures nothing is worse than no test**, and this one was caught.

**Measured parity: ΔAUC −0.00137, decision agreement 99.956 % over 11,386 windows.** Quantisation
costs essentially nothing.

## The deployed artefact

| Property | Value |
|---|---|
| File | `crynet_int8.tflite` |
| Size | **137,384 bytes** |
| SHA-256 | **`bd592d54…dce43b9`** |
| Parameters | 122,770 |
| Input | `int8[1, 81, 64, 1]` |
| Output | `int8[1, 2]` → dequantise → softmax → `[P(no_cry), P(cry)]` |
| Operators | `CONV_2D, FULLY_CONNECTED, MAX_POOL_2D, MEAN, SOFTMAX` |
| Arena | 262,144 B reserved, **108,328 B used**, in PSRAM |
| Latency | **101.8 ms** per window on the ESP32-S3 at 240 MHz with ESP-NN |

The artefact is embedded in the firmware as `crynet_model/include/model_data.h` — an 8,604-line
generated C array — so there is no filesystem, no OTA partition and no model-loading failure mode.
`firmware/tools/check_artifact_drift.py` verifies that `research/out/`, `deploy_config.json` and the
staged firmware copies all describe the same bytes. It currently reports **PASS** — and it is the
check that says which of two hashes in the project's prose is the live one.

## Results

| Split | AUC | What it means |
|---|---|---|
| ICD validation (fold 4) | **0.9994** | held-out fold of the primary corpus |
| ICD test (fold 5) | **0.9993** | never touched during selection |
| **Cross-corpus** | **0.9984** | unseen corpora, unseen babies: cry4 hold-out + ESC-50 + snoring + music hold-out + speech hold-out + all 40 ESC-50 `crying_baby` |
| INT8 vs float32, val | **0.9978 vs 0.9991** | the quantisation's own cost, measured inside the export |

The cross-corpus figure is the one to quote. The other two are consistent with it, which is the
useful observation: there is no large generalisation gap, so the model has learned crying rather than
the corpus.

### A trap worth walking into deliberately

These are the metrics of the **deployed** model — the one whose bytes are on the board. Its SHA-256
is `bd592d54…dce43b9`.

**The project's own prose quotes a different hash.** `DECISIONS.md` D-16 and `SYSTEM_UPDATE.md` both
cite `4aef55d8…126bc11`, and D-16 quotes test AUC **0.9995** and cross-corpus AUC **0.9973**.
Those are the numbers of the **previous** model — the one that was selected on 2026-10-29 and then
superseded by the music retrain of 2026-11-01 (D-58). The history is recoverable from the tree:

| | SHA-256 | val | test | cross |
|---|---|---|---|---|
| Pre-retrain (2026-10-29, D-16's selection) | `4aef55d8…126bc11` | 0.9994 | 0.9995 | 0.9973 |
| **Deployed (2026-11-01, D-58's retrain)** | **`bd592d54…dce43b9`** | **0.9994** | **0.9993** | **0.9984** |

The retrain *lowered* the in-domain test AUC by 0.0002 and *raised* the cross-corpus AUC by 0.0011.
That is the trade it was made for: the whole point was to stop alarming on loud music (8.19 % → 0.21 %),
and cross-corpus generalisation is what that buys. The pre-retrain model also recorded its INT8
parity as **`NaN`** — the comparison cell was broken on that run (I-1) — while the deployed model
records a real `int8_val_auc 0.9978` against `float_val_auc 0.9991`.

`firmware/tools/check_artifact_drift.py` settles which artifact is which, and it is the right thing to
run before quoting a hash:

```
OK  artifacts, firmware constants and deploy_config all agree
    model      : 137384 bytes  sha256 bd592d541027b9f4...
    threshold  : 0.95
    input quant: scale 0.116329655 zp -70
    staged     : 5 files identical to research/out/
```

A defence that quotes a hash must quote **that** one. The stale `4aef55d8…` in the decision log is
recorded as an open documentary item in Chapter 19.

### Against the deployed INT8 model, on real audio

| Test | Before the music retrain | After (deployed) |
|---|---|---|
| ESC-50 `crying_baby` recall | 36 / 40 | **36 / 40** (unchanged) |
| ESC-50 non-cry false alarms | 2.64 % (38 / 1,439) | **1.18 %** |
| **GTZAN music false alarms** | **8.19 %** (79 / 965) | **0.21 %** (2 / 965) |
| Quiet room, this INMP441 | 0 / 236 windows | **0 / 236** |
| Phone-played cry, per-window recall (session 1) | 0.867 | 0.800 |
| Phone-played cry, per-window recall (session 4) | 0.724 | 0.592 |

The last two rows are the honest cost of the retrain and they are not buried. Per-window recall fell;
**episode** recall did not, because a sustained cry trips many consecutive windows and the announce
rule needs only one unmistakable window or two agreeing ones.

## Why the legacy model was replaced

| | Legacy | Rebuild |
|---|---|---|
| Architecture | TinyCryNet, attention + GRU | 5-block plain CNN |
| Size | **6.15 MB, FP32** | **137,384 B, INT8** |
| TFLM-runnable | No (attention, GRU) | Yes, five kernels, all asserted |
| Mel bands | 128, **HTK** | 64, **slaney** |
| Normalisation | none | per-window CMVN |
| Trigger RMS | **0.18** | **0.030**, adaptive down to 0.005 |

Every row of that table is a defect the rebuild fixed, and the trigger row is the one that mattered
most: at 0.18 a soft cry never reached any classifier at all.