import json, os, re
from datetime import datetime,timedelta,timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import boto3
from botocore.exceptions import BotoCoreError,ClientError
from pdf_report import generate_report
from config import REGION,TOPIC_ARN,BUCKET_NAME,REPORT_DIR

_EMAIL_RE=re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ROLE_CACHE={}
_ROLE_CACHE_TTL=300

def _clients(region=None, credentials=None):
    kwargs={"region_name":region or REGION}
    if credentials: kwargs.update({"aws_access_key_id":credentials["AccessKeyId"],"aws_secret_access_key":credentials["SecretAccessKey"],"aws_session_token":credentials["SessionToken"]})
    return {k:boto3.client(k,**kwargs) for k in ("ec2","cloudwatch","sns","s3","sts","ce")}


def _name(instance):
    return next((t.get("Value") for t in instance.get("Tags",[]) if t.get("Key")=="Name" and t.get("Value")),instance.get("InstanceId","Unknown")[:12])

def assume_role(role_arn,region):
    if not re.match(r"^arn:(aws|aws-us-gov|aws-cn):iam::\d{12}:role/[A-Za-z0-9+=,.@_-]{1,512}$",role_arn): return {"ok":False,"message":"Invalid IAM role ARN format."}
    key=(role_arn,region or REGION); now=time.monotonic(); cached=_ROLE_CACHE.get(key)
    if cached and now-cached[0] < _ROLE_CACHE_TTL:
        return {"ok":True,"credentials":cached[1],"account_id":cached[2]}
    try:
        sts=boto3.client("sts",region_name=region or REGION); r=sts.assume_role(RoleArn=role_arn,RoleSessionName="CloudOpsAI-Session",DurationSeconds=3600); creds=r["Credentials"]; account=r["AssumedRoleUser"]["Arn"].split(":")[4]
        _ROLE_CACHE[key]=(now,creds,account)
        return {"ok":True,"credentials":creds,"account_id":account}
    except (BotoCoreError,ClientError) as e: return {"ok":False,"message":str(e)}

def test_role(role_arn,region):
    result=assume_role(role_arn,region)
    if not result["ok"]: return result
    try:
        sts=_clients(region,result["credentials"])["sts"]; ident=sts.get_caller_identity(); return {"ok":True,"account_id":ident["Account"],"arn":ident["Arn"]}
    except (BotoCoreError,ClientError) as e: return {"ok":False,"message":str(e)}

def get_dashboard_data(connection=None):
    if not connection:
        return {"instances":[],"total_instances":0,"region":REGION,"aws_connected":False,"error":"Connect an AWS environment to begin monitoring.","account_id":""}
    try:
        clients=_clients(connection.get("region") if connection else REGION, None)
        if connection:
            assumed=assume_role(connection["role_arn"],connection["region"])
            if not assumed["ok"]: return {"instances":[],"total_instances":0,"region":connection["region"],"aws_connected":False,"error":assumed["message"]}
            clients=_clients(connection["region"],assumed["credentials"]); account_id=assumed["account_id"]
        else:
            account_id=clients["sts"].get_caller_identity()["Account"]
        reservations=clients["ec2"].describe_instances().get("Reservations",[]); raw=[]
        for r in reservations:
            raw.extend(r.get("Instances",[]))
        running_ids=[x["InstanceId"] for x in raw if x.get("State",{}).get("Name") == "running"]
        cpu_map={}
        if running_ids:
            def read_cpu(iid): return iid,get_cpu_utilization(iid,clients["cloudwatch"])
            with ThreadPoolExecutor(max_workers=min(8,len(running_ids))) as pool:
                futures=[pool.submit(read_cpu,iid) for iid in running_ids]
                for f in as_completed(futures):
                    iid,val=f.result(); cpu_map[iid]=val
        instances=[]
        for x in raw:
            state=x.get("State",{}).get("Name","unknown"); instances.append({"InstanceId":x["InstanceId"],"Name":_name(x),"State":state,"InstanceType":x.get("InstanceType","N/A"),"PublicIP":x.get("PublicIpAddress","N/A"),"AvailabilityZone":x.get("Placement",{}).get("AvailabilityZone","N/A"),"CPU":cpu_map.get(x["InstanceId"],0),"Monitoring":x.get("Monitoring",{}).get("State","disabled"),"LaunchTime":x.get("LaunchTime").isoformat() if x.get("LaunchTime") else "N/A"})
        return {"instances":instances,"total_instances":len(instances),"region":connection["region"] if connection else REGION,"aws_connected":True,"error":None,"account_id":account_id}
    except (BotoCoreError,ClientError,Exception) as e: return {"instances":[],"total_instances":0,"region":connection["region"] if connection else REGION,"aws_connected":False,"error":str(e),"account_id":""}

