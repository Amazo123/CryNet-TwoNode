# Chapter 4 — The signal contract: every constant and why it is that value

## What "frozen contract" means here

The model is trained in Python on a workstation and executed in C on a microcontroller. Those two
implementations must compute **the same function**, or the model on the chip is being fed something it
was never trained on and its accuracy is a fiction. "Frozen" means the entire path from microphone
sample to network input is written down once, with no free parameters, and both implementations are
tested against each other.

This is D-11, and it is the most important decision in the project after the architecture itself.

## The chain

```
int16 pcm[32000]                      2.000 s @ 16 kHz mono
  -> subtract mean                    DC removal (the INMP441 sits at ~+18000 counts)
  -> / 32768                          normalise to [-1, 1]
  -> zero-pad 256 front / 512 rear
  -> 81 frames, 512-pt symmetric Hann, hop 400
  -> |rfft|^2                         257 bins
  -> 64 Mel bands (librosa slaney, 20 Hz - 8 kHz)
  -> 10*log10(max(P, 1e-10))          floored at -80 dB
  -> per-window standardisation       (mean 0, std 1 over the whole plane)
  -> int8 quantise                    q = round(v/scale) + zero_point
```

## The constants

| Name | Value | Why |
|---|---|---|
| `SR` | 16000 | The INMP441's comfortable rate; every chosen corpus is already 16 kHz, so nothing is resampled. Nyquist 8 kHz covers a cry's fundamentals (300–600 Hz) and its first ten harmonics |
| `WIN_SEC` | 2.0 | Long enough to contain a full cry expiratory cycle and its pitch contour; short enough that the alert is not stale. A neonatal cry's expiratory phase is typically 0.5–1.5 s |
| `N_SAMPLES` | 32000 | 2.0 × 16000 |
| `N_FFT` | 512 | 32 ms at 16 kHz. Frequency resolution 31.25 Hz — fine enough to resolve cry harmonics, coarse enough that a frame is quasi-stationary |
| `HOP` | 400 | 25 ms, i.e. 112 samples (21.9 %) of overlap between consecutive 512-sample frames; gives exactly 81 frames with the chosen padding |
| `N_FRAMES` | 81 | (32000 + 256 + 512 − 512) / 400 + 1 = 81 |
| `CENTER_PAD` | 256 | N_FFT / 2 — reproduces librosa's `center=True` framing |
| `TAIL_PAD` | 512 | makes the frame count land exactly on 81 rather than 80 |
| `N_MELS` | 64 | Perceptual spacing; 64 bands over 20 Hz–8 kHz gives fine resolution where cry harmonics live and coarse resolution up top. 128 was the legacy value and doubles the input for no measured gain |
| `FMIN` / `FMAX` | 20 / 8000 | 20 Hz discards rumble; 8 kHz is Nyquist |
| Mel scale | **slaney** | librosa's default: linear below 1 kHz, logarithmic above. **HTK** (the legacy firmware's choice) is logarithmic throughout. They are *different filterbanks* — using HTK weights against a slaney-trained model is a silent accuracy disaster |
| Mel weights | **497 non-zero** | stored sparsely as offsets + starts + ends, so the C filterbank loop touches 497 multiply-accumulates per frame, not 64 × 257 = 16,448 |
| `LOG_EPS` | 1e-10 | floor inside the log, so a silent band gives −100 dB before the −80 dB clamp rather than −∞ |
| `DB_FLOOR` | −80 | clamps the dynamic range so silence does not dominate the standardisation |
| `CMVN` | True | per-window mean/variance removal — see below |
| `SILENCE_RMS_GATE` | 0.0015 | below this the window is declared silence and skipped entirely |
| `TARGET_RECALL` | 0.95 | the calibration target that picks the alarm threshold |
| `SEED` | 1337 | every RNG in the pipeline is seeded from this |

## Why each step is not optional

### DC removal, and why the sum is an integer

The INMP441's output sits at roughly **+18000 counts**, not zero. Without DC removal the spectrum has
an enormous zero-frequency component that leaks into every Mel band through the window's sidelobes.

The sum is accumulated in `int32_t`, and the comment in the source explains exactly why:

> A float32 accumulator loses the low bits badly at this magnitude: summing 32,000 samples of 18000
> in float32 gives 575,726,660 instead of 576,000,000, so the "mean" comes out 8.5 counts low and 8.5
> counts of DC survive. That is invisible in a normal signal but fatal for the DC-offset probe, where
> it leaves a constant residual that the per-window standardisation then blows up into a completely
> different feature vector.

`int32` holds the sum of 32,000 `int16` samples exactly (at most 1,048,576,000). It is also *faster*:
integer adds are native, while the double-precision alternative would be emulated in software on the
ESP32-S3.

This is a genuinely excellent defence answer. It is a case where the obvious implementation
(`float sum`) is wrong, the wrongness is invisible on real audio, and it was caught by a *synthetic
probe* designed to expose it.

### The padding, and why there is no padded buffer

Frame `f` covers padded samples `[f·400, f·400 + 512)`; padded sample `p` holds PCM sample
`p − 256`, with zeros outside the signal. The C code builds each frame **directly from the caller's
PCM** with that index arithmetic, rather than materialising a padded copy. The copy was 128 KB of
working set and bought nothing.

### The window function must be *symmetric* Hann

`numpy.hanning` / `scipy.signal.windows.hann(N, sym=True)` and the *periodic* Hann used by some FFT
libraries differ by one sample of phase. Over 81 frames that difference is small but systematic, and
it is exactly the kind of small systematic difference that costs a few percent of accuracy for no
visible reason. The contract names the symmetric one, and the C table is generated from it.

### The FFT

