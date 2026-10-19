# Repository documentation and presentation

**Goal:** give the repository a stated purpose, a landing page that fits its job, and a
per-plugin reference that already exists inside the code but never reached a reader.
**Branch:** `main` (this is the repository's public face; the unmerged
`feat/nacelle-actuator-surface` branch keeps its own extra validation sections and is
reconciled at merge).
**Out of scope:** renaming plugins (deferred, S10) and any source or physics change.

## Specs

- **S1** — Request:
  > "hay una cosa que me gustaria de este repo y es mejorar su readme su documentacion y su
  > presentacion"
- **S2** — Purpose of the repository (must become explicit):
  > "la idea de este repositorio seria tener el andamiaje CFD para mi otro software de
  > aeroelasticidad https://github.com/efirvida/AeroElast aeroelast incorpora su propio
  > solver de fluido para turbinas basado en CCBLADE y este pretende tener todo el andamiaje
  > necesario para tener CFD sobre openfoam para Aeroelast"
- **S3** — Independence (architectural property, must be stated):
  > "de igual forma seria independiente de aeroelast ya que toda la comunicacion FSI se hace
  > a travez de precice, por lo que no es restrictivo de aeroelast"
- **S4** — The gap:
  > "Dicho esto la documentacion del repo ni su nombr e menciona nada de esto."
- **S5** — The other gap:
  > "incluye plugins que sustituyen comportamiento por defecto de OpenFOAM sin justificacion
  > de porque estos plugins y no por ejemplo usar el multibody motionsolver de OpenFOAM o el
  > adapter oficial de precice para OpenFOAM, o el turbineFoam oficial tambien. Todo eso
  > falta en la documentacion del repo"
- **S6** — Renames are future work:
  > "incluso tambien en algun momento creo que deberia cambiar algunos nombres de plugins."
- **S7** — Framing decided: the README opens as the CFD leg of AeroElast, with the link, and
  the preCICE independence is explained afterwards as an architectural property.
- **S8** — Rationale placement decided: the "why these plugins and not the alternatives"
  section carries the differences that are verifiable in the repository **and an explicit
  pending placeholder**; the author writes his reasons later. No reason is invented.
- **S9** — Structure decided: the root README becomes an index (what / why / pieces /
  quickstart / links) and the deep detail moves to per-plugin READMEs, including the three
  plugins that have none today.
- **S10** — Scope of this work: documentation only. Plugin renames stay out, with their cost
  documented and published separately.

## Audit evidence (baseline, `main`)

| Finding | Evidence |
| --- | --- |
| The root README says `of-plugins`; the repository is `efirvida/openfoam-fsi-plugins` | `README.md:1`, `AGENTS.md:1` |
| No mention of AeroElast anywhere in the repository | `grep -ri aeroelast` → empty |
| No mention of the alternatives the plugins replace | `grep -riE 'solidBodyMotionFvMesh\|multibody\|dynamicOversetFvMesh\|openfoam-adapter' *.md` → empty |
| The root README performs 7 jobs (landing, contents, validation, FSI motion model, AMI reference, build, 3 usage snippets, fork rationale, licence) | `README.md`, 403 lines, no `docs/` directory |
| 3 of 5 plugins have no README | `solidBodyDisplacementLaplacianZone/`, `fsiOmega/`, `dynamicOversetZoneDisplacementFvMesh/` |
| The largest component has a 36-line README, and it is upstream's | `precice-openfoam-adapter/README.md` |
| The rationale already exists, buried in C++ class headers | `dynamicOversetZoneDisplacementFvMesh.H` (native `dynamicOversetFvMesh` pattern with a single motion solver instead of `dynamicMotionSolverListFvMesh`), `solidBodyDisplacementLaplacianZoneFvMotionSolver.H` (the `U_total = R(t)·(x+u_fsi) − x` model and the deform-then-rotate order), `fsiOmega/preciceOmega.H` (data flow) |
| The adapter fork's real divergence is not enumerated anywhere | `precice-openfoam-adapter/changelog-entries/*.md` are upstream PR entries (338…394), not fork deltas |

## Tasks

