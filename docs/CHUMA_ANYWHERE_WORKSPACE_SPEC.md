# CHUMA Anywhere Workspace
## Canonical architecture for device-independent work

Status: DESIGN BASELINE
Scope: CHUMA CONTROL / Personal Dev Cloud
Principle: IDENTITY FOLLOWS CHUMA, NOT THE DEVICE OR SERVER.

## 1. Goal

The owner must be able to continue the same work from a phone, Windows computer, laptop, or another authorized device without creating independent project copies.

The device is only a client. The authoritative project state lives in CHUMA Control and the server-side project workspace.

## 2. Canonical topology

```
PHONE ───────┐
WINDOWS ─────┤
LAPTOP ──────┤
OTHER DEVICE ┘
       │
       ▼
CHUMA CONTROL
       │
       ├── Owner Identity / Session
       ├── Workspace State
       ├── Project Registry
       ├── Task / Job State
       ├── Permissions
       └── Audit / Provenance
       │
       ▼
CHUMA AGENT
       │
       ▼
PRIMARY LINUX WORKSPACE
       │
       ├── SHUMA.SPACE
       ├── Film Combain
       └── Personal AI Companion
```

## 3. Single source of truth

Every project has a machine-readable state:

- project_id
- active_branch
- current_revision
- current_task
- task_status
- last_successful_stage
- next_action
- workspace_lock
- owner_id
- updated_at
- provenance
- last_verified_result

The client must never treat a local checkout as authoritative.

## 4. Resume-anywhere contract

A client request is reduced to:

```
AUTHENTICATE
→ LOAD WORKSPACE STATE
→ ACQUIRE PROJECT SESSION
→ SHOW CURRENT TASK
→ EXECUTE / DELEGATE
→ PERSIST RESULT
→ RELEASE SESSION
```

Example:

```
Phone: "Continue Film Combain"
       ↓
CHUMA CONTROL
       ↓
PROJECT_STATE(FILM_COMBAIN)
       ↓
"Current task: produce and verify final.mp4"
       ↓
CHUMA AGENT
       ↓
server execution
       ↓
PROJECT_STATE updated
       ↓
Phone receives result
```

Opening the same project on Windows reads the same state; it does not start a second independent workflow.

## 5. Device roles

### Phone
- command and status interface;
- voice/text input;
- artifact preview;
- approvals when physically required;
- emergency stop / safe mode.

### Windows / desktop
- full control surface;
- terminal-like operations through CHUMA Control;
- file/artifact inspection;
- logs and test results;
- optional local tooling.

### Linux server
- primary execution environment;
- workers;
- project files;
- databases/object storage;
- CI/CD and backups.

No device is the owner of project truth.

## 6. Session and concurrency

Only one active mutating project session is allowed per project.

Read-only clients may connect concurrently.

A mutating session receives a short-lived workspace lease:

```
PROJECT → LEASE → DEVICE SESSION → TASK → RESULT → RELEASE
```

If a device disappears, the lease expires automatically. Work already committed to the server remains valid.

This prevents phone + Windows from accidentally modifying the same project in parallel.

## 7. Security

Minimum security boundary:

- Owner Identity Core;
- MFA / trusted-device policy;
- short-lived sessions;
- server-side authorization;
- per-project permissions;
- audit trail;
- tool permission firewall;
- safe mode;
- rollback;
- no secrets stored in client workspace state.

Device identity is supplemental. CHUMA owner identity remains primary.

## 8. Offline behavior

A client may cache UI state for convenience, but cached state is explicitly marked stale.

Offline clients may prepare a command, but mutating execution waits for authenticated CHUMA Control connectivity.

No offline client is allowed to silently fork the authoritative project state.

## 9. Artifact model

Large artifacts remain server-side.

The client receives:

- status;
- metadata;
- preview;
- checksum;
- downloadable/exportable artifact reference.

This allows a phone to inspect a generated video, image, build, archive, or report without storing the whole project.

## 10. Recovery

Every significant operation records:

- operation id;
- project id;
- starting revision;
- resulting revision;
- actor/session;
- action;
- result;
- verification;
- timestamp;
- rollback reference where applicable.

The system must be able to answer:

"Where did this project stop, what changed, and what is safe to do next?"

## 11. Required CHUMA Control commands

Initial command contract:

```
workspace status
workspace open <project>
workspace resume <project>
workspace lock <project>
workspace release <project>
workspace stop <project>
workspace safe-mode
workspace history <project>
workspace artifact <id>
workspace verify <project>
```

These commands are control-plane operations. They do not expose raw infrastructure credentials.

## 12. Project isolation

Projects remain isolated:

- SHUMA.SPACE
- Film Combain
- Personal AI Companion

A shared control plane may orchestrate them, but one project must not silently modify another project's working state.

## 13. Server replacement

The primary server is replaceable.

Migration sequence:

```
NEW SERVER
→ INSTALL CHUMA CONTROL
→ RESTORE CONTROL STATE
→ RESTORE PROJECT STATE
→ VERIFY ARTIFACTS
→ VERIFY SERVICES
→ SWITCH EXECUTION TARGET
```

The user's working identity and project state follow CHUMA rather than the server.

## 14. Acceptance test

The Anywhere Workspace feature is accepted only when:

1. A project can be opened from one authorized device.
2. A task can be started and persisted.
3. The first device can disappear.
4. A second authorized device can resume the same task.
5. No duplicate mutating session is created.
6. The second device sees the same authoritative state.
7. The resulting artifact is traceable to the same project revision.
8. Rollback remains available.
9. Unauthorized devices cannot mutate project state.

## 15. Non-negotiable rule

The user should not have to remember:

- which computer was used;
- which server was used;
- where a project was checked out;
- which terminal was open.

The user asks CHUMA to continue the work.

CHUMA resolves the current authoritative state and execution location.
