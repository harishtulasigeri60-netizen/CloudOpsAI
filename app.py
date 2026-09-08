import os,re,secrets,time
from datetime import datetime,timezone
from functools import wraps
from flask import Flask,render_template,request,redirect,url_for,jsonify,flash,session,send_file,abort,Response
from dotenv import load_dotenv
load_dotenv()
from config import SECRET_KEY,DB_PATH,REGION
from auth import init_db,create_user,get_user_by_email,get_user,touch_login,verify_password,save_aws_connection,get_aws_connection,login_allowed,record_login_failure,record_login_success
from aws_services import get_dashboard_data,get_cpu_history,get_network_history,get_notification_status,send_health_report,subscribe_email,generate_pdf_file,upload_pdf_report,upload_report_to_s3,test_role
from recommendation import get_health_score,get_cost_summary,get_operations_score,analyze_instances,anomaly_score

app=Flask(__name__)
app.config.update(SECRET_KEY=SECRET_KEY or secrets.token_hex(32),SESSION_COOKIE_NAME="cloudopsai_session",SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE","false").lower()=="true",MAX_CONTENT_LENGTH=64*1024,SEND_FILE_MAX_AGE_DEFAULT=0)
init_db(DB_PATH)
_DASH_CACHE={}
_DASH_TTL=20

EMAIL_RE=re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def csrf_token():
    if "csrf" not in session: session["csrf"]=secrets.token_urlsafe(32)
    return session["csrf"]
app.jinja_env.globals["csrf_token"]=csrf_token

def require_csrf():
    if not hmac_safe(request.form.get("csrf_token","") or request.headers.get("X-CSRF-Token","") ,session.get("csrf","")): abort(400)

def hmac_safe(a,b):
    import hmac
    return bool(a and b and hmac.compare_digest(a,b))

def login_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        if not session.get("user_id"): return redirect(url_for("login_page",next=request.path))
        return fn(*args,**kwargs)
    return wrapper

def current_user(): return get_user(DB_PATH,session.get("user_id")) if session.get("user_id") else None

def connection():
    row=get_aws_connection(DB_PATH,session.get("user_id")) if session.get("user_id") else None
    return dict(row) if row else None

def dashboard_context(force=False):
    user_id=session.get("user_id")
    conn=connection()
    key=(user_id, conn.get("account_id") if conn else None, conn.get("role_arn") if conn else None, conn.get("region") if conn else REGION, conn.get("topic_arn") if conn else None, conn.get("bucket_name") if conn else None)
    now=time.monotonic()
    cached=_DASH_CACHE.get(key)
    if cached and not force and now-cached[0] < _DASH_TTL:
        return cached[1]
    data=get_dashboard_data(conn); instances=data.get("instances",[]); score,recs,saving=get_health_score(instances); costs=get_cost_summary(instances,saving); running=[i for i in instances if i.get("State")=="running"]; avg=round(sum(float(i.get("CPU",0)) for i in running)/len(running),1) if running else 0; high=[i for i in running if float(i.get("CPU",0))>=80]; availability=round(len(running)/len(instances)*100) if instances else 0; ops,ops_break=get_operations_score(instances,score,90); recs2,_,incidents=analyze_instances(instances)
    user=current_user()
    public_user=None
    if user:
        public_user={"id":user["id"],"name":user["name"],"email":user["email"],"created_at":user["created_at"],"last_login":user["last_login"]}
    ctx={"data":data,"score":score,"recommendations":recs2,"saving":saving,"costs":costs,"avg_cpu":avg,"active_alerts":len(high),"high_cpu_instances":high,"availability":availability,"health_breakdown":{"cpu":max(0,min(100,round(100-max(0,avg-15)*1.5))),"availability":availability,"alarms":max(0,100-len(high)*20),"cost":max(0,min(100,round(100-costs["savings_percent"]*.5)))},"last_updated":datetime.now().strftime("%d %b %Y, %I:%M:%S %p"),"aws_connected":data.get("aws_connected",False),"notification_status":get_notification_status(conn),"running_instances":running,"user":public_user,"connection":conn,"operations_score":ops,"operations_breakdown":ops_break,"incidents":incidents,"aws_error":data.get("error")}
    _DASH_CACHE[key]=(now,ctx)
    return ctx

def page_context():
    return dashboard_context(force=request.args.get("refresh") == "1")

def invalidate_dashboard_cache():
    _DASH_CACHE.clear()

@app.context_processor
def global_context():
    # Safe defaults are available on every page, including /connect and error pages.
    # Connection metadata is read locally; no AWS API call is made here.
    conn=connection()
    return {
        "logged_in": bool(session.get("user_id")),
        "current_user": current_user(),
        "data": {"region": conn.get("region",REGION) if conn else REGION},
        "region": conn.get("region",REGION) if conn else REGION,
        "aws_connected": bool(conn and conn.get("status") == "verified"),
        "active_alerts": 0,
    }

@app.after_request
def headers(resp):
    resp.headers["X-Content-Type-Options"]="nosniff"; resp.headers["X-Frame-Options"]="DENY"; resp.headers["Referrer-Policy"]="strict-origin-when-cross-origin"; resp.headers["Permissions-Policy"]="geolocation=(), microphone=(), camera=()"; resp.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"; resp.headers["Cache-Control"]="no-store" if request.path.startswith(("/login","/register","/connect","/api")) else resp.headers.get("Cache-Control","no-cache")
    return resp

@app.get("/favicon.ico")
def favicon(): return Response(status=204)

@app.route("/")
def home(): return redirect(url_for("dashboard")) if session.get("user_id") else render_template("index.html")
@app.route("/register",methods=["GET","POST"])
def register():
    if session.get("user_id"): return redirect(url_for("dashboard"))
    if request.method=="POST":
        require_csrf(); name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower(); password=request.form.get("password",""); confirm=request.form.get("confirm_password","")
        if not 2<=len(name)<=80 or not EMAIL_RE.match(email) or len(password)<10 or password!=confirm: return render_template("register.html",error="Use a valid name/email, a password of at least 10 characters, and matching passwords.",form={"name":name,"email":email})
        if get_user_by_email(DB_PATH,email): return render_template("register.html",error="An account with that email already exists.",form={"name":name,"email":email})
        uid=create_user(DB_PATH,name,email,password); session.clear(); session["user_id"]=uid; csrf_token(); flash("Account created. Connect your AWS environment to continue.","success"); return redirect(url_for("connect_aws"))
    return render_template("register.html")
@app.route("/login",methods=["GET","POST"])
def login_page():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        require_csrf()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not login_allowed(DB_PATH, email):
            return render_template("login.html", error="Too many failed attempts. Try again after 15 minutes.")
        user = get_user_by_email(DB_PATH, email)
        if user and verify_password(password, user["password_hash"]):
            session.clear()
            session["user_id"] = user["id"]
            csrf_token()
            touch_login(DB_PATH, user["id"])
            record_login_success(DB_PATH, email)
            next_url = request.args.get("next", "")
            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("dashboard")
            return redirect(next_url)
        record_login_failure(DB_PATH, email)
        return render_template("login.html", error="Invalid email or password.")
    return render_template("login.html")
@app.post("/logout")
def logout(): require_csrf(); session.clear(); return redirect(url_for("home"))

@app.route("/connect",methods=["GET","POST"])
@login_required
def connect_aws():
    if request.method=="POST":
        require_csrf(); role=request.form.get("role_arn","").strip(); region=request.form.get("region",REGION).strip() or REGION; topic=request.form.get("topic_arn","").strip(); bucket=request.form.get("bucket_name","").strip(); result=test_role(role,region)
        if result.get("ok"): save_aws_connection(DB_PATH,session["user_id"],result["account_id"],role,region,topic,bucket,"verified"); invalidate_dashboard_cache(); flash(f"AWS connection verified for account {result['account_id']}.","success"); return redirect(url_for("dashboard"))
        return render_template("connect.html",error=result.get("message","AWS connection failed."),region=region,role_arn=role)
    return render_template("connect.html",connection=connection(),region=REGION)

@app.route("/dashboard")
@login_required
def dashboard(): return render_template("dashboard.html",**page_context())

@app.route("/ec2")
@login_required
def ec2(): return render_template("ec2.html",**page_context())
@app.route("/analytics")
@login_required
def analytics(): return render_template("analytics.html",**page_context())
@app.route("/recommendations")
@login_required
def recommendations(): return render_template("recommendations.html",**page_context())
@app.route("/alarms")
@login_required
def alarms(): return render_template("alarms.html",**page_context())
@app.route("/notifications")
@login_required
def notifications(): return render_template("notifications.html",**page_context())
@app.route("/cost")
@login_required
def cost(): return render_template("cost.html",**page_context())
@app.route("/logs")
@login_required
def logs(): return render_template("logs.html",**page_context())
@app.route("/reports")
@login_required
def reports(): return render_template("reports.html",**page_context())
@app.route("/instance/<instance_id>")
@login_required
def instance_detail(instance_id):
    ctx=page_context(); instance=next((i for i in ctx["data"].get("instances",[]) if i.get("InstanceId")==instance_id),None)
    if not instance: flash("The requested EC2 instance was not found.","error"); return redirect(url_for("ec2"))
    return render_template("instance_detail.html",**ctx,instance=instance)

@app.get("/api/dashboard")
@login_required
def api_dashboard(): return jsonify(dashboard_context(force=request.args.get("refresh") == "1"))
@app.get("/api/cpu-history/<instance_id>")
@login_required
def api_cpu(instance_id): return jsonify(get_cpu_history(instance_id,connection()))
@app.get("/api/network-history/<instance_id>")
@login_required
def api_network(instance_id): return jsonify(get_network_history(instance_id,connection()))
@app.get("/api/notifications/status")
@login_required
def api_notifications(): return jsonify(get_notification_status(connection()))

@app.post("/send-test-email")
@login_required
def send_test_email():
    require_csrf(); r=send_health_report(test=True,connection=connection()); flash("SNS accepted the test notification." if r.get("ok") else f"Test notification failed: {r.get('message')}","success" if r.get("ok") else "error"); return redirect(url_for("notifications"))
@app.post("/subscribe-email")
@login_required
def subscribe():
    require_csrf(); email=request.form.get("email","").strip(); r=subscribe_email(email,connection()); flash("SNS subscription request sent. Confirm it from your email." if r.get("ok") and not r.get("already_confirmed") else ("Email is already confirmed." if r.get("ok") else f"Subscription failed: {r.get('message')}"),"warning" if r.get("ok") and not r.get("already_confirmed") else ("success" if r.get("ok") else "error")); return redirect(url_for("notifications"))
@app.post("/send-report")
@login_required
def send_report():
    require_csrf(); r=send_health_report(connection=connection()); flash("Health report published to SNS." if r.get("ok") else f"Report email failed: {r.get('message')}","success" if r.get("ok") else "error"); return redirect(url_for("notifications"))
@app.post("/download-pdf")
@login_required
def download_pdf():
    require_csrf(); ctx=page_context(); path=generate_pdf_file(ctx["data"],ctx["score"],ctx["recommendations"]); return send_file(path,as_attachment=True,download_name=os.path.basename(path),mimetype="application/pdf")
@app.post("/upload-report")
@login_required
def upload_report():
    require_csrf()
    try: ctx=page_context(); key=upload_report_to_s3(ctx["data"],ctx["score"],ctx["recommendations"],connection()); flash(f"JSON report uploaded to S3: {key}","success")
    except Exception as e: flash(f"S3 upload failed: {e}","error")
    return redirect(url_for("reports"))
@app.post("/generate-pdf")
@login_required
def generate_pdf():
    require_csrf()
    try: ctx=page_context(); name=upload_pdf_report(ctx["data"],ctx["score"],ctx["recommendations"],connection()); flash(f"PDF uploaded to S3: {name}","success")
    except Exception as e: flash(f"PDF/S3 upload failed: {e}","error")
    return redirect(url_for("reports"))


@app.errorhandler(400)
def bad_request(e):
    return render_template("error.html", error_code=400, error_title="Request rejected", error_message="The request could not be validated. Refresh the page and try again."), 400

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", error_code=404, error_title="Page not found", error_message="The requested CloudOpsAI page does not exist."), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", error_code=500, error_title="Something went wrong", error_message="CloudOpsAI handled an unexpected server error. Check the application log for details."), 500

if __name__=="__main__": app.run(host="127.0.0.1",port=int(os.getenv("PORT","5000")),debug=False)
