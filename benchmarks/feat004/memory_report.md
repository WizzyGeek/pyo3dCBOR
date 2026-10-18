# FEAT004 native-memory probe

This report records process-level peak-RSS evidence for the direct encoder.
Each sample ran in a fresh CPython 3.14.7 process on Linux x86-64. The probe
used `resource.getrusage(RUSAGE_SELF).ru_maxrss` and `/proc/self/statm`; it
prepared and retained the Python input before taking the pre-encode baseline,
then called `dcbor.dumps()` once. Five child samples were collected for each
revision and workload. Raw sample values, fingerprints, RSS readings, output
hashes, and environment details are in [memory_raw.json](memory_raw.json).

The reported growth is the increase in the process high-water mark over the
pre-encode high-water mark. It includes extension/runtime behavior and is not
an exact native allocation count or an encoder-only byte attribution. RSS is
page-granular and can include allocator retention. These measurements support
bounded process-memory comparisons only; they do not establish a speedup or
cache behavior.

| Workload | Wire bytes | Baseline growth median (range) | Candidate growth median (range) | Median change | Output SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| 2 MiB bytes | 2,097,157 | 6,238,208 (6,234,112–6,242,304) | 4,194,304 (4,194,304–4,194,304) | −2,043,904 (−32.8%) | `7c9f27c8f6d68971cb3bd3690979c0d5e3e17660f29b934f79429dd55dd8ce9a` |
| 2 MiB ASCII text | 2,097,157 | 6,291,456 (6,291,456–6,291,456) | 4,194,304 (4,194,304–4,194,304) | −2,097,152 (−33.3%) | `9b3aba7a7b31b00c6db83c17d0da26d725793c6abfdd0ca773e3cdccde4b5557` |
| Nested graph, 2,048 maps | 258,151 | 4,063,232 (4,063,232–4,063,232) | 524,288 (524,288–524,288) | −3,538,944 (−87.1%) | `22aa02e2e464d169166d56f7ef9dc60c69aa6177a1232bd759c80fdff793f626` |
| Map with 128 Ki U+0344 key | 524,295 | 3,559,424 (3,538,944–3,670,016) | 2,555,904 (2,408,448–2,584,576) | −1,003,520 (−28.2%) | `4a5259175380ad227bd0ad59404e562d1ac5771d727db7be1d72bd003587155a` |

For every workload, all five baseline outputs and all five candidate outputs
had the same length and SHA-256. The baseline extension SHA-256 was
`44a625d54b2a44f0440aead0783a3a34447231e3d68d1ed4ceeebe01a663115c`; the
candidate extension SHA-256 was
`36502b893f69ae0c7bf8b159d53099b17c7ec02446c14b5d6a3555a6a278d581`.

The long U+0344 key exercises Unicode normalization of a long non-starter
sequence. Candidate RSS growth is lower for this bounded input, while its
2,555,904-byte median growth still shows material normalization scratch-memory
use. The normalization iterator is shared existing behavior; this sample does
not establish a bound for arbitrary key lengths.

Reproduce from the repository root with the same Python 3.14 environment and
the isolated old-wheel install:

```sh
python benchmarks/feat004/memory_native.py \
  --baseline-import-root /tmp/feat004-baseline/site \
  --candidate-import-root "$PWD/python" \
  --samples 5 --output /tmp/feat004-memory-paired.json
```
