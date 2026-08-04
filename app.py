import streamlit as st
import json
import subprocess
import sys

st.set_page_config(page_title="VaxiJen Session Server", page_icon="🧬")

# Install camoufox browser on first run
@st.cache_resource
def install_camoufox():
    subprocess.check_call([sys.executable, "-m", "camoufox", "fetch"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

st.title("🧬 VaxiJen Cloudflare Bypass")
st.markdown("Solves Cloudflare and shows session cookies for use in camoufox-js")

with st.spinner("Installing Camoufox browser (first run only)..."):
    install_camoufox()

if st.button("🚀 Solve Cloudflare"):
    with st.spinner("Launching Camoufox..."):
        from camoufox.sync_api import Camoufox
        import time

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
                    time.sleep(2)
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

                st.success(f"Cloudflare bypassed! Got: {list(cf_cookies.keys())}")

                st.subheader("📋 Copy this JSON → save as cookies.json")
                st.code(json.dumps(session_data, indent=2), language="json")
