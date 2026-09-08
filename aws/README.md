# AWS permissions reference

The application itself is AWS-only and uses an IAM role plus temporary STS credentials.

`CloudOpsAI-MonitoringPolicy.json` is a reference least-privilege policy covering the application features. If SNS or S3 are not being used, remove those statements from the role rather than granting unused access.

For SNS, use a topic name beginning with `CloudOpsAI-` and configure its ARN on the CloudOpsAI AWS Connection page. Email endpoints still require Amazon SNS confirmation.

For S3, use a bucket beginning with `cloudopsai-reports-` and configure the bucket name on the AWS Connection page.
