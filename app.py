import sqlite3
import streamlit as st

DB_FILE = "verinews_v2.db"

st.set_page_config(page_title="VeriNews - Local Rumor Checker", page_icon="🛡️", layout="wide")

def init_db():
    """Initializes a completely fresh database file to bypass frozen server caches."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rumors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            true_votes INTEGER DEFAULT 0,
            fake_votes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Unverified ⏳',
            proof_link TEXT,
            creator_ip TEXT DEFAULT 'SYSTEM',
            maps_link TEXT,
            location_hub TEXT DEFAULT 'mumbai'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rumor_id INTEGER NOT NULL,
            user_ip TEXT NOT NULL,
            vote_type TEXT NOT NULL,
            UNIQUE(rumor_id, user_ip)
        )
    ''')
    cursor.execute("SELECT COUNT(*) FROM rumors")
    if cursor.fetchone() == 0:
        mock_data = [
            ("Water Supply Maintenance Alert", "Forward claiming water supply will be completely cut off this weekend due to pipeline maintenance work.", 12, 2, "Verified True ✅", "https://example-municipal-corp.gov", "SYSTEM", "https://google.com", "mumbai"),
            ("Emergency Bank Closure Rumor", "Viral message stating all local banks are closing for 5 consecutive working days starting tomorrow.", 1, 18, "Confirmed Fake ❌", "https://example-reserve-bank.org", "SYSTEM", "", "delhi"),
            ("Traffic Diversion near Main Highway", "Posts claiming the main flyover is shut down tonight due to urgent road repairs.", 2, 1, "Unverified ⏳", "", "SYSTEM", "https://google.com", "bangalore")
        ]
        cursor.executemany('''
            INSERT INTO rumors (title, content, true_votes, fake_votes, status, proof_link, creator_ip, maps_link, location_hub)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', mock_data)
    conn.commit()
    conn.close()

def get_user_session_id():
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    ctx = get_script_run_ctx()
    return str(ctx.session_id) if ctx is not None else "UNKNOWN_USER"

def get_user_vote_type(rumor_id, user_ip):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT vote_type FROM votes_log WHERE rumor_id = ? AND user_ip = ?", (rumor_id, user_ip))
    result = cursor.fetchone()
    conn.close()
    return result if result else None

def handle_delete_click(rumor_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM rumors WHERE id = ?", (rumor_id,))
    cursor.execute("DELETE FROM votes_log WHERE rumor_id = ?", (rumor_id,))
    conn.commit()
    conn.close()
    st.toast("Post successfully deleted!")

def handle_vote_click(rumor_id, user_ip, targeted_vote_type):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    existing_vote_tuple = get_user_vote_type(rumor_id, user_ip)
    existing_vote = existing_vote_tuple if existing_vote_tuple else None
    
    if existing_vote == targeted_vote_type:
        cursor.execute("DELETE FROM votes_log WHERE rumor_id = ? AND user_ip = ?", (rumor_id, user_ip))
        if targeted_vote_type == 'true':
            cursor.execute("UPDATE rumors SET true_votes = MAX(0, true_votes - 1) WHERE id = ?", (rumor_id,))
        else:
            cursor.execute("UPDATE rumors SET fake_votes = MAX(0, fake_votes - 1) WHERE id = ?", (rumor_id,))
    else:
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
    conn.commit()
    cursor.execute("SELECT true_votes, fake_votes FROM rumors WHERE id = ?", (rumor_id,))
    row = cursor.fetchone()
    if row:
        true_v, fake_v = row
        total = true_v + fake_v
        if total >= 3:
            fake_pct = (fake_v / total) * 100
            true_pct = (true_v / total) * 100
            if fake_pct >= 66: status = "Confirmed Fake ❌"
            elif true_pct >= 66: status = "Verified True ✅"
            else: status = "Highly Disputed ⚠️"
        else:
            status = "Unverified ⏳"
        cursor.execute("UPDATE rumors SET status = ? WHERE id = ?", (status, rumor_id))
        conn.commit()
    conn.close()

init_db()
user_identity = get_user_session_id()

HUBS = ["mumbai", "delhi", "bangalore", "pune", "chennai", "kolkata", "hyderabad", "ahmedabad"]

st.title("🛡️ VeriNews — Location Proximity Index")
st.markdown("An open public platform verifying viral claims sorted dynamically by regional zones.")

st.subheader("🌍 Set Your Current Position")
selected_city = st.selectbox("Select your current operational hub city to filter proximity feed:", options=HUBS, index=0)

st.sidebar.header("📢 Report an Unverified Forward")
with st.sidebar.form(key="report_form", clear_on_submit=True):
    title = st.text_input("Rumor/Forward Headline", placeholder="e.g., Local market closed early")
    content = st.text_area("Full Forward Message Text", placeholder="Paste the viral forward claim text...")
    proof_link = st.text_input("Verification Source Link (Optional)", placeholder="https://official-update.gov")
    maps_input = st.text_input("Google Maps Location URL (Optional)", placeholder="Paste shared link from Google Maps")
    rumor_location = st.selectbox("Where is this incident taking place?", options=HUBS)
    submit_button = st.form_submit_button(label="Publish to Dashboard")

if submit_button:
    if title and content:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO rumors (title, content, proof_link, creator_ip, maps_link, location_hub) VALUES (?, ?, ?, ?, ?, ?)", (title, content, proof_link, user_identity, maps_input, rumor_location))
        conn.commit()
        conn.close()
        st.sidebar.success("Rumor successfully published to dashboard!")
        st.rerun()
    else:
        st.sidebar.error("Please fill out all required fields.")

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
cursor.execute("SELECT * FROM rumors")
all_rumors = cursor.fetchall()
conn.close()

processed_rumors = []
for rumor in all_rumors:
    r_id, r_title, r_content, r_true, r_fake, r_status, r_proof, r_creator, r_maps, r_hub = rumor
    sort_rank = 1 if r_hub == selected_city else 2
    processed_rumors.append({
        'id': r_id, 'title': r_title, 'content': r_content, 'true': r_true, 'fake': r_fake,
        'status': r_status, 'proof': r_proof, 'creator': r_creator, 'maps': r_maps, 'hub': r_hub, 'rank': sort_rank
    })

sorted_rumors = sorted(processed_rumors, key=lambda x: x['rank'])
st.write("---")
st.subheader(f"📍 Alerts Sorted for Zone: {selected_city.upper()}")

if sorted_rumors:
    for rumor in sorted_rumors:
        with st.container(border=True):
            is_owner = (rumor['creator'] == user_identity)
            
            # 🏢 TOP ROW SPLIT: Split title row into left (90% content) and right (10% actions menu)
            title_col, menu_col = st.columns([9, 1])
            
            with title_col:
                if is_owner: st.caption("📝 *You posted this report*")
                zone_tag = "🔥 Active Local Area Update" if rumor['hub'] == selected_city else f"📍 Regional Update ({rumor['hub'].upper()})"
                st.markdown(f"### {rumor['title']} <span style='font-size:14px; color:gray;'>[{zone_tag}]</span>", unsafe_allow_html=True)
            
            with menu_col:
                # 💬 The Options Dropdown: Renders an elegant vertical options anchor
                with st.popover("⋮", help="Post Options"):
                    st.button("🗑️ Delete Post", key=f"del_{rumor['id']}", type="secondary", on_click=handle_delete_click, args=(rumor['id'],), use_container_width=True)
            
            st.markdown(f"**Status Evaluation:** `{rumor['status']}`")
            st.write(rumor['content'])
            if rumor['proof']: st.markdown(f"[🔗 View Attached Verification Evidence]({rumor['proof']})")
            if rumor['maps']: st.markdown(f"[🗺️ Open Location in Google Maps]({rumor['maps']})")
            st.write(f"🟢 **True Votes:** {rumor['true']} | 🔴 **Fake Votes:** {rumor['fake']}")
            
            current_vote_tuple = get_user_vote_type(rumor['id'], user_identity)
            current_vote = current_vote_tuple if current_vote_tuple else None
            true_label = "Undo Vote True ↩️" if current_vote == 'true' else "Vote True 👍"
            fake_label = "Undo Vote Fake ↩️" if current_vote == 'fake' else "Vote Fake 👎"
            
            # Action controls
            st.button(true_label, key=f"t_{rumor['id']}", type="primary" if current_vote == 'true' else "secondary", on_click=handle_vote_click, args=(rumor['id'], user_identity, 'true'))
            st.button(fake_label, key=f"f_{rumor['id']}", type="primary" if current_vote == 'fake' else "secondary", on_click=handle_vote_click, args=(rumor['id'], user_identity, 'fake'))
            
