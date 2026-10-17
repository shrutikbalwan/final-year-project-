# Demonstration and Industrial Deployment Boundary

**Project status:** academic development and demonstration platform. This document defines a separation boundary; it does not authorize an industrial deployment.

## Demonstration environment

Use this repository's supported setup for local development and supervised demonstrations only:

- Run the backend on loopback (`127.0.0.1`) with a dedicated local SQLite database and synthetic, clearly identified helmet/workplace records.
- Use mock/test footage or footage with documented permission. Keep video processing local and in memory unless a test explicitly requires an output file. Do not use identifiable worker footage in routine demonstrations.
- The demonstration uses a temporary local account and API-enforced role. It is not an organization identity provider or an industrial deployment credential.
- Keep AWS disabled. The cloud folder is a placeholder and architecture documents are proposals; no cloud identities, resources, or deployment path are configured.
- Use development workplace profiles only. Their rule thresholds are examples, not certified operating limits.
- Do not connect demonstration devices or camera feeds to production networks, alerting, or incident-management processes.

Keep demo data and configuration separate from any real operational system. Use separate database files, credentials, accounts, network segments, buckets/topics, and notification destinations if a future pilot is separately approved. Never copy production records, credentials, footage, or worker identity data into this demo workspace. Do not use demo users or example credentials in an industrial environment.

## Industrial use requires a separate project and approval

This codebase has not been engineered, assessed, or certified as an industrial safety system. The local API now enforces bearer authentication and roles, but it lacks production identity controls and persistence has no configured retention lifecycle; cloud infrastructure and IAM are not implemented; and model evaluation is limited and not representative of a target workplace. Rule thresholds are configurable development policy, and model detections can be missed or false.

Before any real industrial pilot, the responsible organization must conduct an independent hazard and privacy assessment and define applicable legal, regulatory, worker consultation, and site requirements. A separate deployment must at minimum provide:

1. Server-enforced identity, least-privilege roles, device authentication, TLS, credential rotation, network isolation, audit trails, and incident response.
2. Site-approved and independently validated sensor/rule limits, calibration and maintenance procedures, fail-safe handling, and documented human response procedures.
3. Representative, permissioned, site-specific validation for every sensor and vision/model feature, including missed detections and false alarms, under expected lighting, PPE variation, occlusion, connectivity loss, and device faults.
4. Explicit data minimization, worker notice/consultation, access control, retention/deletion, backup, encryption, and breach-handling policies.
5. Monitored, recoverable infrastructure with tested backup/restore, alerting, capacity and failure testing, change control, and rollback.
6. A qualified safety review demonstrating that this platform is supplemental and cannot replace required certified PPE, approved alarms, procedures, or competent human supervision.

Do not connect this academic demo to real worker monitoring or use its outputs to decide whether a workplace is safe. Unknown, stale, missing, invalid, or model-unavailable results must remain visibly uncertain and must never be presented as a clearance.

## Separation checklist for future work

Before a separately authorized pilot, document the boundary and owner for each item:

- [ ] Separate source/configuration release, environment, cloud account and network.
- [ ] Separate identities, secrets, device certificates and notification recipients.
- [ ] Separate storage, retention policy, backups and deletion verification.
- [ ] Approved data protection and worker consultation.
- [ ] Approved rules, validated calibration, model/data evaluation and human procedures.
- [ ] Security assessment, operational readiness review, monitoring and rollback plan.
- [ ] Written approval from site safety, security, privacy and project stakeholders.

This checklist is guidance for a future review; checking boxes does not itself certify the system.
