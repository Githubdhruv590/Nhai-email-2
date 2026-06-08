from flask import Flask, render_template, request, jsonify, redirect, session
import pandas as pd
import os
import threading
import time
import base64
import json
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "nhai-email-portal-secret-2024")

# ------------------------------------
# Load credentials.json from env var
# (for Render deployment)
# ------------------------------------
creds_data = os.environ.get("GOOGLE_CREDENTIALS_JSON")
if creds_data:
    with open("credentials.json", "w") as f:
        f.write(creds_data)

# ------------------------------------
# Only allow insecure transport locally
# ------------------------------------
if os.environ.get("RENDER") != "true":
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

SCOPES = ['https://www.googleapis.com/auth/gmail.send']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

RECIPIENT_FOLDER = "uploads/recipients"
ATTACHMENT_FOLDER = "uploads/attachments"
LOG_FOLDER = "logs"

os.makedirs(RECIPIENT_FOLDER, exist_ok=True)
os.makedirs(ATTACHMENT_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)

campaign_status = {
    "running": False,
    "total": 0,
    "sent": 0,
    "failed": 0,
    "logs": []
}


# ----------------------------------------
# Replace {{placeholders}} in text
# ----------------------------------------

def personalize_text(text, row):
    result = text
    for column in row.index:
        placeholder = f"{{{{{column}}}}}"
        value = str(row[column])
        result = result.replace(placeholder, value)
    return result


# ----------------------------------------
# Send a single email via Gmail API
# ----------------------------------------

def send_email(service, sender_email, receiver_email, subject, body, attachment_paths):
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "html"))

    for file_path in attachment_paths:
        with open(file_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(file_path)}"'
        )
        message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()


# ----------------------------------------
# Bulk sender (runs in background thread)
# ----------------------------------------

def send_campaign(recipient_path, sender_email, subject_template, body_template, attachment_paths):
    global campaign_status

    # Load recipients
    try:
        employees = pd.read_excel(recipient_path)
    except Exception as e:
        campaign_status["running"] = False
        campaign_status["logs"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "recipient": "System",
            "status": "failed",
            "error": f"Failed to load recipient file: {str(e)}"
        })
        return

    # Detect email column
    email_column = None
    for col in employees.columns:
        if str(col).strip().lower() == "email":
            email_column = col
            break

    if email_column is None:
        campaign_status["running"] = False
        campaign_status["logs"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "recipient": "System",
            "status": "failed",
            "error": "Email column not found in Excel file"
        })
        return

    campaign_status["running"] = True
    campaign_status["total"] = len(employees)
    campaign_status["sent"] = 0
    campaign_status["failed"] = 0
    campaign_status["logs"] = []

    # Initialize Gmail API
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())

        service = build('gmail', 'v1', credentials=creds)
        print("Gmail API initialized successfully")

        log_filename = f"campaign_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        log_path = os.path.join(LOG_FOLDER, log_filename)
        log_file = open(log_path, "w", encoding="utf-8")
        log_file.write(f"Campaign Started\nTotal Recipients: {len(employees)}\n\n")

    except Exception as e:
        campaign_status["running"] = False
        campaign_status["logs"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "recipient": "System",
            "status": "failed",
            "error": f"Gmail API init failed: {str(e)}"
        })
        return

    campaign_status["logs"].append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "recipient": "System",
        "status": "info",
        "error": f"Starting campaign. Total recipients: {len(employees)}"
    })

    # Send emails
    for _, row in employees.iterrows():
        recipient = "Unknown"
        try:
            recipient = str(row.get(email_column, "")).strip()

            if not recipient or "@" not in recipient:
                raise Exception("Missing or invalid email address")

            subject = personalize_text(subject_template or "", row)
            body = personalize_text(body_template or "", row)

            send_email(service, sender_email, recipient, subject, body, attachment_paths)

            campaign_status["sent"] += 1
            log_file.write(f"[{datetime.now().strftime('%H:%M:%S')}] SENT -> {recipient}\n")
            campaign_status["logs"].append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "recipient": recipient,
                "status": "sent",
                "error": ""
            })

            time.sleep(0.5)

        except Exception as e:
            campaign_status["failed"] += 1
            log_file.write(f"[{datetime.now().strftime('%H:%M:%S')}] FAILED -> {recipient}\nERROR: {str(e)}\n\n")
            campaign_status["logs"].append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "recipient": recipient,
                "status": "failed",
                "error": str(e)
            })
            print(f"Error sending to {recipient}: {e}")

    # Finish up
    campaign_status["running"] = False
    log_file.write(f"\nCampaign Finished\nSent: {campaign_status['sent']}\nFailed: {campaign_status['failed']}\n")
    log_file.close()

    campaign_status["logs"].append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "recipient": "System",
        "status": "info",
        "error": f"Campaign finished. Sent: {campaign_status['sent']}, Failed: {campaign_status['failed']}"
    })

    # Cleanup temp files
    try:
        if os.path.exists(recipient_path):
            os.remove(recipient_path)
        for file_path in attachment_paths:
            if os.path.exists(file_path):
                os.remove(file_path)
    except Exception as e:
        print(f"Cleanup error: {e}")


