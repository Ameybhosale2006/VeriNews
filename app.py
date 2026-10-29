import sqlite3
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

DB_FILE = "verinews.db"

# Page layout configurations
st.set_page_config(page_title="VeriNews - Local Rumor Checker", page_icon="🛡️", layout="wide")

def init_db():
    """Creates the SQLite database tables and populates mock sample data if empty."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Main rumors table (Added creator_ip column to track authorship)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rumors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            pincode INTEGER NOT NULL,
            true_votes INTEGER DEFAULT 0,
            fake_votes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Unverified ⏳',
            proof_link TEXT,
            creator_ip TEXT DEFAULT 'SYSTEM'
        )
    ''')
    
    # 2. Votes tracker log table (Tracks exact vote type to allow dynamic toggle/undo)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rumor_id INTEGER NOT NULL,
            user_ip TEXT NOT NULL,
            vote_type TEXT NOT NULL,
            UNIQUE(rumor_id, user_ip)
        )
    ''')
    
    # Pre-seed realistic example neighborhood rumors if database is empty
    cursor.execute("SELECT COUNT(*) FROM rumors")
    if cursor.fetchone()[0] == 0:
        mock_data = [
            ("Water Supply Maintenance Alert", "Forward claiming water supply will be completely cut off this weekend due to pipeline maintenance work.", 400001, 12, 2, "Verified True ✅", "https://example-municipal-corp.gov", "SYSTEM"),
            ("Emergency Bank Closure Rumor", "Viral message stating all local banks are closing for 5 consecutive working days starting tomorrow. Panic buying reported.", 400025, 1, 18, "Confirmed Fake ❌", "https://example-reserve-bank.org", "SYSTEM"),
            ("Traffic Diversion near Main Highway", "Posts claiming the main flyover is shut down tonight due to urgent road repairs. Commuters advised to take alternate routes.", 400001, 2, 1, "Unverified ⏳", "", "SYSTEM")
        ]
        cursor.executemany('''
            INSERT INTO rumors (title, content, pincode, true_votes, fake_votes, status, proof_link, creator_ip)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', mock_data)
        
    conn.commit()
    conn.close()

def get_user_session_id():
    """Retrieves a completely stable, unique connection signature for the active user tab."""
    ctx = get_script_run_ctx()
    if ctx is not None:
        return str(ctx.session_id)
    return "UNKNOWN_USER"

def get_user_vote_type(rumor_id, user_ip):
    """Returns the type of vote cast by the user ('true', 'fake', or None)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT vote_type FROM votes_log WHERE rumor_id = ? AND user_ip = ?", (rumor_id, user_ip))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def delete_rumor(rumor_id, user_ip):
    """Deletes a rumor post if the current user is the original creator."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT creator_ip FROM rumors WHERE id = ?", (rumor_id,))
    row = cursor.fetchone()
    if row and row[0] == user_ip:
        cursor.execute("DELETE FROM rumors WHERE id = ?", (rumor_id,))
        cursor.execute("DELETE FROM votes_log WHERE rumor_id = ?", (rumor_id,))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def toggle_vote(rumor_id, user_ip, targeted_vote_type):
    """Handles adding a new vote, changing a vote, or retracting (undoing) an existing vote."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    existing_vote = get_user_vote_type(rumor_id, user_ip)
    
    if existing_vote == targeted_vote_type:
        # ---- UNDO LOGIC ----
        cursor.execute("DELETE FROM votes_log WHERE rumor_id = ? AND user_ip = ?", (rumor_id, user_ip))
        if targeted_vote_type == 'true':
            cursor.execute("UPDATE rumors SET true_votes = MAX(0, true_votes - 1) WHERE id = ?", (rumor_id,))
        else:
            cursor.execute("UPDATE rumors SET fake_votes = MAX(0, fake_votes - 1) WHERE id = ?", (rumor_id,))
        toast_msg = "Your vote has been removed."
    else:
        # ---- NEW VOTE OR CHANGE VOTE LOGIC ----
        if existing_vote is not None:
            if existing_vote == 'true':
                cursor.execute("UPDATE rumors SET true_votes = MAX(0, true_votes - 1) WHERE id = ?", (rumor_id,))
            else:
                cursor.execute("UPDATE rumors SET fake_votes = MAX(0, fake_votes - 1) WHERE id = ?", (rumor_id,))
            cursor.execute("UPDATE votes_log SET vote_type = ? WHERE rumor_id = ? AND user_ip = ?", (targeted_vote_type, rumor_id, user_ip))
        else:
            cursor.execute("INSERT INTO votes_log (rumor_id, user_ip, vote_type) VALUES (?, ?, ?)", (rumor_id, user_ip, targeted_vote_type))
            
        if targeted_vote_type == 'true':
            cursor.execute("UPDATE rumors SET true_votes = true_votes + 1 WHERE id = ?", (rumor_id,))
        else:
            cursor.execute("UPDATE rumors SET fake_votes = fake_votes + 1 WHERE id = ?", (rumor_id,))
        toast_msg = f"Logged as {targeted_vote_type.upper()}."

    conn.commit()
    
    # ---- RECALCULATE VERIFICATION STATUS ----
    cursor.execute("SELECT true_votes, fake_votes FROM rumors WHERE id = ?", (rumor_id,))
    row = cursor.fetchone()
    if row:
        true_v, fake_v = row[0], row[1]
        total = true_v + fake_v
        
        if total >= 3:
            fake_pct = (fake_v / total) * 100
            true_pct = (true_v / total) * 100
            
            if fake_pct >= 66:
                status = "Confirmed Fake ❌"
            elif true_pct >= 66:
                status = "Verified True ✅"
            else:
                status = "Highly Disputed ⚠️"
        else:
            status = "Unverified ⏳"
            
        cursor.execute("UPDATE rumors SET status = ? WHERE id = ?", (status, rumor_id))
        conn.commit()
        
    conn.close()
    return toast_msg

