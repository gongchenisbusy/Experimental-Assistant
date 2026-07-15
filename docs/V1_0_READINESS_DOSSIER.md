# Experimental Assistant v1.0 Readiness Dossier

Current status: `ready for v1.0 promotion`; `v1_promotion_ready: true`.

The machine-readable dossier is [`V1_0_READINESS_DOSSIER.yml`](V1_0_READINESS_DOSSIER.yml). v0.9.9 freezes the intended v1.0 feature contract. Promotion requires current-candidate automated tests, public benchmarks, native CI, deterministic Mock integration, fresh simulated-agent journeys/scientific reviews, manual final-artifact inspection, supply-chain/package checks, and issue disposition with no unresolved blocker.

Real-user trials, external expert sign-off, live Zotero, and real publisher/institution logins are not promotion gates. The dossier never treats simulated or Mock evidence as those external activities.

The verified release candidate has 447 passing regression tests, three passing fresh simulated-agent review tracks with no unresolved P0/P1/P2 finding, a passing deterministic five-target Mock transaction, recorded manual artifact inspection, successful native public CI, byte-identical repeated builds, clean wheel/sdist installation, a 59-component SBOM with zero unallowlisted vulnerabilities, and a passing release-package checklist. This freezes the v1.0 feature contract. v0.9.9 publication and downloaded-asset replay remain release-delivery steps, not additional product-capability or external-participant gates.