# ----------------------------------------
# ROUTES
# ----------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ----------------------------------------
# Gmail OAuth2 - Step 1: Redirect to Google
# ----------------------------------------

@app.route("/authorize")
def authorize():
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=request.host_url.rstrip('/') + '/oauth2callback'
    )
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    session['state'] = state
    return redirect(auth_url)


# ----------------------------------------
# Gmail OAuth2 - Step 2: Google redirects back
# ----------------------------------------

@app.route("/oauth2callback")
def oauth2callback():
    try:
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_FILE,
            scopes=SCOPES,
            state=session.get('state'),
            redirect_uri=request.host_url.rstrip('/') + '/oauth2callback'
        )
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials

        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())

        return redirect('/')
    except Exception as e:
        return f"OAuth Error: {str(e)}", 400


# ----------------------------------------
# Check if Gmail is authorized
# ----------------------------------------

@app.route("/auth-status")
def auth_status():
    if not os.path.exists(TOKEN_FILE):
        return jsonify({"authorized": False, "email": ""})

    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.valid:
            service = build('gmail', 'v1', credentials=creds)
            profile = service.users().getProfile(userId='me').execute()
            return jsonify({"authorized": True, "email": profile.get("emailAddress", "")})

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())
            service = build('gmail', 'v1', credentials=creds)
            profile = service.users().getProfile(userId='me').execute()
            return jsonify({"authorized": True, "email": profile.get("emailAddress", "")})

    except Exception:
        pass

    return jsonify({"authorized": False, "email": ""})


# ----------------------------------------
# Validate recipient Excel file
# ----------------------------------------

@app.route("/validate-recipients", methods=["POST"])
def validate_recipients():
    file = request.files.get("recipient_file")

    if not file:
        return jsonify({"success": False, "error": "No file uploaded"})

    try:
        df = pd.read_excel(file)
        email_found = any(col.strip().lower() == "email" for col in df.columns)

        if not email_found:
            return jsonify({"success": False, "error": "Email column missing in Excel"})

        return jsonify({
            "success": True,
            "recipient_count": len(df),
            "columns": list(df.columns)
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ----------------------------------------
# Preview email for first recipient
# ----------------------------------------

@app.route("/preview", methods=["POST"])
def preview():
    subject_template = request.form.get("subject")
    body_template = request.form.get("body")
    file = request.files.get("recipient_file")

    if not file:
        return jsonify({"success": False, "error": "Please upload a recipient Excel file first"})

    try:
        employees = pd.read_excel(file)

        if len(employees) == 0:
            return jsonify({"success": False, "error": "The uploaded Excel file is empty"})

        first_row = employees.iloc[0]
        email_column = None

        for col in employees.columns:
            if str(col).strip().lower() == "email":
                email_column = col
                break

        preview_subject = personalize_text(subject_template or "", first_row)
        preview_body = personalize_text(body_template or "", first_row)

        return jsonify({
            "success": True,
            "recipient": str(first_row.get(email_column, "N/A")),
            "subject": preview_subject,
            "body": preview_body,
            "total_recipients": len(employees)
        })

    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to parse Excel file: {str(e)}"})


# ----------------------------------------
# Start campaign
# ----------------------------------------

@app.route("/send", methods=["POST"])
def send():
    global campaign_status

    if campaign_status["running"]:
        return jsonify({"status": "error", "message": "A campaign is already running"})

    if not os.path.exists(TOKEN_FILE):
        return jsonify({"status": "error", "message": "Gmail not connected. Please authorize first."})

    subject = request.form.get("subject")
    body = request.form.get("body")

    # Get sender email from token
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        sender_email = profile.get("emailAddress", "me")
    except Exception as e:
        return jsonify({"status": "error", "message": f"Gmail auth error: {str(e)}"})

    # Save recipient file
    recipient_file = request.files.get("recipient_file")
    if not recipient_file or recipient_file.filename == "":
        return jsonify({"status": "error", "message": "Please upload a recipient Excel file"})

    recipient_filename = f"recipients_{int(time.time())}.xlsx"
    recipient_path = os.path.join(RECIPIENT_FOLDER, recipient_filename)
    recipient_file.save(recipient_path)

    # Save attachments
    files = request.files.getlist("attachments")
    attachment_paths = []
    for file in files:
        if file.filename == "":
            continue
        path = os.path.join(ATTACHMENT_FOLDER, file.filename)
        file.save(path)
        attachment_paths.append(path)

    # Reset status
    campaign_status = {
        "running": True,
        "total": 0,
        "sent": 0,
        "failed": 0,
        "logs": [{
            "time": datetime.now().strftime("%H:%M:%S"),
            "recipient": "System",
            "status": "info",
            "error": "Initializing campaign..."
        }]
    }

    # Start background thread
    thread = threading.Thread(
        target=send_campaign,
        args=(recipient_path, sender_email, subject, body, attachment_paths)
    )
    thread.daemon = True
    thread.start()

    return jsonify({"status": "success", "message": "Campaign started successfully!"})


# ----------------------------------------
# Poll campaign status
# ----------------------------------------

@app.route("/status", methods=["GET"])
def status():
    global campaign_status
    return jsonify(campaign_status)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)