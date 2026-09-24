ware_ops_pipes
==============

What is it?
-----------
This repository contains the source code to reproduce the results presented in the paper
"Warehouse-Aware Design of Algorithmic Pipelines for Decision-Making in Warehouse Operations".

Together with `ware_ops_algos`_, ``ware_ops_pipes`` forms the meta-model framework **Context-Aware Synthesis
for Optimization Problems (CASOP)**.

.. _ware_ops_algos: https://github.com/kit-dsm/ware_ops_algos

CASOP enables:

1. **Semantic representation of warehouse systems**  (layout, orders, resources, storage)
2. **Context-specific algorithm selection** by matching algorithm requirements against warehouse features
3. **Automated pipeline synthesis** across decision stages (item assignment, batching, routing, scheduling)


Framework Overview
------------------

CASOP consists of four main components:

🏭 **Data Layer and Domain Objects** (``ware_ops_algos``)
   To deal with heterogenous data sources, warehouse information is organized into domain objects: Layout, Articles, Orders, Resources, and Storage.

🛠️ **Algorithm Repository** (``ware_ops_algos``)
   Modular implementations of algorithms for item assignment, batching, routing, and scheduling. Each algorithm is annotated with its requirements via algorithm cards.

⚙️ **Domain-Algorithm Mapping** (``ware_ops_algos``)
   Filtering mechanism that identifies applicable algorithms based on instance characteristics and algorithm requirements.

🔄 **Context-aware Pipelines** (``ware_ops_pipes``)
   Uses `CLS-Luigi`_ to automatically generate all feasible algorithm combinations as directed acyclic graphs.
.. _CLS-Luigi: https://github.com/cls-python/cls-luigi

.. figure:: docs/source/_static/3d4l_framework_v5.png
   :alt: CASOP Architecture
   :width: 100%
   :align: center

   Architecture of the CASOP framework.

Supported Problem Classes
-------------------------
- **SPRP** - Single Picker Routing Problem
- **OBRP** - Order Batching and Routing Problem
- **OBSRP** - Order Batching, Scheduling, and Routing Problem


Getting Started
---------------

Clone repositories
~~~~~~~~~~~~~~~~~~

First, clone both required repositories:

.. code-block:: bash

   cd Documents/projects
   git clone https://github.com/kit-dsm/ware_ops_algos.git
   git clone https://github.com/kit-dsm/ware_ops_pipes.git

Both repositories should be in the same parent directory for easy installation.

Create virtual environment
~~~~~~~~~~~~~~~~~~~~~~~~~~

Create and activate a virtual environment for ware_pipe:

.. code-block:: bash

   cd ware_ops_pipes
   python -m venv .venv
   source .venv/bin/activate  # On Linux/Mac
   # or
   .venv\Scripts\activate  # On Windows

Install dependencies
~~~~~~~~~~~~~~~~~~~~

With the ware_pipe virtual environment activated, install ware_ops_algos first:

.. code-block:: bash

   pip install -e ../ware_ops_algos

Then install ware_ops_pipes:

.. code-block:: bash

   pip install -e .

The ``-e`` flag installs both packages in editable mode, allowing you to make changes without reinstalling.


Running Experiments
-------------------

Experiment runners are in ``experiments/``. Their raw Luigi outputs are written
to ``experiments/output/``. Result loading and preparation are available as
``ware_ops_pipes.benchmark_results``; the dashboard's static files are in
``site/``.

**Running an experiment:**

.. code-block:: bash

   uv run python experiments/run_foodmart.py

**Evaluating results:**

Download ``benchmark-results.parquet`` from the ``benchmark-results`` GitHub
release for analysis. It contains one row per instance and pipeline version,
including instance characteristics and loader timing when recorded by the
benchmark. Older rows retain null values for fields that were not recorded.
Nested algorithm configuration values are JSON strings.

.. code-block:: bash

   gh release download benchmark-results --pattern benchmark-results.parquet

.. code-block:: python

   from pathlib import Path
   from ware_ops_pipes.benchmark_results import read_results

   results = read_results(Path("benchmark-results.parquet"))
   print(results.groupby("instance_set")["total_distance"].mean())

The package also exposes ``load_new_results``, ``merge_results`` and
``postprocess`` for analysis of local summaries. To rebuild the dashboard from
the downloaded release asset, run:

.. code-block:: bash

   uv run --extra eval python -m ware_ops_pipes.benchmark_results.cli build-site \
     --input benchmark-results.parquet --output site/data

Benchmark sampling and publication
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Automated runs use the checked-in cohort in
``experiments/benchmark_samples.json``. The first 20 entries of every set form
the fast cohort and are a strict subset of the 100-instance standard cohort.
The cohort covers filename factor levels and configuration families before
adding deterministic, hash-selected replicates. This avoids alphabetical
``first 100`` bias while keeping comparisons and Luigi cache placement stable
across algorithm revisions.

Regenerate the cohort only when the experiment design or instance inventory is
intentionally changed:

.. code-block:: bash

   uv run python experiments/benchmark_sampling.py \
     --output experiments/benchmark_samples.json

After committing and pushing the workflow and cohort, run a small publication
check first:

.. code-block:: bash

   gh workflow run run_bench_on_change.yml --ref main \
     -f instance_set=FoodmartDataTest \
     -f sample_size=20 \
     -f update_cache=true \
     -f deploy_site=true
   gh run watch

Then publish the standard production cohort:

.. code-block:: bash

   gh workflow run run_bench_on_change.yml --ref main \
     -f instance_set=all \
     -f sample_size=100 \
     -f update_cache=true \
     -f deploy_site=true
   gh run watch

The collector restores the previously published result dataframe before
merging new rows, so publishing one set does not remove results for other sets.
Cache assets are keyed by the cohort-file hash. After all selected shards
succeed, superseded assets are removed only for those completed sets, including
the corresponding assets from the legacy ``cache`` release. The rolling
``benchmark-results.parquet`` asset is replaced only after the result dataframe
and website data have both been built successfully. The first publication after
migration imports history from the earlier ``benchmark-results.tar.gz`` asset.

Citation
========

If you use ware_ops_pipes in your research, please cite:

.. code-block:: bibtex

   @misc{bischoff2026ware_ops_pipes,
    author = {Bischoff, Janik and Suba, Oezge Nur and Barlang, Maximilian and Kutabi, Hadi and Mohring, Uta and Dunke, Fabian and Meyer, Anne and Nickel, Stefan and Furmans, Kai},
    title = {ware_ops_pipes},
    year = {2026},
    publisher = {GitHub},
    journal = {GitHub Repository},
    howpublished = {\url{https://github.com/kit-dsm/ware_ops_pipes.git}},
}

Authors
-------

- Janik Bischoff (IMI, Karlsruhe Institute of Technology)
- Özge Nur Subas (IOR, Karlsruhe Institute of Technology)
- Maximilian Barlang (IFL, Karlsruhe Institute of Technology)
- Hadi Kutabi (IMI, Karlsruhe Institute of Technology)
- Uta Mohring (University of Zurich)
- Fabian Dunke (IMI, Karlsruhe Institute of Technology)
- Anne Meyer (IMI, Karlsruhe Institute of Technology)
- Stefan Nickel (IOR, Karlsruhe Institute of Technology)
- Kai Furmans (IFL, Karlsruhe Institute of Technology)
