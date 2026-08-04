import streamlit as st
import json
import subprocess
import sys
import re

st.set_page_config(page_title="VaxiJen API", page_icon="🧬")

@st.cache_resource
def install_camoufox():
    subprocess.check_call([sys.executable, "-m", "camoufox", "fetch"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

st.title("🧬 VaxiJen Vaccine Candidate Predictor")

with st.spinner("Installing Camoufox browser (first run only)..."):
    install_camoufox()

TARGETS = ["bacteria", "virus", "tumour", "parasite", "fungal"]
SCRIPT_URL = "https://www.ddg-pharmfac.net/vaxijen/scripts/VaxiJen_scripts/VaxiJen3.pl"

def predict_with_camoufox(sequence, target, threshold):
    from camoufox.sync_api import Camoufox
    import httpx
    import time

    with Camoufox(headless="virtual", humanize=True) as browser:
        page = browser.new_page()
        page.goto(
            "https://www.ddg-pharmfac.net/vaxijen/VaxiJen/VaxiJen.html",
            wait_until="networkidle",
            timeout=90000,
        )

        title = page.title()
        if "Just a moment" in title:
            for _ in range(30):
                time.sleep(2)
                title = page.title()
                if "Just a moment" not in title:
                    break

        if "Just a moment" in title:
            return None, None, "Cloudflare blocked"

        all_cookies = page.context.cookies()
        user_agent = page.evaluate("navigator.userAgent")
        cf_cookies = {c["name"]: c["value"] for c in all_cookies if "ddg-pharmfac" in c.get("domain", "")}

        # Close browser, use httpx with same IP
        cookie_str = "; ".join(f"{k}={v}" for k, v in cf_cookies.items())

    # Use httpx with same IP (cookies + IP match)
    import httpx as hx
    headers = {
        "User-Agent": user_agent,
        "Cookie": cookie_str,
        "Accept": "text/html",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    with hx.Client(timeout=60, follow_redirects=True, headers=headers) as client:
        resp = client.post(SCRIPT_URL, data={
            "seq": sequence,
            "Target": target,
            "threshold": str(threshold),
            "submit": "Submit",
        })

        if "Overall Prediction" not in resp.text:
            return None, None, "Unexpected response"

        prediction = score = None
        for line in resp.text.split("\n"):
            if "Overall Prediction" in line:
                m = re.search(r"=\s*<?b?>?\s*([\d.]+)", line)
                if m:
                    score = float(m.group(1))
                upper = line.upper()
                if "NON-ANTIGEN" in upper:
                    prediction = "Non-antigen"
                elif "ANTIGEN" in upper:
                    prediction = "Probable ANTIGEN"
                break

        return prediction, score, None

# UI
sequence = st.text_area("Protein Sequence", value="MALWMRLLPLLALLALWGPDPAAAFVNQHLCGSHLVEALYLVCGERGFFYTPK", height=100)
col1, col2 = st.columns(2)
with col1:
    target = st.selectbox("Target Organism", TARGETS)
with col2:
    threshold = st.number_input("Threshold", value=0.5, min_value=0.0, max_value=1.0, step=0.1)

if st.button("🧬 Predict", type="primary"):
    with st.spinner("Solving Cloudflare + running prediction..."):
        prediction, score, error = predict_with_camoufox(sequence, target, threshold)

    if error:
        st.error(error)
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Prediction", prediction)
        with col2:
            st.metric("Score", f"{score:.4f}" if score else "N/A")

        st.success(f"Target: {target} | Threshold: {threshold}")