# Initialize database at startup
init_db()
user_identity = get_user_session_id()

# ---- APPLICATION USER INTERFACE ----
st.title("🛡️ VeriNews — Hyper-Local Rumor Verification Index")
st.markdown("An open public space to flag viral forwards and confirm neighborhood safety reports.")

# Sidebar Configuration for reporting new rumors
st.sidebar.header("📢 Report an Unverified Forward")
with st.sidebar.form(key="report_form", clear_on_submit=True):
    title = st.text_input("Rumor/Forward Headline", placeholder="e.g., Water cuts expected tomorrow")
    content = st.text_area("Full Forward Message Text", placeholder="Paste the viral claim here...")
    pincode = st.number_input("Target Area Pincode", min_value=100000, max_value=999999, step=1, value=400001)
    proof_link = st.text_input("Verification Source Link (Optional)", placeholder="https://official-government-update.com")
    submit_button = st.form_submit_button(label="Publish to Dashboard")

if submit_button:
    if title and content and pincode:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO rumors (title, content, pincode, proof_link, creator_ip) VALUES (?, ?, ?, ?, ?)",
            (title, content, pincode, proof_link, user_identity)
        )
        conn.commit()
        conn.close()
        st.sidebar.success("Rumor broadcast successfully posted!")
        st.rerun()
    else:
        st.sidebar.error("Please fill out all required fields.")

# Main Dashboard Feed Filters
st.subheader("📍 Neighborhood Alerts")
pincode_filter = st.text_input("Filter feed by entering your 6-digit Pincode:", placeholder="Leave blank to view all regions")

# Fetch data based on the pincode search query
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
if pincode_filter.strip():
    cursor.execute("SELECT * FROM rumors WHERE pincode = ? ORDER BY id DESC", (pincode_filter.strip(),))
else:
    cursor.execute("SELECT * FROM rumors ORDER BY id DESC")
rumors = cursor.fetchall()
conn.close()

# Render items dynamically
if rumors:
    for rumor in rumors:
        r_id, r_title, r_content, r_pincode, r_true, r_fake, r_status, r_proof, r_creator = rumor
        
        with st.container():
            st.markdown("---")
            if r_creator == user_identity:
                st.caption("📝 *You posted this report*")
                
            st.markdown(f"### {r_title}")
            st.markdown(f"**📍 Pincode Location Target:** {r_pincode} | **Status Evaluation:** `{r_status}`")
            st.write(r_content)
            
            if r_proof:
                st.markdown(f"[🔗 View Attached Verification Evidence]({r_proof})")
                
            st.write(f"🟢 **True Votes:** {r_true} | 🔴 **Fake Votes:** {r_fake}")
            
            current_vote = get_user_vote_type(r_id, user_identity)
            true_label = "Undo Vote True ↩️" if current_vote == 'true' else "Vote True 👍"
            fake_label = "Undo Vote Fake ↩️" if current_vote == 'fake' else "Vote Fake 👎"
            
            # Action controls
            if st.button(true_label, key=f"t_{r_id}", type="primary" if current_vote == 'true' else "secondary"):
                msg = toggle_vote(r_id, user_identity, 'true')
                st.toast(msg)
                st.rerun()
                
            if st.button(fake_label, key=f"f_{r_id}", type="primary" if current_vote == 'fake' else "secondary"):
                msg = toggle_vote(r_id, user_identity, 'fake')
                st.toast(msg)
                st.rerun()
                
            if r_creator == user_identity:
