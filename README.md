# CloudOpsAI

CloudOpsAI is an AWS-only cloud operations command center for EC2 and CloudWatch visibility, explainable anomaly/optimization analysis, SNS notifications, reports, and operational scoring.

## Real AWS architecture

CloudOpsAI uses an IAM role and AWS STS temporary credentials for a connected AWS environment. It does not require users to paste long-lived AWS secret keys into the application.

The application stores the user's CloudOpsAI account separately from the AWS connection record. Each connection is associated with its CloudOpsAI user.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Open `http://127.0.0.1:5000`.

Set `CLOUDOPSAI_SECRET` in `.env` to a strong persistent random value. Never commit `.env` or AWS credentials.

## AWS connection

1. Create an IAM role in the AWS account to be monitored.
2. The role trust policy should allow only the identity running CloudOpsAI to call `sts:AssumeRole`.
3. Grant only the AWS permissions required by the features you enable.
4. Enter the role ARN and AWS region on **AWS Connection**.
5. CloudOpsAI verifies the role with STS and then uses temporary credentials for AWS API calls.

For EC2 and CloudWatch monitoring, the minimum policy in the application documentation is based on `ec2:DescribeInstances`, `ec2:DescribeInstanceStatus`, `ec2:DescribeTags`, `cloudwatch:GetMetricData`, `cloudwatch:GetMetricStatistics`, `cloudwatch:ListMetrics`, and `cloudwatch:DescribeAlarms`.

SNS email delivery requires an SNS topic and the corresponding SNS permissions on the monitoring role. New email subscriptions must be confirmed from the SNS confirmation message before delivery begins. A reference least-privilege policy is included in `aws/CloudOpsAI-MonitoringPolicy.json`.

S3 report upload requires an S3 bucket and the corresponding S3 write permission on the monitoring role.

## Security controls

- PBKDF2-SHA256 password hashing with per-password random salt.
- CSRF protection on state-changing requests.
- HTTP-only, SameSite session cookies.
- Optional Secure session cookies for HTTPS deployments.
- Login failure throttling/temporary lockout.
- Least-privilege AWS role design.
- STS temporary credentials rather than stored AWS secret keys.
- Per-user AWS connection records.
- Security response headers and a self-hosted frontend with no runtime CDN dependency.
- Input validation for email addresses and IAM role ARNs.

## Important deployment note

The included SQLite database is intended for local development, portfolio demonstrations, and small single-process deployments. A production multi-instance deployment should use a managed relational database and an appropriate secret/session strategy.

Cost figures in the current application are transparent presentation estimates, not AWS Cost Explorer billing data.
