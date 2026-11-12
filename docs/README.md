# Documentation

The shared authorization pipeline is the backbone of this project. Start with the [research site](index.html) and [architecture](architecture/system/overview.md).

## Use the pipeline

- [Reproduction and demo benchmark](guides/reproduce.md)
- [Machine setup](guides/setup.md), [actor profiles](guides/models.md), [CARC](guides/carc.md)
- [Experiments and permission learning](guides/experiments.md)
- [Application integration](guides/integration.md)

## Research

- [Authorization contract](architecture/authorization/contract.md) and [evaluation method](architecture/evaluation/method.md)
- [Current evidence](results/research-release/README.md): configuration comparisons, local-run catalog and source hashes
- [Our Hugging Face dataset](https://huggingface.co/datasets/siddharth-magesh/grids-laya-permission-v1): gated prompt–action pairs and provisional labels
- [Reference datasets and historical studies](../experiments/reference/README.md): reproducibility inputs, not headline results
- [Manuscript](../paper/manuscript.pdf)

## Contribute

[Contribution guide](../CONTRIBUTING.md) · [Retained test coverage](development/testing.md)

Development tracking is kept in `development/project_tracking.md`; historical implementation notes are in `archive/milestones/`. The separate `plugin/` work is maintained independently. Public results contain aggregate evidence, not raw private logs or model assets.
