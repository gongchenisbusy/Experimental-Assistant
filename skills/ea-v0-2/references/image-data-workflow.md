# Image Data Workflow

Use this reference for SEM, TEM, optical microscopy, and other image-like characterization data.

Core rule:

- Do not treat automatic visual recognition as reliable by default.
- Preserve the raw image as a read-only raw import.
- Ask for or use a user-confirmed image description before saving an image-analysis result.
- Separate user description, EA observations, interpretation, confidence, scale bar, imaging conditions, uncertainty, and references.
- Generate a display copy outside `raw/` with the EA figure footer; never edit the raw image.
- Register the display copy in `figures/index.yml`, generate a Markdown report under `reports/`, and write provenance.

Recommended command shape:

```bash
ea image-data record /path/to/project \
  --metadata raw/sem/char-20260630-001/metadata.yml \
  --method sem \
  --description "User-confirmed description..." \
  --description-review-ref review-20260630-001 \
  --sample-ref sample-001 \
  --confidence low

ea image-data report /path/to/project \
  --metadata processed/sample-001/sem/res-project-sem-20260630-001/image_metadata.yml
```

Confidence guidance:

- `high`: multiple reliable cues and project context support the interpretation.
- `medium`: image features are plausible but need supporting data or better metadata.
- `low`: interpretation depends heavily on user description or uncertain visual cues.
- `insufficient`: record and preserve the data, but ask for more context before scientific conclusions.
