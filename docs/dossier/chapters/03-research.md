# Chapter 3 — The data research: what was chosen, what was rejected, and why

## The question the research had to answer

A cry detector is not a cry *recogniser*. The hard part is not recognising a cry — a cry is a loud,
voiced, harmonic-rich sound with a characteristic rising-falling pitch contour, and almost any
classifier can learn it. The hard part is **not alarming on everything else in a nursery**: an adult
voice, a television, a radio, a cat, a door, a cough, a snore, another baby in the next cot.

So the corpus was chosen backwards from the confusion set. The question was never "where do I get
baby cries" — it was "what does a nursery actually contain, and do I have training examples of every
one of those things".

## The primary corpus: ICD

**`hoyyu1/infant-cry-detection`** on Hugging Face. 28,478 clips, every one of them **16 kHz mono,
exactly 5.00 seconds**, shipped in five folds. That uniformity is not a convenience — it is the reason
this corpus was chosen over the alternatives. No resampling, no channel mixing, no length
normalisation, no per-clip decisions. The signal contract can be defined once and applied to every
clip identically.

| | Clips |
|---|---|
| **Positives (cry)** | **13,330** |
| EnesBabyCries | 5,026 |
| CryCeleb2023 | 4,552 |
| iFLYTEK | 3,752 |
| **Negatives (non-cry)** | **15,148** |
| VoxCeleb (adult speech) | 4,963 |
| DASEE (domestic noise) | 4,506 |
| Human non-speech (cough, laugh, sneeze…) | 2,076 |
| Cat meows | 1,953 |
| Silence | 1,650 |
| **Total** | **28,478** |

Three independent cry corpora means hundreds of different infants recorded through three different
chains. That matters: a model trained on one corpus of babies learns that corpus's microphone as much
as it learns crying. Three chains break that shortcut.

The negative mix is the confusion set, deliberately: speech (the commonest sound in a room with
adults), domestic noise (the room itself), human non-speech vocalisations (the sounds *closest* to a
cry — a cough or a laugh is voiced and harmonic too), cat meows (the classic false alarm of every
commercial baby monitor, and acoustically a near-twin of an infant cry), and silence (so the model
has an explicit "nothing here" class rather than an undefined region).

## The supplementary corpora

| Corpus | Clips | Role | Notes |
|---|---|---|---|
| **Baby Cry 4-class** | 4,871 | extra positives, different provenance | needs 3,103 / physical_pain 774 / scared 684 / burping 310. All four map to *cry*: the system is binary (D-1) |
| **ESC-50** | 1,960 negatives + **40 held out** | environmental negatives; the 40 `crying_baby` clips are the *only* cross-corpus real-cry test | ESC-50 contains **no music and no speech** — a fact that later mattered enormously |
| **Snoring** | 1,000 | a sleeping adult, the other thing in a nursery at 3 a.m. | |
| **GTZAN** (added later, D-51) | 1,000 | **music**, ten genres | added *because a measurement demanded it*, not by foresight |
| **Loud speech** | recorded in this room | in-domain hard negatives | captured on the actual INMP441 |

### The music story — the best argument in the project

This sequence is worth being able to tell in full, because it is the clearest demonstration that the
project measures rather than assumes.

1. The first false-alarm map over ESC-50 (2026-10-31) showed the model rejecting speech, household
   noise and human non-speech well — **1.6 %**.
2. But ESC-50 contains **no music at all**, and neither did any training corpus. So "the model tells a
   cry from music" was not merely unmeasured — it was **untrained**.
3. A nursery has a radio, a television and a phone playing something. Music is a first-class confusion
   class here, not an afterthought.
4. GTZAN was fetched (1,000 clips, ten genres) and `research/eval_music.py` ran the *deployed* INT8
   model over it. **79 of the 965 clips that reach the model alarmed — 8.19 %**, three times the rate
   for any other kind of sound.
5. The per-genre breakdown made the cause obvious: jazz **14.3 %**, blues **13.0 %**, pop **12.0 %**,
   disco **10.0 %**, rock **10.0 %**; reggae 2.0 %, classical 2.9 %, country 3.0 %, metal 4.0 %. A
   saxophone and a sung vowel are voiced, harmonic-rich sounds. In the log-Mel domain they *are*
   cries, as far as the features are concerned.
