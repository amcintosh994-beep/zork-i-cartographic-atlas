# Zork I cartographic atlas

## Release notes - v1.0

### Status
v1.0 establishes the first fully schema-validated, drift-resistant baseline of the Zork I room atlas.

All room files:

* Successfully normalize under schema authority
* Validate against JSON schema
* Pass pre-commit gate
* Exhibit zero structural drift under git diff

### Structural guarantees
* Title authority inversion enforced
* Canonical exit formatting enforced
* Mapping Notes object schema-compliant
* Internal IDs conform to ^Z1-R-\d{3}$
* No unknown sections permitted

### Compiler integrity
* No recursion errors
* No import errors
* Windows-compatible pre-commit execution
* Deterministc normalization pass

### Drift prevention policy
Post-v1.0:
* Structural changes require schema revision
* Schema revision requires version bump.
* Unknown keys trigger failure.
* The compiler must never silently absorb stuctural novelty.

### Scope of v1.0
* Complete Zork I room corpus (91 rooms)
* Canonical normalization pipeline
* Fully operational compiler gate

Future work (outside v1.0 scope):
* Zork II integration
* Cross-game ID namespace extension
* 3D reconstruction layer
* Visualization tooling