def get_cpu_utilization(instance_id,client=None):
    try:
        cw=client or _clients()["cloudwatch"]; end=datetime.now(timezone.utc); pts=cw.get_metric_statistics(Namespace="AWS/EC2",MetricName="CPUUtilization",Dimensions=[{"Name":"InstanceId","Value":instance_id}],StartTime=end-timedelta(minutes=30),EndTime=end,Period=300,Statistics=["Average"]).get("Datapoints",[]); return round(max(pts,key=lambda x:x["Timestamp"])["Average"],2) if pts else 0
    except Exception:return 0

def history(instance_id,metric,connection=None):
    if not connection: return {"labels":[],"values":[],"error":"Connect an AWS environment first."}
    try:
        region=connection.get("region") if connection else REGION; creds=None
        if connection:
            a=assume_role(connection["role_arn"],region)
            if not a["ok"]: return {"labels":[],"values":[],"error":a["message"]}
            creds=a["credentials"]
        cw=_clients(region,creds)["cloudwatch"]; end=datetime.now(timezone.utc); pts=cw.get_metric_statistics(Namespace="AWS/EC2",MetricName=metric,Dimensions=[{"Name":"InstanceId","Value":instance_id}],StartTime=end-timedelta(hours=1),EndTime=end,Period=300,Statistics=["Average"]).get("Datapoints",[]); pts=sorted(pts,key=lambda x:x["Timestamp"]); return {"labels":[p["Timestamp"].astimezone().strftime("%H:%M") for p in pts],"values":[round(p["Average"],2) for p in pts]}
    except Exception as e:return {"labels":[],"values":[],"error":str(e)}

def get_cpu_history(instance_id,connection=None): return history(instance_id,"CPUUtilization",connection)
def get_network_history(instance_id,connection=None):
    if not connection: return {"labels":[],"network_in":[],"network_out":[],"error":"Connect an AWS environment first."}
    try:
        region=connection.get("region") if connection else REGION; creds=None
        if connection:
            x=assume_role(connection["role_arn"],region)
            if not x["ok"]: return {"labels":[],"network_in":[],"network_out":[],"error":x["message"]}
            creds=x["credentials"]
        cw=_clients(region,creds)["cloudwatch"]; end=datetime.now(timezone.utc); out={}
        for metric,key in (("NetworkIn","network_in"),("NetworkOut","network_out")):
            pts=cw.get_metric_statistics(Namespace="AWS/EC2",MetricName=metric,Dimensions=[{"Name":"InstanceId","Value":instance_id}],StartTime=end-timedelta(hours=1),EndTime=end,Period=300,Statistics=["Average"]).get("Datapoints",[])
            for p in pts: out.setdefault(p["Timestamp"],{})[key]=round(p["Average"]/1024/1024,3)
        stamps=sorted(out); return {"labels":[s.astimezone().strftime("%H:%M") for s in stamps],"network_in":[out[s].get("network_in",0) for s in stamps],"network_out":[out[s].get("network_out",0) for s in stamps]}
    except Exception as e:return {"labels":[],"network_in":[],"network_out":[],"error":str(e)}