6. **A threshold change could not fix it.** The INT8 output saturates at P(cry) = 0.9961: **45 of
   those 81 music alarms and 34 of the 36 true cry detections carried exactly the same value.** No
   threshold separates them. This is the single most important number in the whole evaluation, and it
   is the reason the answer was a training round rather than a config change.
7. GTZAN went into the training mix (D-51), split by clip so that 25 % of it is held out as *music the
   model has never heard*. The notebook was re-run on Kaggle, the model redeployed and re-verified
   4/4 on the board (D-58).
8. **Music false alarms: 8.19 % → 0.21 % (2 of 965).** ESC-50 non-cry alarms halved, 2.64 % → 1.18 %.
   ESC-50 crying-baby recall unchanged at 36/40. The quiet room still silent, 0/236.
9. **The cost was measured too, and it is real:** per-window recall on the phone-speaker cry sessions
   dropped — session 1 from 0.867 to 0.800, session 4 from 0.724 to 0.592. A sustained cry still trips
   many consecutive windows, so *episodes* are still caught; but the trade is stated, not hidden.

That is the whole loop: an unmeasured assumption, a measurement that broke it, a diagnosis that ruled
out the cheap fix, a data change, a re-measurement, and an honest account of what got worse.

## What was rejected, and on what evidence

Being able to say *why not* is worth more in a defence than being able to say why.

| Rejected | Reason |
|---|---|
| **`mennaahmed23/baby-cry*`** | **Contaminated.** Its "silence" class measures RMS **0.22** with a constant **1225 Hz** tone. That is not silence; it is a synthesised signal. Training on it teaches the model that a pure tone is silence — the exact opposite of what is needed. Found by measuring the audio, not by reading the dataset card |
| **`rahult25/five-class`** | Its classes are **pitch-shifted derivatives** of the same source clips. Training and testing on it measures the model's ability to recognise a resampling artefact, not a cry. Inflated scores, zero transfer |
| **ICSD** | Gated access; not obtainable within the project's timeframe |
| **AxonData** | Paid |
| **Baby Chillanto** | Request-only, no guaranteed turnaround. A classic in the literature, but unusable on a deadline |
| **AudioSet / FSD50K** | Redundant with ESC-50 + DASEE for this confusion set, at ten times the download and processing cost. (One FSD50K speech archive was kept as a *single irreplaceable copy* — its GitHub release no longer carries the asset) |
| **Raw DonateACry** | 8 kHz, heavily skewed in age and duration. Upsampling 8 kHz to 16 kHz invents the top octave the model would then learn to rely on |

The pattern: **every rejection is a measurement or an access constraint, never a preference.** The
contaminated corpus was found by computing RMS and looking at the spectrum. The derivative corpus was
found by comparing waveforms. That is the standard the rest of the project holds to.

## The level asymmetry — a finding that changed the firmware

While assembling the corpus, one measurement stood out: **ICD cries have RMS ≈ 0.006; the negatives
have RMS 0.3–0.46.** The cries are, on average, *sixty times quieter* than the non-cries in the same
dataset. That is an artefact of how the corpora were normalised by their authors, and it is a trap:
a model trained on that data without level normalisation would learn "quiet ⇒ cry" and achieve
excellent validation numbers for entirely the wrong reason.

**Per-window CMVN makes the model level-invariant**, which is why it is in the frozen contract and
not an option. The mean and standard deviation of the whole 81 x 64 log-Mel plane are removed, per window, so
absolute level carries no information into the network.

The same finding exposed a real bug in the legacy firmware. The old hub fired an audio pull only at
**RMS ≥ 0.18**. Real cries in this data sit around 0.006. **A soft cry never reached any classifier at
all** — the system was not misclassifying quiet cries, it was never being asked about them. The
rebuild's trigger is 0.030 and, since D-63, adaptive down to 0.005. Rejecting false triggers is
exactly what the model was trained for; gating them out before the model was throwing away the
model's whole purpose.

## How the corpora are turned into training rows

A clip is 5.00 s; the contract's window is 2.00 s. Each clip therefore yields several windows, and
the labelling rule is **"any cry present"**: a window is positive if cry audio is present anywhere in
it. That is the right rule for an alarm — a caregiver needs to know a cry started, not that a
majority of the last two seconds was crying.

