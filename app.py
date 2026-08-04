import streamlit as st
import json
import subprocess
import sys
import re
import time
import pandas as pd

st.set_page_config(page_title="VaxiJen API", page_icon="🧬", layout="wide")

@st.cache_resource
def install_camoufox():
    subprocess.check_call([sys.executable, "-m", "camoufox", "fetch"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

with st.spinner("Installing Camoufox (first run only)..."):
    install_camoufox()

TARGETS = ["bacteria", "virus", "tumour", "parasite", "fungal"]
SCRIPT_URL = "https://www.ddg-pharmfac.net/vaxijen/scripts/VaxiJen_scripts/VaxiJen3.pl"

params = st.query_params
mode = params.get("mode", "")

# --- JSON API mode (for JS polling) ---
if mode == "upload" and "seqs" in params:
    import httpx
    from camoufox.sync_api import Camoufox

    sequences = json.loads(params["seqs"])
    target = params.get("target", "bacteria")
    threshold = float(params.get("threshold", "0.5"))
    job_id = params.get("job", str(int(time.time())))

    if "results" not in st.session_state:
        st.session_state.results = {}
    if job_id not in st.session_state.results:
        st.session_state.results[job_id] = {"total": len(sequences), "done": 0, "data": []}

    # Get CF session
    with Camoufox(headless="virtual", humanize=True) as browser:
        page = browser.new_page()
        page.goto("https://www.ddg-pharmfac.net/vaxijen/VaxiJen/VaxiJen.html", wait_until="networkidle", timeout=90000)
        title = page.title()
        if "Just a moment" in title:
            for _ in range(30):
                time.sleep(2)
                title = page.title()
                if "Just a moment" not in title:
                    break
        all_cookies = page.context.cookies()
        user_agent = page.evaluate("navigator.userAgent")
        cf_cookies = {c["name"]: c["value"] for c in all_cookies if "ddg-pharmfac" in c.get("domain", "")}

    cookie_str = "; ".join(f"{k}={v}" for k, v in cf_cookies.items())
    headers = {"User-Agent": user_agent, "Cookie": cookie_str, "Accept": "text/html", "Content-Type": "application/x-www-form-urlencoded"}

    with httpx.Client(timeout=60, follow_redirects=True, headers=headers) as client:
        for i, seq in enumerate(sequences):
            resp = client.post(SCRIPT_URL, data={"seq": seq, "Target": target, "threshold": str(threshold), "submit": "Submit"})
            prediction = score = None
            if "Overall Prediction" in resp.text:
                for line in resp.text.split("\n"):
                    if "Overall Prediction" in line:
                        m = re.search(r"=\s*<?b?>?\s*([\d.]+)", line)
                        if m: score = float(m.group(1))
                        upper = line.upper()
                        if "NON-ANTIGEN" in upper: prediction = "Non-antigen"
                        elif "ANTIGEN" in upper: prediction = "Probable ANTIGEN"
                        break
            st.session_state.results[job_id]["data"].append({"sequence": seq[:50], "prediction": prediction, "score": score})
            st.session_state.results[job_id]["done"] = i + 1
            time.sleep(1)

    st.session_state.results[job_id]["status"] = "complete"
    st.json(st.session_state.results[job_id])
    st.stop()

# --- Poll mode ---
if mode == "poll":
    job_id = params.get("job", "")
    if job_id and "results" in st.session_state and job_id in st.session_state.results:
        st.json(st.session_state.results[job_id])
    else:
        st.json({"error": "job not found"})
    st.stop()

# --- Normal UI mode ---
st.title("🧬 VaxiJen Batch Predictor")

upload_col, poll_col = st.columns(2)

with upload_col:
    st.subheader("Upload Sequences")
    uploaded = st.file_uploader("CSV with 'sequence' column", type="csv")
    target = st.selectbox("Target", TARGETS)
    threshold = st.number_input("Threshold", value=0.5, min_value=0.0, max_value=1.0, step=0.1)

    if uploaded:
        df = pd.read_csv(uploaded)
        st.dataframe(df.head(5))
        st.info(f"{len(df)} sequences")

        if st.button("🚀 Start Batch", type="primary"):
            job_id = str(int(time.time()))
            sequences = df["sequence"].tolist()
            st.session_state.current_job = job_id
            st.session_state.current_sequences = sequences
            st.session_state.current_target = target
            st.session_state.current_threshold = threshold
            st.session_state.processing = True

with poll_col:
    st.subheader("Job Status")

    if st.session_state.get("processing"):
        job_id = st.session_state.current_job
        sequences = st.session_state.current_sequences
        target = st.session_state.current_target
        threshold = st.session_state.current_threshold

        if "results" not in st.session_state:
            st.session_state.results = {}
        st.session_state.results[job_id] = {"total": len(sequences), "done": 0, "data": [], "status": "running"}

        st.info(f"Job: `{job_id}`")
        st.code(f"Poll URL: ?mode=poll&job={job_id}", language=None)

        import httpx
        from camoufox.sync_api import Camoufox

        progress = st.progress(0)
        status = st.empty()

        with Camoufox(headless="virtual", humanize=True) as browser:
            page = browser.new_page()
            page.goto("https://www.ddg-pharmfac.net/vaxijen/VaxiJen/VaxiJen.html", wait_until="networkidle", timeout=90000)
            title = page.title()
            if "Just a moment" in title:
                for _ in range(30):
                    time.sleep(2)
                    title = page.title()
                    if "Just a moment" not in title:
                        break
            all_cookies = page.context.cookies()
            user_agent = page.evaluate("navigator.userAgent")
            cf_cookies = {c["name"]: c["value"] for c in all_cookies if "ddg-pharmfac" in c.get("domain", "")}

        cookie_str = "; ".join(f"{k}={v}" for k, v in cf_cookies.items())
        headers = {"User-Agent": user_agent, "Cookie": cookie_str, "Accept": "text/html", "Content-Type": "application/x-www-form-urlencoded"}

        with httpx.Client(timeout=60, follow_redirects=True, headers=headers) as client:
            for i, seq in enumerate(sequences):
                status.text(f"Processing {i+1}/{len(sequences)}: {seq[:30]}...")
                resp = client.post(SCRIPT_URL, data={"seq": seq, "Target": target, "threshold": str(threshold), "submit": "Submit"})
                prediction = score = None
                if "Overall Prediction" in resp.text:
                    for line in resp.text.split("\n"):
                        if "Overall Prediction" in line:
                            m = re.search(r"=\s*<?b?>?\s*([\d.]+)", line)
                            if m: score = float(m.group(1))
                            upper = line.upper()
                            if "NON-ANTIGEN" in upper: prediction = "Non-antigen"
                            elif "ANTIGEN" in upper: prediction = "Probable ANTIGEN"
                            break
                st.session_state.results[job_id]["data"].append({"sequence": seq[:50], "prediction": prediction, "score": score})
                st.session_state.results[job_id]["done"] = i + 1
                progress.progress((i + 1) / len(sequences))
                time.sleep(1)

        st.session_state.results[job_id]["status"] = "complete"
        st.session_state.processing = False

        result_df = pd.DataFrame(st.session_state.results[job_id]["data"])
        st.dataframe(result_df)
        st.download_button("📥 Download Results", result_df.to_csv(index=False), "vaxijen_results.csv", "text/csv")
        st.success("Done!")
    else:
        st.info("Upload CSV and click Start Batch")

        job_id = st.text_input("Or enter Job ID to check:", "")
        if job_id and "results" in st.session_state and job_id in st.session_state.results:
            job = st.session_state.results[job_id]
            st.metric("Progress", f"{job['done']}/{job['total']}")
            if job["data"]:
                st.dataframe(pd.DataFrame(job["data"]))