def get_notification_status(connection=None):
    topic=(connection or {}).get("topic_arn") or TOPIC_ARN
    if not topic:return {"configured":False,"confirmed":False,"pending":False,"subscriptions":[],"message":"SNS topic ARN is not configured for this AWS connection."}
    try:
        region=(connection or {}).get("region") or REGION; creds=None
        if connection:
            a=assume_role(connection["role_arn"],region)
            if not a["ok"]: return {"configured":True,"confirmed":False,"pending":False,"subscriptions":[],"message":a["message"]}
            creds=a["credentials"]
        sns=_clients(region,creds)["sns"]; sns.get_topic_attributes(TopicArn=topic); subs=sns.list_subscriptions_by_topic(TopicArn=topic).get("Subscriptions",[]); rows=[]
        for s in subs: rows.append({"protocol":s.get("Protocol",""),"endpoint":s.get("Endpoint",""),"status":"confirmed" if s.get("SubscriptionArn") and s.get("SubscriptionArn")!="PendingConfirmation" else "pending"})
        return {"configured":True,"confirmed":any(x["status"]=="confirmed" for x in rows),"pending":any(x["status"]=="pending" for x in rows),"subscriptions":rows,"message":f"{sum(x['status']=='confirmed' for x in rows)} confirmed, {sum(x['status']=='pending' for x in rows)} pending."}
    except Exception as e:return {"configured":True,"confirmed":False,"pending":False,"subscriptions":[],"message":f"SNS check failed: {e}"}

def subscribe_email(email,connection=None):
    topic=(connection or {}).get("topic_arn") or TOPIC_ARN
    if not topic:return {"ok":False,"message":"SNS topic ARN is not configured for this AWS connection."}
    if not _EMAIL_RE.match(email):return {"ok":False,"message":"Invalid email address."}
    try:
        region=(connection or {}).get("region") or REGION; creds=None
        if connection:
            a=assume_role(connection["role_arn"],region)
            if not a["ok"]: return {"ok":False,"message":a["message"]}
            creds=a["credentials"]
        sns=_clients(region,creds)["sns"]; current=sns.list_subscriptions_by_topic(TopicArn=topic).get("Subscriptions",[])
        for s in current:
            if s.get("Endpoint","").lower()==email.lower() and s.get("Protocol")=="email": return {"ok":True,"already_confirmed":s.get("SubscriptionArn")!="PendingConfirmation"}
        r=sns.subscribe(TopicArn=topic,Protocol="email",Endpoint=email,ReturnSubscriptionArn=True); return {"ok":True,"already_confirmed":False,"subscription_arn":r.get("SubscriptionArn")}
    except Exception as e:return {"ok":False,"message":str(e)}

