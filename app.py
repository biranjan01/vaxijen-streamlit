import streamlit as st
import json
import subprocess
import sys
import re

st.set_page_config(page_title="VaxiJen API", page_icon="🧬", layout="wide")

@st.cache_resource
def install_camoufox():
    subprocess.check_call([sys.executable, "-m", "camoufox", "fetch"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

with st.spinner("Installing Camoufox (first run only)..."):
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
        cookie_str = "; ".join(f"{k}={v}" for k, v in cf_cookies.items())

    headers = {
        "User-Agent": user_agent,
        "Cookie": cookie_str,
        "Accept": "text/html",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    with httpx.Client(timeout=60, follow_redirects=True, headers=headers) as client:
        resp = client.post(SCRIPT_URL, data={
            "seq": sequence, "Target": target,
            "threshold": str(threshold), "submit": "Submit",
        })
        if "Overall Prediction" not in resp.text:
            return None, None, "Unexpected response"

        prediction = score = None
        for line in resp.text.split("\n"):
            if "Overall Prediction" in line:
                m = re.search(r"=\s*<?b?>?\s*([\d.]+)", line)
                if m: score = float(m.group(1))
                upper = line.upper()
                if "NON-ANTIGEN" in upper: prediction = "Non-antigen"
                elif "ANTIGEN" in upper: prediction = "Probable ANTIGEN"
                break
        return prediction, score, None

# Check URL query params (for JS integration)
params = st.query_params
auto_seq = params.get("seq", "")
auto_target = params.get("target", "bacteria")
auto_threshold = float(params.get("threshold", "0.5"))

# Auto-predict if seq param is provided (JS integration mode)
if auto_seq:
    st.title("🧬 VaxiJen API")
    with st.spinner(f"Predicting for sequence ({len(auto_seq)} chars)..."):
        prediction, score, error = predict_with_camoufox(auto_seq, auto_target, auto_threshold)

    if error:
        st.json({"success": False, "error": error})
    else:
        result = {
            "success": True,
            "sequence": auto_seq[:50] + "..." if len(auto_seq) > 50 else auto_seq,
            "target": auto_target,
            "prediction": prediction,
            "score": score,
        }
        st.json(result)
        st.success(f"Result: {prediction} (score: {score})")
else:
    # Manual UI mode
    st.title("🧬 VaxiJen Vaccine Candidate Predictor")

    sequence = st.text_area("Protein Sequence", value="MALWMRLLPLLALLALWGPDPAAAFVNQHLCGSHLVEALYLVCGERGFFYTPK", height=100)
    col1, col2 = st.columns(2)
    with col1:
        target = st.selectbox("Target Organism", TARGETS, index=TARGETS.index(auto_target) if auto_target in TARGETS else 0)
    with col2:
        threshold = st.number_input("Threshold", value=auto_threshold, min_value=0.0, max_value=1.0, step=0.1)

    if st.button("🧬 Predict", type="primary"):
        with st.spinner("Running prediction..."):
            prediction, score, error = predict_with_camoufox(sequence, target, threshold)
        if error:
            st.error(error)
        else:
            c1, c2 = st.columns(2)
            with c1: st.metric("Prediction", prediction)
            with c2: st.metric("Score", f"{score:.4f}" if score else "N/A")
