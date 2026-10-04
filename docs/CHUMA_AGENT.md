# CHUMA Autonomous Server Agent

The agent is a provider-independent control layer for the CHUMA deployment.

## Responsibilities

- monitor CHUMA health;
- restart unhealthy services;
- keep operational state and logs;
- create pre-change snapshots;
- verify the service after changes;
- provide a rollback foundation.

## Safety model

The agent is intended to evolve into separate Main Agent, Security Agent and Watchdog roles. Automated actions must preserve owner control, safe mode and rollback.

## Provider independence

Selectel is only the current infrastructure adapter. The agent must not depend on Selectel-specific APIs.

## Next layers

1. automatic update acquisition;
2. backup rotation;
3. verified deploy;
4. automatic rollback;
5. SAFE/AUTO modes;
6. security monitoring;
7. multi-server orchestration.