def send_health_report(test=False, connection=None):
    topic = (connection or {}).get("topic_arn") or TOPIC_ARN

    if not topic:
        return {
            "ok": False,
            "message": "SNS topic ARN is not configured for this AWS connection."
        }

    try:
        region = (connection or {}).get("region") or REGION
        creds = None

        if connection:
            a = assume_role(connection["role_arn"], region)
            if not a["ok"]:
                return {"ok": False, "message": a["message"]}
            creds = a["credentials"]

        clients = _clients(region, creds)
        ec2 = clients["ec2"]
        sns = clients["sns"]
        cloudwatch = clients["cloudwatch"]

        # ---------------------------------------------------------
        # TEST NOTIFICATION
        # ---------------------------------------------------------
        if test:
            message = f"""CloudOpsAI Test Notification

AWS Region: {region}

SNS connectivity is working successfully.

CloudOpsAI can now publish notifications to this SNS topic.

This is a test message generated from CloudOpsAI.
"""

            r = sns.publish(
                TopicArn=topic,
                Subject="CloudOpsAI Test Notification"[:100],
                Message=message
            )

            return {
                "ok": True,
                "message_id": r.get("MessageId")
            }

        # ---------------------------------------------------------
        # GET EC2 INSTANCES
        # ---------------------------------------------------------
        response = ec2.describe_instances()

        instances = []

        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                state = instance.get("State", {}).get("Name", "unknown")

                name = instance.get("InstanceId", "Unknown")

                for tag in instance.get("Tags", []):
                    if tag.get("Key") == "Name":
                        name = tag.get("Value") or name
                        break

                instances.append({
                    "id": instance.get("InstanceId", "unknown"),
                    "name": name,
                    "state": state,
                    "type": instance.get("InstanceType", "unknown"),
                    "az": instance.get("Placement", {}).get(
                        "AvailabilityZone", "unknown"
                    )
                })

        # ---------------------------------------------------------
        # GET CPU UTILIZATION
        # ---------------------------------------------------------
        from datetime import datetime, timedelta, timezone

        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=1)

        cpu_values = {}

        for instance in instances:

            if instance["state"] != "running":
                cpu_values[instance["id"]] = 0.0
                continue

            try:
                metric = cloudwatch.get_metric_statistics(
                    Namespace="AWS/EC2",
                    MetricName="CPUUtilization",
                    Dimensions=[
                        {
                            "Name": "InstanceId",
                            "Value": instance["id"]
                        }
                    ],
                    StartTime=start,
                    EndTime=end,
                    Period=300,
                    Statistics=["Average"]
                )

                datapoints = metric.get("Datapoints", [])

                if datapoints:
                    cpu = sum(
                        float(d.get("Average", 0))
                        for d in datapoints
                    ) / len(datapoints)
                else:
                    cpu = 0.0

                cpu_values[instance["id"]] = round(cpu, 2)

            except Exception:
                cpu_values[instance["id"]] = 0.0

        # ---------------------------------------------------------
        # ANALYZE INFRASTRUCTURE
        # ---------------------------------------------------------
        running = [
            i for i in instances
            if i["state"] == "running"
        ]

        stopped = [
            i for i in instances
            if i["state"] == "stopped"
        ]

        high_cpu = []

        for instance in running:
            cpu = cpu_values.get(instance["id"], 0.0)

            if cpu >= 80:
                high_cpu.append((instance, cpu))

        # ---------------------------------------------------------
        # HEALTH SCORE
        # ---------------------------------------------------------
        total = len(instances)

        if total == 0:
            health_score = 0
        else:
            score = 100

            # Stopped instances
            score -= min(len(stopped) * 10, 30)

            # High CPU instances
            score -= min(len(high_cpu) * 15, 45)

            health_score = max(0, min(100, score))

        # ---------------------------------------------------------
        # SEVERITY
        # ---------------------------------------------------------
        if high_cpu:
            severity = "CRITICAL"
        elif stopped:
            severity = "WARNING"
        else:
            severity = "HEALTHY"

        # ---------------------------------------------------------
        # BUILD EMAIL MESSAGE
        # ---------------------------------------------------------
        lines = []

        lines.append("CLOUDOPSAI INFRASTRUCTURE HEALTH ALERT")
        lines.append("=" * 45)
        lines.append("")
        lines.append(f"AWS Region       : {region}")
        lines.append(f"Health Score     : {health_score}/100")
        lines.append(f"Overall Status   : {severity}")
        lines.append("")
        lines.append("INFRASTRUCTURE SUMMARY")
        lines.append("-" * 45)
        lines.append(f"Total EC2        : {total}")
        lines.append(f"Running          : {len(running)}")
        lines.append(f"Stopped          : {len(stopped)}")
        lines.append(f"High CPU         : {len(high_cpu)}")
        lines.append("")

        # ---------------------------------------------------------
        # INSTANCE DETAILS
        # ---------------------------------------------------------
        lines.append("EC2 INSTANCE STATUS")
        lines.append("-" * 45)

        if not instances:
            lines.append("No EC2 instances were found.")

        for instance in instances:

            cpu = cpu_values.get(instance["id"], 0.0)

            lines.append(
                f"{instance['name']} | "
                f"{instance['state'].upper()} | "
                f"CPU {cpu:.2f}% | "
                f"{instance['type']} | "
                f"{instance['az']}"
            )

        lines.append("")

        # ---------------------------------------------------------
        # FINDINGS
        # ---------------------------------------------------------
        lines.append("CLOUDOPSAI FINDINGS")
        lines.append("-" * 45)

        if high_cpu:

            lines.append(
                f"WARNING: {len(high_cpu)} running instance(s) "
                "have CPU utilization at or above 80%."
            )

            for instance, cpu in high_cpu:
                lines.append(
                    f"  - {instance['name']}: {cpu:.2f}% CPU"
                )

        if stopped:

            lines.append(
                f"INFO: {len(stopped)} instance(s) are currently stopped."
            )

            for instance in stopped:
                lines.append(
                    f"  - {instance['name']}"
                )

        if not high_cpu and not stopped:
            lines.append(
                "No immediate EC2 health issues were detected."
            )

        lines.append("")

        # ---------------------------------------------------------
        # RECOMMENDATIONS
        # ---------------------------------------------------------
        lines.append("RECOMMENDED ACTIONS")
        lines.append("-" * 45)

        if high_cpu:
            lines.append(
                "1. Investigate workloads on high-CPU instances."
            )
            lines.append(
                "2. Review CloudWatch CPU trends before scaling."
            )
            lines.append(
                "3. Consider right-sizing or scaling if high "
                "utilization persists."
            )

        if stopped:
            lines.append(
                "1. Verify that stopped instances are intentionally stopped."
            )
            lines.append(
                "2. Review unused resources to avoid unnecessary "
                "storage-related costs."
            )

        if not high_cpu and not stopped:
            lines.append(
                "1. Continue monitoring CPU utilization."
            )
            lines.append(
                "2. Review CloudWatch trends periodically."
            )

        lines.append("")
        lines.append("=" * 45)
        lines.append("Generated automatically by CloudOpsAI.")
        lines.append(
            "This notification is based on the current AWS infrastructure state."
        )

        message = "\n".join(lines)

        # ---------------------------------------------------------
        # SEND THROUGH SNS
        # ---------------------------------------------------------
        r = sns.publish(
            TopicArn=topic,
            Subject=(
                f"CloudOpsAI {severity} - "
                f"Infrastructure Health Report"
            )[:100],
            Message=message
        )

        return {
            "ok": True,
            "message_id": r.get("MessageId")
        }

    except Exception as e:
        return {
            "ok": False,
            "message": str(e)
        }