An iterative radix-2 FFT, N = 512, in place, with the twiddle factors computed by **recurrence**
(`cr, ci` rotated by `wr, wi` each butterfly) rather than by a lookup table or a `cosf` per bin. The
recurrence is kept *identical to the reference implementation* so the two agree bit-for-bit on the
same input — accumulated rounding in a twiddle recurrence is a real source of divergence between two
otherwise-correct FFTs.

### The Mel filterbank

librosa's **slaney** normalisation: each triangular filter is scaled by `2 / (f_hi − f_lo)`, so filters
have equal *area*, not equal peak. HTK normalisation does not do this. The weights are precomputed in
Python and emitted as three arrays — `CRYNET_MEL_OFFSET`, `CRYNET_MEL_START`, `CRYNET_MEL_END` — plus
the 497 non-zero `CRYNET_MEL_WEIGHTS`. The C loop is then:

```c
for (int m = 0; m < 64; m++) {
    float acc = 0.0f;
    const float *wts = &CRYNET_MEL_WEIGHTS[CRYNET_MEL_OFFSET[m]];
    for (int b = CRYNET_MEL_START[m]; b < CRYNET_MEL_END[m]; b++)
        acc += power[b] * wts[b - CRYNET_MEL_START[m]];
    mel[m] = acc;
}
```

### Log, floor, and why −80 dB

`10·log10(max(P, 1e-10))`, then clamped at −80 dB. The clamp matters because of the *next* step: a
band at −100 dB in an otherwise loud window would drag the window's standard deviation up and squash
everything else towards zero. The floor bounds the dynamic range the standardisation has to cope with.

### Per-window standardisation — the level-invariance guarantee

```c
mu = mean(mel_out[0 .. 81*64));
sd = sqrt(variance(...)) + 1e-6f;
mel_out[i] = (mel_out[i] - mu) / sd;
```

Note precisely: this is over the **whole 81 × 64 plane**, one mean and one standard deviation per
window — not per Mel band. The `+1e-6` guards the all-silence case, where the variance is zero.

This is what makes the model level-invariant, and it is a direct response to a measured property of
the data: ICD cries sit at RMS 0.006 and its negatives at 0.3–0.46. Without standardisation the
network can learn "quiet ⇒ cry" and score beautifully for entirely the wrong reason.

### Quantisation

```c
v = nearbyintf(mel[i] / CRYNET_IN_SCALE) + CRYNET_IN_ZP;
clamp to [-128, 127];
```

`nearbyintf` — round-half-to-even under the default rounding mode — matches the converter's own
quantisation, so the host parity test and the chip agree on ties as well as on everything else.

## The eight compile-time guards

Because the generated header `crynet_tables.h` may only be included in **one** translation unit
(file-scope `const` arrays have external linkage in C, so a second inclusion is a link error), the
firmware mirrors a few generated constants under its own names. That duplication is a drift hazard,
so it is fenced:

```c
_Static_assert(CRYNET_INPUT_SCALE       == CRYNET_IN_SCALE,      "input scale drift");
_Static_assert(CRYNET_INPUT_ZERO_POINT  == CRYNET_IN_ZP,         "input zero-point drift");
_Static_assert(CRYNET_OUTPUT_SCALE      == CRYNET_OUT_SCALE,     "output scale drift");
_Static_assert(CRYNET_OUTPUT_ZERO_POINT == CRYNET_OUT_ZP,        "output zero-point drift");
_Static_assert(CRYNET_SILENCE_RMS_GATE  == CRYNET_SILENCE_RMS,   "silence gate drift");
_Static_assert(CRYNET_N_SAMPLES == 32000, "sample count drift");
_Static_assert(CRYNET_N_FRAMES  == 81,    "frame count drift");
_Static_assert(CRYNET_N_MELS    == 64,    "mel band count drift");
```

**If a new set of Kaggle artefacts changes any of these values, the firmware fails to compile instead
of silently classifying with stale numbers.** That is the difference between a bug that ships and a
bug that cannot.

## Where the working set lives, and the 3× speed-up

The DSP context allocates only the spectrum scratch:

| Buffer | Size |
|---|---|
| power spectrum | 257 × 4 = 1,028 B |
| Mel band accumulator | 64 × 4 = 256 B |
| FFT working array | 512 × 8 = 4,096 B |
| **Total** | **≈ 5.4 KB** |

It lives in **internal SRAM, not PSRAM**, and the reason is measured: PSRAM on the ESP32-S3 is
external memory reached over SPI. The FFT's butterfly passes and the Mel filterbank's bin loop stream
through these buffers 81 times per window. Leaving them in PSRAM made the front end cost **135 ms**;
moving them to internal SRAM, which is plentiful once the 128 KB padded-signal copy is gone, brought
it to **41.7 ms**.

The general rule the project follows: **large and cold goes to PSRAM; small and hot stays internal.**
The tensor arena (262 KB, touched by the interpreter) and the framebuffer (153 KB, written once per
redraw) are PSRAM; the FFT scratch (5.4 KB, touched 81 times per window) is internal.

## How parity was proved

Two independent tests, both still runnable:

1. **`firmware/tools/gen_probe_refs.py`** regenerates `crynet_probe_refs.h` from the *notebook's own
   front end* — four probe windows with their expected 81 × 64 feature planes. The hub computes the
   same four at boot and compares. **Maximum absolute difference: 6.9 × 10⁻⁵.**
2. **`research/test_c_parity.py`** runs the C front end on the host against the Python one on the same
   PCM, so a divergence can be debugged on a workstation rather than on a board.

The probes are not random audio. They include a **DC-offset case** specifically designed to expose the
float-accumulator bug described above, and a near-silence case that exercises the `+1e-6` guard. A
parity test on ordinary audio would have passed with the bug present.