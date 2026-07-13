<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/hero-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="./assets/hero-light.svg">
    <img src="./assets/hero-light.svg" width="100%" alt="Derishabl — making invisible system behavior measurable">
  </picture>
</div>

<br>

## `01 / FIELD NOTE`

Most systems announce hard failures. The interesting ones fail quietly: a corpus exists but is never exposed, a few hubs dominate retrieval, or a migration passes while coverage collapses.

I build compact, inspectable instruments for those cases — currently around **vector retrieval**, **RAG observability**, and **regression testing**.

> **Working principle:** measure → compare → make regressions fail loudly.

<details>
<summary><code>Коротко по-русски</code></summary>
<br>
Меня интересуют системы, которые выглядят исправными, но скрывают сбои внутри распределений. Я превращаю такие слепые зоны в измеримые сигналы — сейчас в области vector search, RAG и контроля регрессий.
</details>

<br>

## `02 / CURRENT SIGNAL`

<a href="https://github.com/derishabl/retrieval-fairness">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/project-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="./assets/project-light.svg">
    <img src="./assets/project-light.svg" width="100%" alt="retrieval-fairness — exposure audits for vector search and RAG">
  </picture>
</a>

**[retrieval-fairness](https://github.com/derishabl/retrieval-fairness)** is an early-stage, open-source exposure audit for vector search. It measures corpus coverage, dark matter, Gini concentration, hub capture, and retrieval regressions — then turns the result into a report or a CI gate.

<p align="center">
  <a href="https://github.com/derishabl/retrieval-fairness#quick-start"><code>quick start ↗</code></a>
  &nbsp;·&nbsp;
  <a href="https://github.com/derishabl/retrieval-fairness/blob/main/docs/case_study_nq.md"><code>case study ↗</code></a>
  &nbsp;·&nbsp;
  <a href="https://github.com/derishabl/retrieval-fairness/blob/main/docs/comparison.md"><code>research notes ↗</code></a>
</p>

<br>

## `03 / WORKING COORDINATES`

```text
signal/
├── retrieval       RAG · vector search · FAISS · Qdrant · pgvector
├── measurement     coverage · Gini · hub capture · qrels
├── verification    pytest · regression diffs · CI gates
└── systems         Python · C++ · CLI tooling
```

<details>
<summary><code>smaller experiments / archive</code></summary>
<br>

- **[Praktika](https://github.com/derishabl/Praktika)** — a C++ heap-sort study with a small Windows console interface.

</details>

<br>

---

<p align="center">
  <sub>NO DASHBOARDS ABOUT ME &nbsp;·&nbsp; I BUILD DASHBOARDS FOR THE SYSTEMS</sub>
</p>
