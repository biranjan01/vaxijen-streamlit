import streamlit as st
import asyncio
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

st.set_page_config(page_title="VaxiJen Session Server", page_icon="🧬")

COOKIE_FILE = Path("./cf_cookies.json")

st.title("🧬 VaxiJen Session Server")
st.markdown("Solves Cloudflare and emails session cookies for use in camoufox-js")

# Email config in sidebar
with st.sidebar:
    st.header("Email Settings")
    smtp_server = st.text_input("SMTP Server", value="smtp.gmail.com")
    smtp_port = st.number_input("SMTP Port", value=587)
    sender_email = st.text_input("Sender Email")
    sender_password = st.text_input("Sender Password", type="password", help="Use App Password for Gmail")
    recipient_email = st.text_input("Recipient Email")

def save_cookies(cookies_dict, ua):
    with open(COOKIE_FILE, "w") as f:
        json.dump({"cookies": cookies_dict, "user_agent": ua}, f)

def load_cookies():
    if COOKIE_FILE.exists():
        with open(COOKIE_FILE) as f:
            return json.load(f)
    return None

def send_email(cookies_data):
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = "VaxiJen Cloudflare Session"

    body = json.dumps(cookies_data, indent=2)
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)

if st.button("🚀 Solve Cloudflare & Send Cookies"):
    if not all([sender_email, sender_password, recipient_email]):
        st.error("Fill in all email settings in the sidebar")
    else:
        with st.spinner("Launching Camoufox..."):
            from camoufox.sync_api import Camoufox

            with Camoufox(headless="virtual", humanize=True) as browser:
                page = browser.new_page()
                page.goto(
                    "https://www.ddg-pharmfac.net/vaxijen/VaxiJen/VaxiJen.html",
                    wait_until="networkidle",
                    timeout=90000,
                )

                title = page.title()
                st.info(f"Page title: {title}")

                if "Just a moment" in title:
                    st.info("Cloudflare detected, waiting...")
                    for _ in range(30):
                        page.wait_for_timeout(2000)
                        title = page.title()
                        if "Just a moment" not in title:
                            break
                    st.info(f"Title after wait: {title}")

                if "Just a moment" in title:
                    st.error("Could not bypass Cloudflare")
                else:
                    all_cookies = page.context.cookies()
                    user_agent = page.evaluate("navigator.userAgent")
                    cf_cookies = {
                        c["name"]: c["value"]
                        for c in all_cookies
                        if "ddg-pharmfac" in c.get("domain", "")
                    }

                    session_data = {
                        "cookies": cf_cookies,
                        "user_agent": user_agent,
                    }
                    save_cookies(cf_cookies, user_agent)

                    st.success(f"Cloudflare bypassed! Got: {list(cf_cookies.keys())}")

                    # Display session info
                    st.subheader("Session Info (for JS)")
                    st.code(json.dumps(session_data, indent=2), language="json")

                    # Send email
                    with st.spinner("Sending email..."):
                        send_email(session_data)
                        st.success(f"Email sent to {recipient_email}")

if st.button("📋 Check Existing Cookies"):
    data = load_cookies()
    if data:
        st.json(data)
        st.info(f"UA: {data.get('user_agent', 'N/A')}")
    else:
        st.warning("No cookies found. Click solve first.")