| ID | S# | Task | Route | Commit |
| --- | --- | --- | --- | --- |
| D1 | S9 | Write `solidBodyDisplacementLaplacianZone/README.md` (motion model, zone semantics, AMI protection, dict reference) | inline | `f0c4950` |
| D2 | S9 | Write `dynamicOversetZoneDisplacementFvMesh/README.md` (why it exists, overset usage, footer) | inline | `f0c4950` |
| D3 | S9 | Write `fsiOmega/README.md` (Function1 contract with the adapter, data flow) | inline | `f0c4950` |
| D4 | S4, S9 | Rewrite `precice-openfoam-adapter/README.md` as a fork README with a divergence section | inline | `6abfd2a` |
| D5 | S2, S3, S7 | Rewrite the root `README.md`: purpose, AeroElast framing, preCICE independence, pieces table, quickstart, doc map | inline | `6abfd2a` |
| D6 | S5, S8 | Add "Why these plugins and not the alternatives": verifiable capability differences plus the pending-rationale placeholder | inline | `6abfd2a` |
| D7 | S4 | Fix the stale repository name (`AGENTS.md`, `turbinesFoam/README.md` clone URL) | inline | `56d715e` |
| D8 | — | `CHANGELOG.md` entry for the documentation change | inline | `56d715e` |
| D9 | S6, S10 | Document the rename cost and the deprecation options; publish separately | inline | `72986a4`, [#4](https://github.com/efirvida/openfoam-fsi-plugins/issues/4) |

## Log

- **L1** (user, verbatim):
  > "hay una cosa que me gustaria de este repo y es mejorar su readme su documentacion y su
  > presentacion, incluso tambien en algun momento creo que deberia cambiar algunos nombres
  > de plugins.
  >
  > la idea de este repositorio seria tener el andamiaje CFD para mi otro software de
  > aeroelasticidad https://github.com/efirvida/AeroElast aeroelast incorpora su propio
  > solver de fluido para turbinas basado en CCBLADE y este pretende tener todo el andamiaje
  > necesario para tener CFD sobre openfoam para Aeroelast, pero de igual forma seria
  > independiente de aeroelast ya que toda la comunicacion FSI se hace a travez de precice,
  > por lo que no es restrictivo de aeroelast. Dicho esto la documentacion del repo ni su
  > nombr e menciona nada de esto.
  >
  > Por otra parte incluye plugins que sustituyen comportamiento por defecto de OpenFOAM sin
  > justificacion de porque estos plugins y no por ejemplo usar el multibody motionsolver de
  > OpenFOAM o el adapter oficial de precice para OpenFOAM, o el turbineFoam oficial
  > tambien. Todo eso falta en la documentacion del repo"
- **L2** (user, decisions): (1) framing = "es la pata CFD de AeroElast"; (2) rationale =
  evidence from the repository **and** leave the space for the author to propose his reasons
  later; (3) structure = README plus a README per plugin; (4) renames = documentation only
  now, renames later.
- **L3** (parent, evidence): the README audited first was the branch's. `main` carries the
  same document minus the ASM-MESH, nacelle, `geometry/` and rotational-augmentation content
  (`git diff main feat/nacelle-actuator-surface -- README.md` = +77/−11). The rewrite targets
  `main`; at merge, the branch's extra validation sections are re-added as links.

- **L4** (parent, delivery): D1–D8 landed on `main` in three work units — `f0c4950`  (the three missing per-plugin READMEs), `6abfd2a` (root README as a landing page plus the
  adapter fork README), `56d715e` (stale repository name in `AGENTS.md` and
  `turbinesFoam/README.md`, plus the `CHANGELOG.md` entry). Check run: all 35 relative
  Markdown links across the six touched documents resolve to existing files. No source file,
  case dictionary or plugin name was modified, and no physics changed. D9 (rename cost and
  deprecation options) stays deferred: plugin names are unchanged by design (S10).
- **L5** (parent, delivery): D9 landed as `72986a4`
  (`odd/tasks/plugin-rename.md`, the measured name contract and the T1/T2/T3 tiers) and was
  published as [#4](https://github.com/efirvida/openfoam-fsi-plugins/issues/4) through the
  `refactor.yml` issue form, verified by target-host read-back (title and body match, state
  `OPEN`, label `enhancement`). The form gained a `repository-wide` option before publication,
  because a rename spans all five plugins. No plugin name was changed.
