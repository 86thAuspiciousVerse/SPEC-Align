# Minimal document dependency example

<!-- spec
id: REQ-OFFLINE
status: active
-->

Core operations must work offline.

<!-- /spec -->

<!-- spec
id: DEC-STORAGE
status: active
depends_on:
  - REQ-OFFLINE
-->

Use SQLite for local persistence.

<!-- /spec -->

