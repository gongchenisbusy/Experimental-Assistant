# EA Child Skill Manifest

Use this reference when adding or validating a child skill.

Minimum manifest:

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

Reject or request edits when a skill writes into `raw/`, omits provenance, lacks review gates for interpretation, produces unindexed figures, cites literature without references, or requires external accounts without a user-confirmed setup path.
