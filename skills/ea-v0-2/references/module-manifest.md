# EA Child Skill Manifest

Use this reference when adding or validating a child skill.

Characterization manifest:

```yaml
ea_skill:
  id: ea.raman-analysis
  version: 0.2.0
  category: characterization.spectrum
  method: raman
  input_artifacts:
    - raw_spectrum
    - sample_context
    - project_context
  output_artifacts:
    - processed_result
    - figure_record
    - report_section
    - provenance_record
    - memory_candidate
  review_gates:
    - confirm_method
    - confirm_processing_parameters
    - confirm_interpretation_before_memory_write
  required_indices:
    - raw/index.yml
    - reports/index.yml
    - figures/index.yml
    - provenance/index.yml
```

Category contracts:

| Category prefix | Required outputs |
| --- | --- |
| `characterization.*` | `processed_result`, `figure_record`, `report_section`, `provenance_record`, `memory_candidate` |
| `literature.*` | `literature_status`, `reference_record`, `report_section`, `provenance_record` |
| `visualization.*` | `figure_record`, `report_section`, `provenance_record` |
| other | `report_section`, `provenance_record` |

Built-in v0.2 manifest catalogue lives in `skill-registry/builtins/` and is indexed by `skill-registry/index.yml`. Current built-ins cover Raman, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, thermal analysis, image analysis, local literature library, and scientific figure generation. Raman, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, thermal analysis, image-data, and scientific-figure style infrastructure have concrete initial workflows; local literature library and deeper specialized analysis entries remain contract boundaries where implementation services are still intentionally limited.

Reject or request edits when a skill writes into `raw/`, omits provenance, lacks review gates for interpretation, produces unindexed figures, cites literature without references, or requires external accounts without a user-confirmed setup path.

Use these commands for deterministic governance:

```bash
ea add-skills check /path/to/manifest.yml
ea add-skills dry-run /path/to/manifest.yml --workspace /path/to/ea-project --sample-output /path/to/sample-output.yml
ea add-skills register /path/to/manifest.yml --workspace /path/to/ea-project --sample-output /path/to/sample-output.yml --status active
```

`dry-run` and `register` do not execute external skill code. They validate the manifest and, when a sample output is supplied, check that declared outputs follow EA output rules. `register` only writes `skill-registry/index.yml` after dry-run passes.
