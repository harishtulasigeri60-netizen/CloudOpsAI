from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape


def _safe(value):
    # ReportLab's built-in fonts do not support emoji; keep report text portable.
    text = str(value).replace("⚠️", "WARNING:").replace("⚠", "WARNING:").replace("💡", "TIP:").replace("🟢", "OK:").replace("🔴", "ALERT:")
    return escape(text)


def generate_report(data, score, recommendations, output_path="CloudOps_AI_Report.pdf"):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path))
    styles = getSampleStyleSheet()
    story = [
        Paragraph("<b>CloudOpsAI</b>", styles["Title"]),
        Paragraph("AWS Infrastructure Monitoring Report", styles["Heading2"]),
        Spacer(1, 20),
        Paragraph(f"Generated On: {_safe(datetime.now().strftime('%d-%m-%Y %H:%M:%S'))}", styles["Normal"]),
        Paragraph(f"Infrastructure Health Score: {_safe(score)}/100", styles["Normal"]),
        Spacer(1, 20),
        Paragraph("EC2 Instance Details", styles["Heading2"]),
        Spacer(1, 10),
    ]
    for instance in data.get("instances", []):
        story.append(Paragraph(
            f"<b>Instance ID:</b> {_safe(instance.get('InstanceId','N/A'))}<br/>"
            f"<b>Name:</b> {_safe(instance.get('Name','N/A'))}<br/>"
            f"<b>Status:</b> {_safe(instance.get('State','N/A'))}<br/>"
            f"<b>Type:</b> {_safe(instance.get('InstanceType','N/A'))}<br/>"
            f"<b>CPU Utilization:</b> {_safe(instance.get('CPU',0))}%<br/>"
            f"<b>Availability Zone:</b> {_safe(instance.get('AvailabilityZone','N/A'))}<br/>",
            styles["Normal"]
        ))
        story.append(Spacer(1, 10))
    story.extend([Paragraph("AI Recommendations", styles["Heading2"]), Spacer(1, 10)])
    for item in recommendations or ["No recommendations at this time."]:
        if isinstance(item, dict):
            text = f"<b>{_safe(item.get('title','Insight'))}</b><br/>Resource: {_safe(item.get('resource','N/A'))}<br/>Reason: {_safe(item.get('reason','N/A'))}<br/>Action: {_safe(item.get('action','N/A'))}<br/>Confidence: {_safe(item.get('confidence','N/A'))}%"
        else:
            text = _safe(item)
        story.append(Paragraph(text, styles["Normal"]))
        story.append(Spacer(1, 5))
    doc.build(story)
    return str(path)