def generate_pdf_file(data,score,recommendations):
    path=REPORT_DIR/f"CloudOpsAI_Health_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"; generate_report(data,score,recommendations,output_path=str(path)); return str(path)

def upload_report_to_s3(data,score,recommendations,connection=None):
    bucket=(connection or {}).get("bucket_name") or BUCKET_NAME
    if not bucket: raise RuntimeError("S3 bucket is not configured for this AWS connection.")
    report={"Generated On":datetime.now().isoformat(),"Region":data.get("region"),"Health Score":score,"Total EC2":data.get("total_instances",0),"Instances":data.get("instances",[]),"Recommendations":recommendations}; key=f"reports/CloudOpsAI_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    clients=_clients((connection or {}).get("region") or REGION,None)
    if connection:
        a=assume_role(connection["role_arn"],connection["region"])
        if not a["ok"]: raise RuntimeError(a["message"])
        clients=_clients(connection["region"],a["credentials"])
    clients["s3"].put_object(Bucket=bucket,Key=key,Body=json.dumps(report,indent=2,default=str),ContentType="application/json"); return key

def upload_pdf_report(data,score,recommendations,connection=None):
    bucket=(connection or {}).get("bucket_name") or BUCKET_NAME
    if not bucket: raise RuntimeError("S3 bucket is not configured for this AWS connection.")
    path=generate_pdf_file(data,score,recommendations)
    clients=_clients((connection or {}).get("region") or REGION, None)
    if connection:
        a=assume_role(connection["role_arn"],connection["region"])
        if not a["ok"]: raise RuntimeError(a["message"])
        clients=_clients(connection["region"],a["credentials"])
    clients["s3"].upload_file(path,bucket,f"reports/{Path(path).name}"); return Path(path).name
