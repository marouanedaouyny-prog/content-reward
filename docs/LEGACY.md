# Legacy applications

Only Git-tracked files were relocated. Nothing was deleted. Ignored local
databases, `.env` files, browser sessions, credentials and media stay at their
original paths. The exact 92 moves are in [REFACTOR_PLAN.md](REFACTOR_PLAN.md).

`legacy/backend`, `frontend`, `scripts`, `workflows` and `n8n` form the old Empire
stack. `legacy/project` is a separate campaign/skills prototype.
`legacy/social-connector` is a separate OAuth/publishing experiment. None is
imported by the supported `clipping/` application. Old architecture documents,
PRDs and tests are retained alongside their code. Root requirements now install
the supported application; old pins are preserved in `legacy/requirements.txt`.

## Running historical code deliberately

These applications are archived, not validated for production. Do not use them
to publish. Never point their migrations at the clipping database. Their imports
retain `backend.*` and `scripts.*` and expect `legacy/` on the Python import path.
Their historical dependency set is separate and should use a separate venv.

Changing working directory changes relative DB, storage and dotenv paths. For
local historical inspection, stay in the repository root and set `PYTHONPATH`
to the absolute `legacy/` path, then invoke the old module. Explicitly set
`DATABASE_URL`, `STORAGE_DIR`, `LOG_DIR` and other required values to the original
absolute locations. Supply environment files locally; never copy them into Git.
The social connector uses its own original `legacy/social-connector/.env` and
its own encryption key. A root Instagram token does not establish its
authentication.

Historical containers have their data binds adjusted to original host locations;
the social connector compose invocation requires
`--env-file legacy/social-connector/.env` from the repository root (its former
root-level `social-connector/` folder was consolidated into `legacy/` alongside
its databases). These commands are documentary, not authorization to start
services, connect accounts or publish.
Read the legacy configuration before any manual startup.

## Retention/deletion criteria

Keep each archived stack until its useful rules/fixtures are ported, dependency
references are checked again, and an operator explicitly decides its local data
and credentials no longer need it. Legacy local data and credential files now
live at their relocated paths: `legacy/project/data/empire.db` and
`legacy/social-connector/` (`.env` plus `data/app.db`). No runtime dependency from clipping is known;
this does not prove outside scripts or user workflows have no dependency.
Archived tests are intentionally excluded from the supported `pytest` run.
Their original root-wide collection required SQLModel absent from the audited
global interpreter. Historical findings are not silently presented as passing.
