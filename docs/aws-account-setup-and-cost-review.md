# AWS account setup and Task 6 cost review

**Review date:** 2026-10-16  
**Account status:** Not created. No credentials, payment details, or AWS identity are available in this workspace.  
**Resources:** None deployed.

## Account creation and security handoff

Create the account using your own email, phone number, legal/contact information, password, and payment method on the official [AWS Free Tier signup page](https://aws.amazon.com/free/). Do not send those details, passwords, MFA codes, payment details, access keys, or root credentials to this coding agent or commit them to the repository. AWS requires account verification details; the exact signup flow and accepted plans are controlled by AWS.

AWS's current Free Tier program says eligible new accounts receive $100 in credits and may earn up to another $100. During signup, choose between the Free and Paid account plans. The Free plan ends after six months or once credits are exhausted; at expiry the account closes unless upgraded. AWS says a valid payment method is required for signup verification. Eligibility and service availability vary by account and plan; check the Billing console after signup rather than assuming credits cover every service. Joining an AWS Organization can expire Free Tier credits, so do not add this student account to an Organization for this project without first reviewing that consequence.

After account signup, secure it before deploying:

1. Immediately enable root MFA with a passkey or hardware security key where available; keep root use for account-level tasks only.
2. Do not create root access keys. Keep root recovery email and phone secure and current.
3. Create a separate day-to-day administrator through IAM Identity Center, require MFA, and use temporary role sessions. Do not share the root password or create long-lived developer keys for this project.
4. Configure a monthly AWS Budget (suggested alert threshold USD $10, actual 50/80/100%, forecast 100%) and review Free Tier/credit balance. Budgets notify; they do not cap or stop usage, and billing data can be delayed.
5. Select a Region and review the change set and AWS Pricing Calculator estimate before deployment. Do not enter credentials in source files, chat, or screenshots.

AWS signup and authentication require your private contact, password, payment, and verification information. Complete those steps yourself in AWS; do not share signup secrets with this agent. I can continue once you have created the account and established secure local access.

## DynamoDB capacity evaluation

The proposed data model currently has three tables and four GSIs (Telemetry: one GSI; Helmets: one GSI; Incidents: two GSIs). A simple theoretical minimum of 1 RCU and 1 WCU on each base table and each GSI would total **7 RCUs and 7 WCUs**. This is below DynamoDB's documented allowance of 25 provisioned RCUs and 25 WCUs per Region/payer account when the allowance applies. It is a capacity illustration, not a recommended production setting or a guarantee of zero cost.

The minimum can throttle the intended workload: a standard WCU is one write per second for an item up to 1 KB; larger items consume multiple WCUs, transactions consume twice the units, and writes also consume capacity on affected GSIs. A telemetry payload may exceed 1 KB. Conditional/retried writes can consume capacity, and auto scaling above the available free allowance can incur charges. Storage, backup/PITR, log, IoT, Lambda, SQS, API, notification, transfer, tax, and other account charges remain separate.

For scale only, AWS's current US East (N. Virginia) example rates are $0.00065 per WCU-hour and $0.00013 per RCU-hour. Holding 7 WCUs plus 7 RCUs provisioned for a 30-day (720-hour) month would be about **$3.93/month before any applicable allowance or credits**: `(7 × 0.00065 + 7 × 0.00013) × 720`. This excludes storage and every other service, and assumes US East prices; another Region differs. The allowance would cover those capacity hours only if the account/Region/plan qualifies and all relevant table and index capacity is within its limits. It is not a total bill estimate or zero-cost guarantee.

| Mode | Billing behavior | Fit for this project |
|---|---|---|
| Provisioned | Charged per hour for capacity set on each table and index, even when unused; can be less expensive for steady, measured traffic. | Consider after device reporting rate, payload size, queries, and index projections are measured. Configure cautious min/max and alarms; avoid autoscaling without a cost ceiling. |
| On-demand | Charged per request unit consumed; does not require selecting capacity in advance. | Easier for irregular early testing and unknown spikes, but request, transaction, and index costs are still metered. No guarantee of being free. |

**Recommendation:** do not select a capacity mode yet. For an initial controlled pilot, compare (a) provisioned capacity with a chosen minimum/maximum and (b) on-demand using the same workload in AWS Pricing Calculator for the chosen Region. The 7/7 minimum scenario appears to fit under the stated provisioned allowance if eligible, but it is not enough evidence to choose it for the operational path. The project should start with synthetic tests and measured arrival rates. Consider switching modes only after observed usage supports the choice.

## Remaining estimate inputs

A useful estimate needs a Region; number of helmets; messages per helmet per hour and payload bytes; desired telemetry retention; reads/list requests per day; incident frequency; GSI projected item sizes; expected notification channel (email vs SMS and destination); and whether backups/PITR are required. SMS and cross-region use can materially change cost. These values are not known yet, so an all-in monthly total would be misleading.

## Official references checked

- [AWS Free Tier plan and current signup FAQ](https://aws.amazon.com/free/free-tier-faqs/)
- [DynamoDB pricing and provisioned/on-demand behavior](https://aws.amazon.com/dynamodb/pricing/)
- [DynamoDB capacity unit consumption](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/read-write-operations.html)
- [AWS root-user best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/root-user-best-practices.html)
- [AWS sign-in administrator security guidance](https://docs.aws.amazon.com/signin/latest/userguide/best-practices-admin.html)
- [AWS Budgets pricing](https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)
