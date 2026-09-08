from statistics import mean, pstdev

def _safe_cpu(i):
    try: return float(i.get("CPU", 0) or 0)
    except Exception: return 0.0

def anomaly_score(values):
    vals = [float(v) for v in values if v is not None]
    if len(vals) < 5: return {"anomaly": False, "z": 0.0, "confidence": 0}
    mu, sd = mean(vals), pstdev(vals)
    if sd == 0: return {"anomaly": False, "z": 0.0, "confidence": 0}
    z = abs((vals[-1] - mu) / sd)
    return {"anomaly": z >= 2.2, "z": round(z,2), "confidence": min(99, round(55 + z*15))}

def analyze_instances(instances):
    recs=[]; saving=0.0; incidents=[]
    for i in instances:
        name=i.get("Name") or i.get("InstanceId","Unknown"); cpu=_safe_cpu(i); state=i.get("State","unknown")
        if state != "running":
            recs.append({"type":"cost","severity":"medium","title":"Stopped resource detected","resource":name,"reason":f"{name} is stopped. Review whether it is still required.","action":"Review or remove the resource if it is no longer needed.","saving":2.18,"confidence":88})
            saving += 2.18
        elif cpu < 10:
            recs.append({"type":"optimization","severity":"low","title":"Low sustained utilization","resource":name,"reason":f"Current CPU is {cpu:.1f}%, indicating low compute utilization.","action":"Evaluate right-sizing or scheduled operation.","saving":2.18,"confidence":90})
            saving += 2.18
        elif cpu > 80:
            recs.append({"type":"performance","severity":"high","title":"High CPU utilization","resource":name,"reason":f"CPU is {cpu:.1f}%, which may indicate workload pressure.","action":"Investigate workload and consider scaling if sustained.","saving":0,"confidence":93})
            incidents.append({"title":"High CPU utilization","resource":name,"severity":"high","status":"active"})
        else:
            recs.append({"type":"health","severity":"info","title":"Healthy resource","resource":name,"reason":f"CPU is {cpu:.1f}% and the instance is running.","action":"Continue monitoring.","saving":0,"confidence":86})
    return recs, round(saving,2), incidents

def get_health_score(instances):
    if not instances: return 0, [], 0
    recs,saving,_=analyze_instances(instances); score=100
    for i in instances:
        cpu=_safe_cpu(i)
        if i.get("State") != "running": score -= 8
        elif cpu < 10: score -= 2
        elif cpu > 80: score -= 12
    return max(0,min(100,score)), recs, saving

def get_cost_summary(instances,saving):
    running=sum(i.get("State")=="running" for i in instances); stopped=sum(i.get("State")=="stopped" for i in instances)
    estimated=round(running*8.76,2)
    return {"estimated_monthly_compute":estimated,"potential_savings":round(saving,2),"savings_percent":round(saving/estimated*100,1) if estimated else 0,"running":running,"stopped":stopped}

def get_operations_score(instances, health, security=90):
    if not instances: return 0, {"reliability":0,"performance":0,"cost":0,"security":security}
    running=sum(i.get("State")=="running" for i in instances); avg=mean([_safe_cpu(i) for i in instances])
    reliability=round(running/len(instances)*100); performance=max(0,min(100,round(100-max(0,avg-20)*1.25))); cost=max(0,min(100,round(health*0.85+15))); total=round(reliability*.25+performance*.25+cost*.25+security*.25)
    return total,{"reliability":reliability,"performance":performance,"cost":cost,"security":security}
