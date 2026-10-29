import sqlite3
import math
import os
import streamlit as st
import streamlit.components.v1 as components
from streamlit.runtime.scriptrunner import get_script_run_ctx

DB_FILE = "verinews.db"

# 🔄 AUTOMATIC RESET TRICK: This instantly wipes the old broken database file on the server
if os.path.exists(DB_FILE):
    try:
        os.remove(DB_FILE)
    except Exception:
        pass

st.set_page_config(page_title="VeriNews - Local Rumor Checker", page_icon="🛡️", layout="wide")

def init_db():
    """Initializes the database schema cleanly without the pincode field."""
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
            latitude REAL DEFAULT 0.0,
            longitude REAL DEFAULT 0.0
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
    
    # Pre-seed sample neighborhood alerts paired with realistic coordinate mapping details
    cursor.execute("SELECT COUNT(*) FROM rumors")
    if cursor.fetchone() == 0:
        mock_data = [
            ("Water Supply Maintenance Alert", "Forward claiming water supply will be completely cut off this weekend due to pipeline maintenance work.", 12, 2, "Verified True ✅", "https://example-municipal-corp.gov", "SYSTEM", "https://google.com", 18.9220, 72.8340),
            ("Emergency Bank Closure Rumor", "Viral message stating all local banks are closing for 5 consecutive working days starting tomorrow.", 1, 18, "Confirmed Fake ❌", "https://example-reserve-bank.org", "SYSTEM", "", 19.0178, 72.8478),
            ("Traffic Diversion near Main Highway", "Posts claiming the main flyover is shut down tonight due to urgent road repairs.", 2, 1, "Unverified ⏳", "", "SYSTEM", "https://google.com", 18.9340, 72.8250)
        ]
        cursor.executemany('''
            INSERT INTO rumors (title, content, true_votes, fake_votes, status, proof_link, creator_ip, maps_link, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', mock_data)
    conn.commit()
    conn.close()

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates the straight-line physical distance between two GPS coordinates in kilometers."""
    if not lat1 or not lon1 or not lat2 or not lon2:
        return 99999.0
    R = 6371.0  # Earth's radius in KM
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def get_user_session_id():
    ctx = get_script_run_ctx()
    return str(ctx.session_id) if ctx is not None else "UNKNOWN_USER"

def get_user_vote_type(rumor_id, user_ip):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT vote_type FROM votes_log WHERE rumor_id = ? AND user_ip = ?", (rumor_id, user_ip))
    result = cursor.fetchone()
    conn.close()
    return result if result else None

def handle_delete_click(rumor_id, user_ip):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT creator_ip FROM rumors WHERE id = ?", (rumor_id,))
    row = cursor.fetchone()
    if row and row == user_ip:
        cursor.execute("DELETE FROM rumors WHERE id = ?", (rumor_id,))
        cursor.execute("DELETE FROM votes_log WHERE rumor_id = ?", (rumor_id,))
        conn.commit()
        st.toast("Post successfully deleted!")
    conn.close()

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
        true_v, fake_v = row, row
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

# ---- NATIVE BROWSER GEOLOCATION LINK COMPONENT ----
components.html("""
<script>
    navigator.geolocation.getCurrentPosition(function(position) {
        const lat = position.coords.latitude;
        const lon = position.coords.longitude;
        window.parent.postMessage({type: 'streamlit:setComponentValue', value: {lat: lat, lon: lon}}, '*');
    });
</script>
""", height=0, width=0)

if 'user_lat' not in st.session_state:
    st.session_state['user_lat'] = 19.0760 # Default center backup coordinates (Mumbai)
    st.session_state['user_lon'] = 72.8777

st.title("🛡️ VeriNews — Geo-Location Community Index")
st.markdown("An open public space to verify claims sorted instantly by proximity to your current position.")

# Sidebar Form Configuration
st.sidebar.header("📢 Report an Unverified Forward")
with st.sidebar.form(key="report_form", clear_on_submit=True):
    title = st.text_input("Rumor/Forward Headline", placeholder="e.g., Water cuts expected tomorrow")
    content = st.text_area("Full Forward Message Text", placeholder="Paste the viral claim here...")
    proof_link = st.text_input("Verification Source Link (Optional)", placeholder="https://official-government-update.com")
    maps_input = st.text_input("Google Maps Location URL (Optional)", placeholder="Paste shared link from Google Maps")
    submit_button = st.form_submit_button(label="Publish to Dashboard")

if submit_button:
    if title and content:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO rumors (title, content, proof_link, creator_ip, maps_link, latitude, longitude) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, content, proof_link, user_identity, maps_input, st.session_state['user_lat'], st.session_state['user_lon']))
        conn.commit()
        conn.close()
        st.sidebar.success("Rumor broadcast successfully posted!")
        st.rerun()
    else:
        st.sidebar.error("Please fill out all required fields.")

# Fetch records from SQLite database file
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
cursor.execute("SELECT * FROM rumors")
all_rumors = cursor.fetchall()
conn.close()

processed_rumors = []
for rumor in all_rumors:
    r_id, r_title, r_content, r_true, r_fake, r_status, r_proof, r_creator, r_maps, r_lat, r_lon = rumor
    dist = haversine_distance(st.session_state['user_lat'], st.session_state['user_lon'], r_lat, r_lon)
    processed_rumors.append({
        'id': r_id, 'title': r_title, 'content': r_content,
        'true': r_true, 'fake': r_fake, 'status': r_status, 'proof': r_proof,
        'creator': r_creator, 'maps': r_maps, 'distance': dist
    })

# Sort items dynamically based on distance metrics
sorted_rumors = sorted(processed_rumors, key=lambda x: x['distance'])

st.subheader("📍 Alerts Sorted by Nearest Proximity")
st.caption(f"🌍 Current Device Position Lock Center: `{st.session_state['user_lat']:.4f}, {st.session_state['user_lon']:.4f}`")

if sorted_rumors:
    for rumor in sorted_rumors:
        with st.container():
            st.markdown("---")
            is_owner = (rumor['creator'] == user_identity)
            if is_owner: st.caption("html📝 *You posted this report*")
            
            dist_label = f"🔥 Very Close ({rumor['distance']:.2f} km away)" if rumor['distance'] < 5 else f"📍 ({rumor['distance']:.2f} km away)"
            
            st.markdown(f"### {rumor['title']} <span style='font-size:14px; color:gray;'>{dist_label}</span>", unsafe_allow_html=True)
