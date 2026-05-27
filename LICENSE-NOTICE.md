# License Notice — Mixed Licensing

This repository ships under two distinct licenses. **Please read this notice
before deploying anything based on this repo in production or redistributing
the Docker image.**

## 1. Source code in this repository — MIT

Everything tracked in this Git repository (the browser GUI, the MCP bridge
script, the benchmark notebooks and input generators, the Docker wrapper
files, the documentation) is covered by the standard **MIT License** in
[`LICENSE`](LICENSE).

You may freely:

- Use it commercially
- Modify it
- Distribute it
- Sublicense it
- Use it privately

…subject only to keeping the copyright and license notices intact.

## 2. ROM binary inside the Docker image — Simthetic Evaluation License

The compiled ROM shared library (`rom.so`) distributed inside the Docker
images `simthetic/my-rom:v1` and `simthetic/my-rom:v1-with-gui` is **not**
covered by the MIT license. It is licensed under the **Simthetic Evaluation
License**, which grants:

- **Free use for local evaluation, benchmarking, and reproduction of the
  results in this repository.**
- **Free use in non-commercial research and academic publications**, provided
  Simthetic is cited.

It does **not** grant:

- The right to deploy the ROM binary in any production system, commercial
  product, paid service, or revenue-generating workflow.
- The right to redistribute the ROM binary, repackage it into another
  Docker image, or extract it from the image for distribution.
- The right to reverse-engineer, decompile, or attempt to extract the
  trained model weights.

If you want any of the above, you need a **commercial license**. We're
friendly about this — most pilot evaluations start with a free conversation
about your use case.

## 3. How to tell what's covered by what

| Artifact | License |
|---|---|
| Anything in this Git repo | MIT (see `LICENSE`) |
| `simthetic/my-rom:v1` Docker image (entrypoint, runtime, GUI files) | MIT |
| `rom.so` inside either Docker image | **Simthetic Evaluation License** |
| ROM weights, scaling config, manifest inside either Docker image | **Simthetic Evaluation License** |

## 4. Contact for commercial licensing

**Email:** [contact@simthetic.io](mailto:contact@simthetic.io)

We typically respond within 24 hours on business days.
