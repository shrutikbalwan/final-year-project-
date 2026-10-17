# Task 6 cloud architecture proposal

**Status:** Proposed; no AWS resources have been created. The local backend and synthetic test suite remain the source of verified behavior.

## Proposed message and API paths

```text
Helmet (unique X.509 certificate, MQTT/TLS)
  -> AWS IoT Core, topic helmets/{thing-name}/telemetry/v1
  -> IoT Rule (route the unchanged v1 JSON payload)
  -> encrypted SQS standard queue -> Lambda event source mapping
       -> validate contracts.v1.DeviceTelemetry
       -> run the shared rule-based SafetyEngine and IncidentWorkflow
       -> DynamoDB telemetry, helmet status, incidents
       -> SNS publish only for configured new/escalated incident conditions

Dashboard / operator
  -> API Gateway HTTP API (AWS_IAM authorization)
  -> FastAPI Lambda adapter (Mangum) -> same DynamoDB adapter

Lambda / IoT / API Gateway
  -> CloudWatch Logs, metrics, alarms, bounded log retention
```

SQS is the IoT Rule destination rather than a direct Lambda action so transient processing failures can be retried with a dead-letter queue. Lambda acknowledges a record only after validation and durable writes. Malformed payloads are rejected into the DLQ and logged with a request/message ID and validation category; raw telemetry and credentials are not copied into logs. Event IDs are idempotency keys so retries do not create repeated telemetry or incidents. Notifications are sent only after the incident write succeeds and only when a configured risk/escalation policy selects them.

## Device authentication and IAM

Each helmet receives its own AWS IoT X.509 certificate and private key during controlled provisioning. MQTT uses TLS mutual authentication. The IoT policy limits `iot:Connect` to that device's Thing/client identity and `iot:Publish` to its own telemetry topic. The policy grants no subscribe, receive, publish-to-other-device, or administrative actions. Certificate rotation/revocation is part of device maintenance; keys stay on the device and are never checked into this repository.

Separate execution roles are proposed for the ingestion Lambda, API Lambda, and IoT Rule. Ingestion can consume only its queue, write only the required DynamoDB tables, publish to the configured SNS topic, and write its CloudWatch log group. API Lambda can query/update the tables needed for API routes but cannot publish SNS. The IoT Rule role can only send to the ingestion queue. No long-lived AWS credentials are embedded in code or device firmware.

## DynamoDB layout and access patterns

Use three on-demand tables with point-in-time recovery disabled initially (backup cost/retention can be approved separately). Encrypt at rest with AWS-owned keys by default; avoid optional paid global tables and streams for the first iteration.

| Table | Keys and indexes | Main access pattern | Retention |
|---|---|---|---|
| Telemetry | PK `device_id`; SK `observed_at#event_id`; GSI `workplace_id` + `observed_at#device_id`; event-id idempotency item/condition | Recent history by helmet or workplace, duplicate detection | Configurable TTL (proposed 90 days), after report/export requirements are confirmed |
| Helmets | PK `device_id`; GSI `workplace_id` + `device_id` | Get current helmet status; list helmets for a workplace | Latest status retained while device is registered |
| Incidents | PK `incident_id`; GSI1 `workplace_id` + `updated_at#incident_id`; GSI2 `device_id` + `opened_at#incident_id`; dedupe key with conditional write | Get incident/history, list workplace/device incidents, merge active repeated triggers | No automatic TTL while unresolved; resolved retention requires policy decision |

The DynamoDB adapter will use `LastEvaluatedKey` cursors for cloud list routes; it will not emulate local offset pagination with full-table scans. Contract objects remain unchanged; cursor tokens are transport metadata. Conditional writes on event IDs and dedupe keys make SQS retries safe. Updating the helmet snapshot uses a timestamp condition so an old replay cannot replace newer status.

## Pricing and budget controls (checked 2026-10-16)

Pricing depends on AWS Region, message size/rate, storage, log volume, API calls, email/SMS destinations, taxes, and current account Free Tier/credit eligibility. New AWS customers are currently offered account plans with up to $200 in credits; the Free plan ends after six months or when credits are exhausted. Service pricing pages can also show service-specific usage allowances, but eligibility and interaction with the selected account plan must be confirmed in that account's Billing console. Do not add allowances together or treat them as a promise that the project will be free. See [aws-account-setup-and-cost-review.md](aws-account-setup-and-cost-review.md) for the provisioned-capacity comparison and security setup. Verify the selected account and region in AWS Pricing Calculator immediately before deployment.

Proposed guardrail: deploy a USD $10/month AWS Budget with actual-spend alerts at 50%, 80%, and 100%, plus a forecast alert at 100%, sent to an email address supplied at deployment. Budgets notifications can lag and do not cap or stop charges. AWS states basic budget monitoring is free for the first two budgets; SNS email notification and any usage beyond included allowances can incur costs. Keep CloudWatch log retention finite (14 days initially), set message-size/rate limits, and avoid SMS until separately costed and approved.

Primary pricing references:

- [AWS IoT Core pricing](https://aws.amazon.com/iot-core/pricing/)
- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/)
- [Amazon DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/)
- [Amazon API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/)
- [Amazon SNS pricing](https://aws.amazon.com/sns/pricing/)
- [AWS Budgets pricing](https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/)
- [CloudWatch Logs billing and cost](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/LogsBillingDetails.html)
- [AWS Free Tier FAQ and account plans](https://aws.amazon.com/free/free-tier-faqs/)

## Deployment and cleanup outline

Deployment would use AWS SAM/CloudFormation in a selected Region. Before the first deployment: create or select an AWS account, confirm account Free Tier/credit status, enter the notification email and a deployment region, review a generated change set and cost estimate, and approve resource creation. Deploy a budget and alert first, then queues/DLQ, tables, roles, functions, IoT rule/policy/topic rule, API, SNS topic, logs/alarms. Provision a test Thing/certificate only after the cloud resources are approved; send a synthetic test telemetry contract message and verify telemetry, helmet status, incident behavior, API reads, alarm/log behavior, duplicate handling, and DLQ handling. Real device activation stays off until certificate issuance and policy checks are validated.

Cleanup removes the stack, IoT certificates/Thing/policies, queue/DLQ, tables, API, SNS topic/subscriptions, log groups, and budget if created. Preserve or export telemetry/incidents before deleting tables. AWS billing and cost records may persist after resource deletion.

## Local validation before deployment

Use botocore Stubber or a local DynamoDB emulator to test adapter calls without an AWS account. Required cases include contract-valid message, invalid message, duplicate ID, conditional-write race, transient AWS error/retry, DLQ exhaustion, incident creation/merge/acknowledgement, cursor pagination, stale status replay, and SNS publish gating. Cloud deployment remains unverified until real synthetic test messages traverse the provisioned path.
