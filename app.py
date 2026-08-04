import streamlit as st
import json
import subprocess
import sys
import re
import csv
import io
import time
import pandas as pd

st.set_page_config(page_title="VaxiJen Batch API", page_icon="🧬", layout="wide")

@st.cache_resource
def install_camoufox():
    subprocess.check_call([sys.executable, "-m", "camoufox", "fetch"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

with st.spinner("Installing Camoufox (first run only)..."):
    install_camoufox()

TARGETS = ["bacteria", "virus", "tumour", "parasite", "fungal"]
SCRIPT_URL = "https://www.ddg-pharmfac.net/vaxijen/scripts/VaxiJen_scripts/VaxiJen3.pl"


def get_cloudflare_session():
    from camoufox.sync_api import Camoufox
    import httpx

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
            return None

        all_cookies = page.context.cookies()
        user_agent = page.evaluate("navigator.userAgent")
        cf_cookies = {c["name"]: c["value"] for c in all_cookies if "ddg-pharmfac" in c.get("domain", "")}

    cookie_str = "; ".join(f"{k}={v}" for k, v in cf_cookies.items())
    return {
        "headers": {
            "User-Agent": user_agent,
            "Cookie": cookie_str,
            "Accept": "text/html",
            "Content-Type": "application/x-www-form-urlencoded",
        }
    }


def predict_single(client, sequence, target, threshold):
    resp = client.post(SCRIPT_URL, data={
        "seq": sequence,
        "Target": target,
        "threshold": str(threshold),
        "submit": "Submit",
    })
    if "Overall Prediction" not in resp.text:
        return None, None

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
    return prediction, score


def predict_with_camoufox(sequence, target, threshold):
    from camoufox.sync_api import Camoufox
    import httpx

    session = get_cloudflare_session()
    if not session:
        return None, None, "Cloudflare blocked"

    with httpx.Client(timeout=60, follow_redirects=True, headers=session["headers"]) as client:
        prediction, score = predict_single(client, sequence, target, threshold)
        if prediction is None:
            return None, None, "Unexpected response"
        return prediction, score, None


# --- UI ---
st.title("🧬 VaxiJen Batch Predictor")

mode = st.radio("Mode", ["Single Sequence", "CSV Batch"], horizontal=True)

if mode == "Single Sequence":
    sequence = st.text_area("Protein Sequence", value="MALWMRLLPLLALLALWGPDPAAAFVNQHLCGSHLVEALYLVCGERGFFYTPK", height=100)
    col1, col2 = st.columns(2)
    with col1:
        target = st.selectbox("Target Organism", TARGETS)
    with col2:
        threshold = st.number_input("Threshold", value=0.5, min_value=0.0, max_value=1.0, step=0.1)

    if st.button("🧬 Predict", type="primary"):
        with st.spinner("Running..."):
            prediction, score, error = predict_with_camoufox(sequence, target, threshold)
        if error:
            st.error(error)
        else:
            c1, c2 = st.columns(2)
            with c1: st.metric("Prediction", prediction)
            with c2: st.metric("Score", f"{score:.4f}" if score else "N/A")

else:
    st.markdown("Upload a CSV with columns: `sequence` (required), `target` (optional, default: bacteria), `threshold` (optional, default: 0.5)")
    uploaded = st.file_uploader("Choose CSV", type="csv")

    if uploaded:
        df = pd.read_csv(uploaded)
        st.dataframe(df.head(10))
        st.info(f"{len(df)} sequences to process")

        if st.button("🚀 Run Batch Prediction", type="primary"):
            st.info("Getting Cloudflare session...")
            session = get_cloudflare_session()
            if not session:
                st.error("Cloudflare blocked")
            else:
                results = []
                progress = st.progress(0)
                status = st.empty()

                import httpx
                with httpx.Client(timeout=60, follow_redirects=True, headers=session["headers"]) as client:
                    for i, row in df.iterrows():
                        seq = str(row.get("sequence", ""))
                        tgt = str(row.get("target", "bacteria"))
                        thr = float(row.get("threshold", 0.5))

                        if not seq:
                            continue

                        status.text(f"Processing {i+1}/{len(df)}: {seq[:30]}...")
                        prediction, score = predict_single(client, seq, tgt, thr)

                        results.append({
                            "sequence": seq,
                            "target": tgt,
                            "threshold": thr,
                            "prediction": prediction,
                            "score": score,
                        })
                        progress.progress((i + 1) / len(df))
                        time.sleep(1)

                result_df = pd.DataFrame(results)
                st.dataframe(result_df)

                csv_out = result_df.to_csv(index=False)
                st.download_button("📥 Download Results CSV", csv_out, "vaxijen_results.csv", "text/csv")
                st.success(f"Done! {len(results)} sequences processed")