Three properties of the assembly are load-bearing:

1. **Splits are by clip, never by window.** `split_by_clip()` shuffles clip identifiers and holds out
   whole clips. Splitting by window would put two overlapping windows of the same clip in train and
   test, and the resulting score would be meaningless.
2. **Augmented views exist only in TRAIN.** They are generated from training clips after the split,
   so an augmented copy of a test clip can never leak into training.
3. **Byte-identical windows are de-duplicated** by MD5 over the float16 feature bytes, with the
   earlier part winning. Silence clips in particular produce many identical windows; without
   de-duplication the model would be trained on thousands of copies of the same zero frame.

### The split

| Split | Contents |
|---|---|
| **TRAIN** | ICD folds 1–3 (clean + augmented) + 70 % of cry4 + 75 % of ESC-50 non-cry + 75 % of Snoring + 75 % of the music + 75 % of the loud speech |
| **VAL** | ICD fold 4 |
| **TEST** | ICD fold 5 |
| **CROSS** | the held-out 30 % of cry4, 25 % of ESC-50, 25 % of Snoring, 25 % of the music, 25 % of the speech, **plus all 40 ESC-50 `crying_baby` clips** |

CROSS is the number to quote in a defence. It is *unseen corpora and unseen babies*, including real
crying-baby recordings the model has never been trained on in any form. VAL and TEST are honest
held-out folds of the primary corpus; CROSS is the honest estimate of what happens in a new room.

### Augmentation

Two stages, in two different domains, for two different reasons.

**Waveform domain** (`augment_window`, applied when building augmented views):

```python
y = x * 10 ** (uniform(-18.0, 6.0) / 20.0)     # random gain, -18..+6 dB
if peak > 0.98: y *= 0.98 / peak               # never clip
if random() < 0.35:                            # reverberation
    y = fftconvolve(y, random_RIR)[:N_SAMPLES]
if random() < 0.5:                             # real-noise mix
    snr_db = uniform(3.0, 25.0)
    a = sqrt(ps / (pn * 10 ** (snr_db / 10)))
    y = y + a * noise; renormalise if peak > 0.99
```

The gain range is wide (24 dB) on purpose: the microphone's sensitivity is fixed and the distance to
the infant is not. The noise is **real recorded noise**, not synthesised white noise, because the
thing the model must reject is a real room. The room impulse responses make the model tolerant of
different rooms and cot positions.

**Feature domain** — SpecAugment, applied per batch on the GPU:

```python
for _ in range(2):   # two frequency masks, width 1..8 Mel bins
for _ in range(2):   # two time masks, width 1..12 frames
```

Implemented in pure TensorFlow ops rather than `tf.py_function`, because a `py_function` erases the
static tensor shape and Keras can then not infer the batch shape. That is a small detail with a large
consequence, and it is the kind of thing a defence is made of.

### The memory constraint that shaped the code

The training machine has **16 GB of RAM and no page file**. An allocation that does not fit is a hard
failure, not a slowdown. The feature matrix is roughly 900 MB, and the first version of the split cell
built it by concatenating copies — four live copies at once — and died with an allocation error before
training ever started.

The rewrite is visible in the code and is worth knowing:

- one **preallocated** destination array, filled a chunk at a time (`fill_rows`, chunk = 2048);
- every source matrix released the moment it falls out of use;
- de-duplication done **per part** rather than over one giant concatenated array (`dedupe_parts`);
- features stored as **float16**, halving both the matrix and the hashing cost;
- a **bounded shuffle buffer of 8192** windows rather than a full-corpus shuffle — each buffered
  element is a whole 81 × 64 window, so a 32k buffer would hold ~340 MB on its own;
- hard examples **mixed in by weighted sampling** (`weights=[1.0, 0.014]`) rather than copied into a
  second matrix.

None of this changes what the model learns. All of it is the difference between a run that finishes
and a run that does not.

## Getting the data

The notebook downloads roughly **4.6 GB** of audio, resumable via `huggingface_hub`, into
`research/_cache/`. Kaggle is the training host because it provides a GPU and because the download is
fast there; the same notebook runs locally in `FAST` mode against a stub cache for pipeline
validation. Chapter 20 gives the exact commands.