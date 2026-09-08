# CloudOpsAI 



### AWS Cloud Operations & Intelligence Platform



CloudOpsAI is an AWS-only cloud operations command center designed to provide a unified view of AWS infrastructure health, performance, operational risks, optimization opportunities, notifications, and reports.



It connects to a real AWS environment through an authorized IAM role and uses temporary AWS STS credentials to inspect infrastructure without requiring long-lived AWS secret keys inside the application.



---



##  What CloudOpsAI Does



CloudOpsAI brings several operational capabilities into one command center:



-  Real-time EC2 infrastructure visibility

-  CloudWatch CPU and network monitoring

-  Infrastructure health scoring

-  Operational readiness scoring

-  Explainable anomaly and optimization analysis

-  Cost and savings estimation

-  AWS SNS email notifications

-  Infrastructure health reports

-  S3 report storage

-  Secure AWS IAM + STS integration

-  User authentication and session security

-  Operational activity logging

-  Interactive EC2 resource details

-  Dark / light interface

-  Responsive professional dashboard



---



#  Application Screenshots



## Landing Page



![CloudOpsAI Landing Page](screenshots/01-landing.png)



## Secure Account Registration



![CloudOpsAI Registration](screenshots/02-register.png)



## AWS Connection



![AWS Connection](screenshots/03-aws-connection.png)



## Command Center Dashboard



![CloudOpsAI Dashboard](screenshots/04-dashboard.png)



## EC2 Infrastructure



![EC2 Instances](screenshots/05-ec2-instances.png)



## CloudWatch Monitoring



![CloudWatch Monitoring](screenshots/06-monitoring.png)



## AWS Notifications



![SNS Notifications](screenshots/07-notifications.png)



## Cost & Savings



![Cost and Savings](screenshots/08-cost-savings.png)



## AI Recommendations



![AI Recommendations](screenshots/09-ai-recommendations.png)



## Reports



![Infrastructure Reports](screenshots/10-reports.png)



## Activity Logs



![Activity Logs](screenshots/11-activity-logs.png)



## Generated Infrastructure Report



![Infrastructure Health Report](screenshots/12-report-preview.png)



---



# Architecture

```mermaid
flowchart TD
    A["CloudOpsAI - Flask Application"]
    B["IAM Role + STS<br/>Temporary Credentials"]

    C["Amazon EC2<br/>Resources"]
    D["Amazon CloudWatch<br/>Metrics & Alarms"]
    E["Amazon SNS<br/>Notifications"]

    F["CloudOpsAI Intelligence & Analysis"]

    G["Infrastructure<br/>Health Score"]
    H["Cost & Savings<br/>Analysis"]
    I["AI / Rule-Based<br/>Recommendations"]
    J["Email<br/>Notifications"]

    K["Amazon S3<br/>Report Storage"]
    L["PDF<br/>Infrastructure Reports"]

    A --> B
    B --> C
    B --> D
    B --> E

    C --> F
    D --> F

    F --> G
    F --> H
    F --> I
    F --> E

    E --> J
    F --> L
    L --> K
```

