import streamlit as st
import pandas as pd
from rectpack import newPacker
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import io
import math
from matplotlib.backends.backend_pdf import PdfPages

# --- PAGE CONFIG & S&C ASIA BRANDING ---
st.set_page_config(layout="wide", page_title="S&C Asia | Production Optimizer", page_icon="logo.png")

try:
    st.sidebar.image("logo.png", use_container_width=True)
except FileNotFoundError:
    pass 

st.title("S&C Asia | Production Optimizer")
st.markdown("**First to Innovative Interior** — Premium Solid Surface Cutting & Yield Management")
st.markdown("---")

# --- CORE OPTIMIZATION ENGINE ---
SPLIT_STRATEGIES = [
    [0.5, 0.5], [0.6, 0.4], [0.7, 0.3], [0.8, 0.2], [0.9, 0.1], [0.95, 0.05], [0.98, 0.02],
    [0.34, 0.33, 0.33], [0.4, 0.4, 0.2], [0.5, 0.3, 0.2], [0.6, 0.2, 0.2],
    [0.7, 0.15, 0.15], [0.8, 0.1, 0.1], [0.9, 0.05, 0.05]
]

def generate_fragments(w, h, strategy_ratios):
    is_w_long = w >= h
    long_side = w if is_w_long else h
    short_side = h if is_w_long else w

    frags = []
    current_offset = 0
    for ratio in strategy_ratios[:-1]:
        length = math.floor(long_side * ratio)
        frags.append({"l": length, "offset": current_offset})
        current_offset += length
    frags.append({"l": long_side - current_offset, "offset": current_offset})

    res = []
    for f in frags:
        if is_w_long:
            res.append({"w": f['l'], "h": short_side, "x": f['offset'], "y": 0})
        else:
            res.append({"w": short_side, "h": f['l'], "x": 0, "y": f['offset']})
    return res

def split_virtual_board(vw, vh, strategy, max_w, max_h, kerf):
    if strategy == [1.0]:
        return [{'w': vw, 'h': vh, 'x': 0, 'y': 0, 'orig_w': vw, 'orig_h': vh}]

    frags = generate_fragments(vw, vh, strategy)
    donor_blocks = []
    for f in frags:
        # EXACT dimensions mapped (no extra buffer)
        dw = min(f['w'], max_w - kerf)
        dh = min(f['h'], max_h - kerf)
        donor_blocks.append({'w': dw, 'h': dh, 'x': f['x'], 'y': f['y'], 'orig_w': f['w'], 'orig_h': f['h']})
    return donor_blocks

def piece_fits_slab(f, limit_w, limit_h, strict_grain=False):
    if strict_grain:
        return f['w'] <= limit_w and f['h'] <= limit_h
    return (f['w'] <= limit_w and f['h'] <= limit_h) or (f['h'] <= limit_w and f['w'] <= limit_h)

def get_oriented_limits(w, h, limit_a, limit_b, strict_grain=False):
    if strict_grain:
        return limit_a, limit_b
        
    max_limit, min_limit = max(limit_a, limit_b), min(limit_a, limit_b)
    if w >= h:
        return max_limit, min_limit
    else:
        return min_limit, max_limit

def get_mandatory_fragments(w, h, limit_w, limit_h):
    frags = []
    curr_x, curr_y = 0, 0
    rem_w, rem_h = w, h

    while rem_w > 0:
        cut_w = min(rem_w, limit_w)
        rem_h = h
        curr_y = 0
        while rem_h > 0:
            cut_h = min(rem_h, limit_h)
            frags.append({'w': cut_w, 'h': cut_h, 'x': curr_x, 'y': curr_y})
            curr_y += cut_h
            rem_h -= cut_h
        curr_x += cut_w
        rem_w -= cut_w
    return frags

def can_pack(rects_to_pack, num_slabs, sheet_w, sheet_h, kerf, strict_grain=False):
    p = newPacker(rotation=not strict_grain)
    p.add_bin(sheet_w, sheet_h, count=num_slabs)
    for r in rects_to_pack:
        p.add_rect(r['w'] + kerf, r['h'] + kerf, rid=r['rid'])
    p.pack()
    return p, len(p.rect_list()) == len(rects_to_pack)

# --- MULTI-COLOR SMART LABELING ---
def draw_multiline_text(ax, cx, cy, lines, colors, fs, rot, rect_patch, act_w, act_h):
    line_height_ratio = 0.25 
    num_lines = len(lines)
    
    for i, (text, color) in enumerate(zip(lines, colors)):
        if rot == 0:
            offset_y = (act_h * line_height_ratio) * ( (num_lines - 1) / 2.0 - i )
            offset_x = 0
        else:
            offset_x = (act_w * line_height_ratio) * ( (num_lines - 1) / 2.0 - i )
            offset_y = 0

        t = ax.text(cx + offset_x, cy + offset_y, text, color=color, weight='bold', ha='center', va='center', fontsize=fs, rotation=rot, clip_on=True)
        t.set_clip_path(rect_patch)

def draw_smart_label(ax, room_name, part_type, w_label, h_label, rx, ry, act_w, act_h, rect_patch, tag=""):
    cx = rx + act_w / 2
    cy = ry + act_h / 2
    
    if pd.isna(room_name) or str(room_name).strip().lower() in ['nan', 'none', '']:
        room_name = "Unassigned"
        
    room_str = str(room_name).strip()
    is_wide = act_w >= act_h
    tag_text = f"#{tag}" if tag else ""

    if act_w <= 12 or act_h <= 12:
        return

    if act_w <= 80 and act_h <= 80:
        if tag_text:
            t = ax.text(cx, cy, tag_text, color='black', weight='bold', ha='center', va='center', fontsize=5, clip_on=True)
            t.set_clip_path(rect_patch)
        return

    lines, colors = [], []
    fs, rot = 4, 0

    if act_w >= 220 and act_h >= 120:
        if tag_text:
            t_badge = ax.text(rx + 15, cy, tag_text, color='#cc0000', weight='bold', ha='left', va='center', fontsize=10, clip_on=True)
            t_badge.set_clip_path(rect_patch)
            
        lines = [f"[{room_str}]", f"{part_type}", f"{w_label}x{h_label}"]
        colors = ['#cc0000', 'black', 'black']
        rot = 0
        fs = 6
    elif is_wide:
        display_room = room_str[:5] + ".." if len(room_str) > 5 else room_str
        if act_h >= 50:
            lines = [f"{tag_text} [{display_room}] {part_type}", f"{w_label}x{h_label}"]
            colors = ['#cc0000', 'black']
            fs = 4.5
        elif act_h >= 25:
            if act_w >= 100:
                lines = [f"{tag_text} {w_label}x{h_label}"]
                colors = ['black']
                fs = 4
            else:
                lines = [tag_text]
                colors = ['black']
                fs = 4
        else:
            lines = [tag_text]
            colors = ['black']
            fs = 3.5
        rot = 0
    else:
        display_room = room_str[:5] + ".." if len(room_str) > 5 else room_str
        if act_w >= 50:
            lines = [f"{tag_text} [{display_room}] {part_type}", f"{w_label}x{h_label}"]
            colors = ['#cc0000', 'black']
            fs = 4.5
        elif act_w >= 25:
            if act_h >= 100:
                lines = [f"{tag_text} {w_label}x{h_label}"]
                colors = ['black']
                fs = 4
            else:
                lines = [tag_text]
                colors = ['black']
                fs = 4
        else:
            lines = [tag_text]
            colors = ['black']
            fs = 3.5
        rot = 90
        
    if lines:
        draw_multiline_text(ax, cx, cy, lines, colors, fs, rot, rect_patch, act_w, act_h)

# --- SIDEBAR SETTINGS ---
st.sidebar.header("1. Material Settings")
sheet_w = st.sidebar.number_input("Slab Width (mm)", value=3680)
sheet_h = st.sidebar.number_input("Slab Height (mm)", value=760)
kerf = st.sidebar.number_input("Blade Kerf (mm)", value=3)

st.sidebar.markdown("---")
st.sidebar.header("2. Optimization Rules")

strict_grain = st.sidebar.checkbox(
    "Veined Material (Strict Grain Match)", 
    value=False, 
    help="Prevents ANY rotation of pieces. Essential for marble/veined colors so grain strictly follows the length."
)
st.sidebar.markdown("<br>", unsafe_allow_html=True)

enable_site_limit = st.sidebar.checkbox(
    "Enable Elevator/Site Limit", 
    value=False, 
    help="Force a cut if a piece exceeds a certain length or width."
)
if enable_site_limit:
    site_limit_l = st.sidebar.number_input("Elevator Max Length (mm)", value=2400)
    site_limit_w = st.sidebar.number_input("Elevator Max Width (mm)", value=1200)
else:
    site_limit_l = None
    site_limit_w = None

st.sidebar.markdown("<br>", unsafe_allow_html=True)
is_seamless = st.sidebar.checkbox(
    "Enable Double-Step Recycled Nesting", 
    value=True, 
    help="Groups scrap into 'Donor Blocks' that are glued into 'Recycled Boards' before final cutting. Maximizes labor efficiency."
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Visual Key")
st.sidebar.markdown("🟦 **Blue:** Clean Solid Cut")
st.sidebar.markdown("🟪 **Purple:** Site Joint (Elevator)")
st.sidebar.markdown("🟧 **Orange:** Factory Joint (Oversized)")
st.sidebar.markdown("🟩 **Green Dotted:** Donor Block (Double Step Recycle)")
st.sidebar.markdown("⬜ **Gray:** Dead Waste")


# --- UI: PROJECT SETUP & TABS ---
if 'parts' not in st.session_state: 
    st.session_state.parts = []

st.subheader("📁 Project Setup")
project_name = st.text_input("Master Project Name", value="Amari Hotel Project")

tab_manual, tab_excel = st.tabs(["🛠️ Manual Input (Organized)", "📥 Excel Import"])

with tab_manual:
    st.markdown("Batch-add parts to multiple rooms instantly.")
    c_pref, c_start, c_units = st.columns([2, 1.5, 1.5])
    room_prefix = c_pref.text_input("Room Name / Prefix", value="", placeholder="e.g., 'Unit ', 'Lobby'")
    enable_auto_num = c_start.checkbox("Auto-Number Rooms", value=True)
    start_num = c_start.number_input("Starting Number", value=101, step=1, disabled=not enable_auto_num)
    num_units = c_units.number_input("Total Rooms to Add", value=15, min_value=1, max_value=1000)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    c_type, c1, c2, c3, c4 = st.columns([1.5, 1.5, 1.5, 1.5, 2])
    part_type = c_type.selectbox("Part Category", ["Top", "Apron", "Splash", "Skirting", "Other"])
    w = c1.number_input("Width (mm)", value=1970, min_value=1)
    h = c2.number_input("Height (mm)", value=220, min_value=1)
    q_per_unit = c3.number_input("Qty per Room", value=1, min_value=1)
    
    c4.markdown("<br>", unsafe_allow_html=True) 
    if c4.button("➕ Batch Add to List", use_container_width=True):
        for i in range(int(num_units)):
            if enable_auto_num:
                current_room_num = int(start_num) + i
                room_str = f"{room_prefix}{current_room_num}" if room_prefix else str(current_room_num)
            else:
                room_str = room_prefix if room_prefix else "Unassigned"
                
            st.session_state.parts.append({
                "room": room_str,
                "type": part_type,
                "w": int(w), 
                "h": int(h), 
                "q": int(q_per_unit)
            })
        st.rerun()

with tab_excel:
    uploaded_file = st.file_uploader("Upload Cut List (.xlsx)", type=["xlsx", "xls"])
    if uploaded_file is not None:
        try:
            df = pd.read_excel(uploaded_file)
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            room_col = next((c for c in df.columns if any(k in c for k in ['room', 'set', 'area'])), None)
            type_col = next((c for c in df.columns if any(k in c for k in ['type', 'part', 'category'])), None)
            w_col = next((c for c in df.columns if any(k in c for k in ['width', 'wid', 'w', 'len'])), None)
            h_col = next((c for c in df.columns if any(k in c for k in ['height', 'hei', 'h', 'dep'])), None)
            q_col = next((c for c in df.columns if any(k in c for k in ['qty', 'q', 'pcs', 'count'])), None)
            
            if w_col and h_col and q_col:
                if st.button("Load Excel Data", type="primary"):
                    for index, row in df.iterrows():
                        room_val = str(row[room_col]) if room_col and pd.notna(row[room_col]) else "Unassigned"
                        type_val = str(row[type_col]) if type_col and pd.notna(row[type_col]) else "Part"
                        w_val = pd.to_numeric(row[w_col], errors='coerce')
                        h_val = pd.to_numeric(row[h_col], errors='coerce')
                        q_val = pd.to_numeric(row[q_col], errors='coerce')
                        
                        if pd.isna(w_val) or pd.isna(h_val) or pd.isna(q_val):
                            continue
                        w_val, h_val, q_val = int(w_val), int(h_val), int(q_val)
                        if w_val > 0 and h_val > 0 and q_val > 0:
                            st.session_state.parts.append({"room": room_val, "type": type_val, "w": w_val, "h": h_val, "q": q_val})
                    st.success("Successfully loaded from Excel!")
                    st.rerun()
            else:
                st.error("⚠️ Ensure Excel has columns for Width, Height, and Qty.")
        except Exception as e:
            st.error(f"Error reading file: {e}")

st.markdown("---")

if st.session_state.parts:
    st.subheader("Current Order Cut List")
    total_order_sqm = 0
    
    for i, p in enumerate(st.session_state.parts):
        sqm_per_pc = (p['w'] * p['h']) / 1_000_000
        row_total_sqm = sqm_per_pc * p['q']
        total_order_sqm += row_total_sqm
        col_text, col_btn = st.columns([6, 1])
        col_text.write(f"• **[{p.get('room', 'Unassigned')}] {p.get('type', 'Part')}** — **{p['q']} pcs** of {p['w']}x{p['h']}mm &nbsp;&nbsp;*( {sqm_per_pc:.2f} SQM/pc | Total: {row_total_sqm:.2f} SQM )*")
        if col_btn.button("🗑️ Remove", key=f"del_{i}"):
            st.session_state.parts.pop(i)
            st.rerun()
            
    st.info(f"📐 **Total Project Area:** {total_order_sqm:.2f} SQM")
    
    col_run, col_clear = st.columns([2, 4])
    run_calc = col_run.button("Run Deep Heuristic Optimizer", type="primary", use_container_width=True)
    if col_clear.button("Clear Entire List"):
        st.session_state.parts = []
        st.rerun()

    if run_calc:
        true_delivered_area = sum(p['w'] * p['h'] * p['q'] for p in st.session_state.parts)
        eff_w = sheet_w - kerf
        eff_h = sheet_h - kerf
        
        standard_targets = []
        mandatory_oversized = []
        target_id = 0
        id_to_room = {} 
        id_to_type = {}
        
        for p in st.session_state.parts:
            for _ in range(p['q']):
                id_to_room[target_id] = p.get('room', 'Unassigned')
                id_to_type[target_id] = p.get('type', 'Part')
                needs_site_split = False
                if enable_site_limit and not piece_fits_slab({'w': p['w'], 'h': p['h']}, site_limit_l, site_limit_w, strict_grain):
                    needs_site_split = True
                
                if needs_site_split:
                    cw, ch = get_oriented_limits(p['w'], p['h'], site_limit_l, site_limit_w, strict_grain)
                    site_frags = get_mandatory_fragments(p['w'], p['h'], cw, ch)
                    final_frags = []
                    all_fit = True
                    for sf in site_frags:
                        if not piece_fits_slab({'w': sf['w'], 'h': sf['h']}, eff_w, eff_h, strict_grain):
                            all_fit = False
                            scw, sch = get_oriented_limits(sf['w'], sf['h'], eff_w, eff_h, strict_grain)
                            sub_frags = get_mandatory_fragments(sf['w'], sf['h'], scw, sch)
                            for sub_f in sub_frags:
                                final_frags.append({'w': sub_f['w'], 'h': sub_f['h'], 'x': sf['x'] + sub_f['x'], 'y': sf['y'] + sub_f['y']})
                        else:
                            final_frags.append(sf)
                    type_label = 'Site Joint' if all_fit else 'Site + Factory Joint'
                    mandatory_oversized.append({'id': target_id, 'w': p['w'], 'h': p['h'], 'frags': final_frags, 'type': type_label})
                else:
                    if not piece_fits_slab({'w': p['w'], 'h': p['h']}, eff_w, eff_h, strict_grain):
                        cw, ch = get_oriented_limits(p['w'], p['h'], eff_w, eff_h, strict_grain)
                        best_frags = get_mandatory_fragments(p['w'], p['h'], cw, ch)
                        mandatory_oversized.append({'id': target_id, 'w': p['w'], 'h': p['h'], 'frags': best_frags, 'type': 'Factory Joint'})
                    else:
                        standard_targets.append({'id': target_id, 'w': p['w'], 'h': p['h']})
                target_id += 1
                
        final_slabs = 0
        final_solid_count = 0
        final_recycled_count = 0
        final_rects = []
        assembled_pieces_data = [] 
        final_virtual_boards = []
        final_donor_blocks = []
        
        slab_area = sheet_w * sheet_h
        theoretical_min_slabs = max(1, math.ceil(true_delivered_area / slab_area))
        max_test_slabs = theoretical_min_slabs + 25 
        
        with st.spinner('Calculating Double-Step Nesting layout... this may take a few seconds...'):
            for test_slabs in range(theoretical_min_slabs, max_test_slabs):
                
                base_rects_input = []
                for t in standard_targets:
                    base_rects_input.append({'w': t['w'], 'h': t['h'], 'rid': f"solid_{t['id']}_{t['w']}_{t['h']}"})
                for mt in mandatory_oversized:
                    prefix = 'site' if 'Site' in mt['type'] else 'mand'
                    for f_idx, f in enumerate(mt['frags']):
                        base_rects_input.append({'w': f['w'], 'h': f['h'], 'rid': f"{prefix}_{mt['id']}_{mt['w']}_{mt['h']}_{f_idx}"})
                        
                packer_base, is_base_success = can_pack(base_rects_input, test_slabs, sheet_w, sheet_h, kerf, strict_grain)
                base_rects = packer_base.rect_list()
                
                packed_solid_ids = set([int(str(r[5]).split('_')[1]) for r in base_rects if str(r[5]).startswith('solid')])
                packed_mand_rids = set([str(r[5]) for r in base_rects if str(r[5]).startswith('mand') or str(r[5]).startswith('site')])
                expected_mand = sum(len(mt['frags']) for mt in mandatory_oversized)
                
                if len(packed_mand_rids) < expected_mand:
                    continue 
                    
                if len(packed_solid_ids) == len(standard_targets):
                    final_slabs = test_slabs
                    final_solid_count = len(standard_targets)
                    final_recycled_count = 0
                    final_rects = base_rects
                    break
                    
                if is_seamless:
                    missing_standard = [t for t in standard_targets if t['id'] not in packed_solid_ids]
                    missing_standard = sorted(missing_standard, key=lambda x: x['w'] * x['h'], reverse=True)
                    
                    virt_packer = newPacker(rotation=not strict_grain)
                    virt_packer.add_bin(sheet_w, sheet_h, count=len(missing_standard))
                    for t in missing_standard:
                        virt_packer.add_rect(t['w'] + kerf, t['h'] + kerf, rid=f"solid_{t['id']}_{t['w']}_{t['h']}")
                    virt_packer.pack()
                    
                    virtual_boards = []
                    for v_bin_idx in set([r[0] for r in virt_packer.rect_list()]):
                        bin_rects = [r for r in virt_packer.rect_list() if r[0] == v_bin_idx]
                        max_w = max([r[1] + r[3] for r in bin_rects])
                        max_h = max([r[2] + r[4] for r in bin_rects])
                        virtual_boards.append({'bin_idx': v_bin_idx, 'w': max_w, 'h': max_h, 'rects': bin_rects})

                    strategies_to_test = [[1.0]] + SPLIT_STRATEGIES
                    all_recycled_packed = False
                    
                    for strategy in strategies_to_test:
                        test_layout = []
                        for tid in packed_solid_ids:
                            t = next(x for x in standard_targets if x['id'] == tid)
                            test_layout.append({'w': t['w'], 'h': t['h'], 'rid': f"solid_{t['id']}_{t['w']}_{t['h']}"})
                        for mt in mandatory_oversized:
                            prefix = 'site' if 'Site' in mt['type'] else 'mand'
                            for f_idx, f in enumerate(mt['frags']):
                                test_layout.append({'w': f['w'], 'h': f['h'], 'rid': f"{prefix}_{mt['id']}_{mt['w']}_{mt['h']}_{f_idx}"})
                                
                        current_donor_blocks = []
                        for vb in virtual_boards:
                            dbs = split_virtual_board(vb['w'], vb['h'], strategy, sheet_w, sheet_h, kerf)
                            for db_idx, db in enumerate(dbs):
                                rid = f"donor_{vb['bin_idx']}_{db_idx}"
                                test_layout.append({'w': db['w'], 'h': db['h'], 'rid': rid})
                                current_donor_blocks.append({'rid': rid, 'db': db, 'vb_idx': vb['bin_idx']})
                                
                        test_packer, is_test_success = can_pack(test_layout, test_slabs, sheet_w, sheet_h, kerf, strict_grain)
                        
                        if is_test_success:
                            all_recycled_packed = True
                            final_packer_instance = test_packer
                            donor_blocks_used = current_donor_blocks
                            break 
                            
                    if all_recycled_packed:
                        final_slabs = test_slabs
                        final_solid_count = len(packed_solid_ids)
                        final_recycled_count = len(missing_standard)
                        final_rects = final_packer_instance.rect_list()
                        final_virtual_boards = virtual_boards
                        final_donor_blocks = donor_blocks_used
                        break

        if final_slabs == 0:
            final_slabs = test_slabs

        total_glue_length_mm = 0
        for mt in mandatory_oversized:
            seam_length = mt['h'] if mt['w'] >= mt['h'] else mt['w']
            joints_count = len(mt['frags']) - 1
            total_glue_length_mm += (joints_count * seam_length)
            assembled_pieces_data.append({'id': mt['id'], 'w': mt['w'], 'h': mt['h'], 'frags': mt['frags'], 'type': mt['type']})

        if final_virtual_boards:
            for vb in final_virtual_boards:
                dbs = [db for db in final_donor_blocks if db['vb_idx'] == vb['bin_idx']]
                if len(dbs) > 1:
                    seam_length = vb['h'] if vb['w'] >= vb['h'] else vb['w']
                    joints_count = len(dbs) - 1
                    total_glue_length_mm += (joints_count * seam_length)
                    
        total_glue_length_cm = total_glue_length_mm / 10.0
        total_material_area = final_slabs * sheet_w * sheet_h
        yield_percentage = (true_delivered_area / total_material_area) * 100 if total_material_area > 0 else 0
        total_project_sqm = true_delivered_area / 1_000_000

        st.markdown("---")
        st.header("3. Production & Material Efficiency Report")
        
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("📦 Slabs Pulled", f"{final_slabs} Slabs")
        col_m2.metric("📐 Total Target Area", f"{total_project_sqm:.2f} SQM")
        col_m3.metric("🔥 True Material Yield", f"{yield_percentage:.1f}%")
        col_m4.metric("💧 Est. Glue Required", f"{total_glue_length_cm:.1f} CM")
        
        st.success(f"📋 **Mixed Batch Output:** {final_solid_count} pieces clean-cut. {len(mandatory_oversized)} oversized joints generated. {final_recycled_count} pieces pulled from Double Step Recycled Boards.")

        # --- COMPREHENSIVE EXCEL EXPORT ---
        export_data = []
        for bin_idx in range(final_slabs):
            bin_rects = [r for r in final_rects if r[0] == bin_idx]
            for r in bin_rects:
                rid = str(r[5])
                act_w, act_h = r[3] - kerf, r[4] - kerf
                if rid.startswith('donor'):
                    parts = rid.split('_')
                    board_num = int(parts[1]) + 1
                    export_data.append({'Slab No.': bin_idx + 1, 'Room/Area': 'FACTORY USE', 'Part Details': f'DONOR BLOCK (For Board {board_num})', 'Width (mm)': int(act_w), 'Height (mm)': int(act_h)})
                else:
                    parts = rid.split('_')
                    t_id = int(parts[1])
                    room_name = id_to_room.get(t_id, "Unassigned")
                    part_type_str = id_to_type.get(t_id, "Part")
                    
                    cat = "Solid Cut"
                    if rid.startswith('site'): cat = "Site Joint"
                    elif rid.startswith('mand'): cat = "Factory Joint"
                    elif rid.startswith('rec'): cat = "Recycled Board Output"
                    
                    export_data.append({'Slab No.': bin_idx + 1, 'Room/Area': room_name, 'Part Details': f"{part_type_str} ({cat})", 'Width (mm)': int(act_w), 'Height (mm)': int(act_h)})
        
        df_export = pd.DataFrame(export_data)
        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
            pd.DataFrame(st.session_state.parts).to_excel(writer, index=False, sheet_name='Input Order')
            if not df_export.empty:
                df_export.to_excel(writer, index=False, sheet_name='Factory Cut Plan')
        
        st.download_button(
            label="📥 Export Detailed Cut Plan (Excel)", 
            data=output_excel.getvalue(), 
            file_name=f"{project_name.replace(' ', '_')}_Factory_Cut_Plan.xlsx", 
            mime="application/vnd.ms-excel",
            type="primary"
        )

        # --- PDF GENERATION ---
        pdf_buffer = io.BytesIO()
        with PdfPages(pdf_buffer) as pdf:
            
            # --- PAGE 1: REPORT SUMMARY ---
            fig_sum, ax_sum = plt.subplots(figsize=(8, 6))
            ax_sum.axis('off')
            site_joints_count = len([m for m in mandatory_oversized if 'Site' in m['type']])
            fact_joints_count = len([m for m in mandatory_oversized if m['type'] == 'Factory Joint'])
            fig_sum.suptitle(f"PROJECT: {project_name.upper()}", fontsize=14, weight='bold', color='#cc0000', y=0.95)
            
            summary_header = "S&C ASIA | PRODUCTION & MATERIAL EFFICIENCY REPORT"
            summary_content = (
                f"====================================================\n"
                f" PROJECT METRICS SUMMARY\n"
                f"====================================================\n\n"
                f" • Total Slabs Pulled        : {final_slabs} Slabs\n"
                f" • Total Target Area         : {total_project_sqm:.2f} SQM\n"
                f" • True Material Yield       : {yield_percentage:.1f}%\n"
                f" • Estimated Glue Required   : {total_glue_length_cm:.1f} CM\n"
                f" • Vein Matching Required    : {'YES (No Rotation)' if strict_grain else 'NO'}\n\n"
                f"----------------------------------------------------\n"
                f" BATCH COMPOSITION BREAKDOWN\n"
                f"----------------------------------------------------\n"
                f" • Solid Clean-Cut Pieces    : {final_solid_count}\n"
                f" • Factory Jointed Pieces    : {fact_joints_count}\n"
                f" • Site Jointed Pieces       : {site_joints_count}\n"
                f" • Pieces on Recycled Boards : {final_recycled_count}\n"
            )
            ax_sum.text(0.05, 0.85, summary_header, fontsize=12, weight='bold', color='#1f4e78', va='top')
            ax_sum.text(0.05, 0.70, summary_content, fontsize=10, family='monospace', va='top')
            fig_sum.text(0.95, 0.05, f"Page {pdf.get_pagecount() + 1}", ha='right', fontsize=9)
            pdf.savefig(fig_sum, bbox_inches='tight')
            plt.close(fig_sum)

            # --- PAGE 2+: ORIGINAL INPUT CUT LIST (PAGINATED) ---
            list_items = []
            for p in st.session_state.parts:
                sqm_pc = (p['w'] * p['h']) / 1_000_000
                total_row = sqm_pc * p['q']
                list_items.append(f"[{p.get('room', 'Unassigned')}] {p.get('type', 'Part')} - {p['q']} pcs of {p['w']}x{p['h']}mm ({sqm_pc:.2f} SQM/pc | Total: {total_row:.2f} SQM)")
            
            items_per_page = 35 # Prevents running off the bottom of the PDF
            for i in range(0, len(list_items), items_per_page):
                page_items = list_items[i:i+items_per_page]
                fig_list, ax_list = plt.subplots(figsize=(8, 6))
                ax_list.axis('off')
                fig_list.suptitle(f"PROJECT: {project_name.upper()} | INPUT CUT LIST", fontsize=14, weight='bold', color='#cc0000', y=0.95)
                
                y_pos = 0.90
                ax_list.text(0.05, y_pos, "ORIGINAL ORDER REQUIREMENTS:", fontsize=11, weight='bold', color='#1f4e78')
                y_pos -= 0.05
                
                for item in page_items:
                    ax_list.text(0.05, y_pos, f"• {item}", fontsize=9, family='monospace')
                    y_pos -= 0.022
                
                if i + items_per_page >= len(list_items):
                    y_pos -= 0.02
                    ax_list.text(0.05, y_pos, f"TOTAL PROJECT AREA: {total_project_sqm:.2f} SQM", fontsize=10, weight='bold', color='#1f4e78')
                
                fig_list.text(0.95, 0.05, f"Page {pdf.get_pagecount() + 1}", ha='right', fontsize=9)
                pdf.savefig(fig_list, bbox_inches='tight')
                plt.close(fig_list)

            # --- PRIMARY SLAB CUTTING MAPS ---
            st.subheader("Factory Floor: Primary Slab Maps")
            for bin_idx in range(final_slabs):
                fig, (ax, ax_leg) = plt.subplots(2, 1, figsize=(10, 4.5), gridspec_kw={'height_ratios': [3.5, 1]})
                fig.suptitle(f"PROJECT: {project_name.upper()} | PRIMARY SLAB {bin_idx + 1}", fontsize=12, weight='bold', color='#1f4e78')
                ax.add_patch(patches.Rectangle((0,0), sheet_w, sheet_h, facecolor='#e0e0e0', edgecolor='black', lw=2))
                bin_rects = [r for r in final_rects if r[0] == bin_idx]
                
                unique_parts = {}
                tag_counter = 1
                for r in bin_rects:
                    rid = str(r[5])
                    parts = rid.split('_')
                    act_w, act_h = r[3] - kerf, r[4] - kerf
                    
                    if rid.startswith('donor'):
                        room_name, part_type_str = "FACTORY", f"BOARD {int(parts[1])+1} DONOR"
                        p_type, target_w, target_h = part_type_str, str(int(act_w)), str(int(act_h))
                    else:
                        t_id = int(parts[1])
                        room_name = id_to_room.get(t_id, "Unassigned")
                        part_type_str = id_to_type.get(t_id, "Part")
                        if rid.startswith('solid'):
                            p_type, target_w, target_h = part_type_str, parts[2], parts[3]
                        elif rid.startswith('site'):
                            p_type, target_w, target_h = f"{part_type_str} (SITE JOINT)", str(int(act_w)), str(int(act_h))
                        elif rid.startswith('mand'):
                            p_type, target_w, target_h = f"{part_type_str} (FACT JOINT)", str(int(act_w)), str(int(act_h))
                            
                    key = (room_name, p_type, target_w, target_h)
                    if key not in unique_parts:
                        unique_parts[key] = {'tag': str(tag_counter), 'count': 0}
                        tag_counter += 1
                    unique_parts[key]['count'] += 1
                
                for r in bin_rects:
                    rx, ry, rw, rh, rid = r[1], r[2], r[3], r[4], str(r[5])
                    act_w, act_h = rw - kerf, rh - kerf
                    parts = rid.split('_')
                    
                    if rid.startswith('donor'):
                        target_w, target_h = str(int(act_w)), str(int(act_h))
                        key = ("FACTORY", f"BOARD {int(parts[1])+1} DONOR", target_w, target_h)
                        tag = unique_parts[key]['tag']
                        patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#1e8449', facecolor='#a9dfbf', lw=2.5, linestyle=':')
                        ax.add_patch(patch)
                        draw_smart_label(ax, "FACTORY", f"DONOR BOARD {int(parts[1])+1}", target_w, target_h, rx, ry, act_w, act_h, patch, tag)
                    else:
                        t_id = int(parts[1])
                        room_name = id_to_room.get(t_id, "Unassigned")
                        part_type_str = id_to_type.get(t_id, "Part")
                        
                        if rid.startswith('solid'):
                            target_w, target_h = parts[2], parts[3]
                            key = (room_name, part_type_str, target_w, target_h)
                            tag = unique_parts[key]['tag']
                            patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#2c3e50', facecolor='#85c1e9', lw=1.5)
                            ax.add_patch(patch)
                            draw_smart_label(ax, room_name, part_type_str, target_w, target_h, rx, ry, act_w, act_h, patch, tag)
                        elif rid.startswith('site'):
                            target_w, target_h = str(int(act_w)), str(int(act_h))
                            key = (room_name, f"{part_type_str} (SITE JOINT)", target_w, target_h)
                            tag = unique_parts[key]['tag']
                            patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#5b2c6f', facecolor='#d7bde2', lw=1.5, linestyle='--')
                            ax.add_patch(patch)
                            draw_smart_label(ax, room_name, "SITE", target_w, target_h, rx, ry, act_w, act_h, patch, tag)
                        elif rid.startswith('mand'):
                            target_w, target_h = str(int(act_w)), str(int(act_h))
                            key = (room_name, f"{part_type_str} (FACT JOINT)", target_w, target_h)
                            tag = unique_parts[key]['tag']
                            patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#d35400', facecolor='#f5b041', lw=1.5, linestyle='--')
                            ax.add_patch(patch)
                            draw_smart_label(ax, room_name, "FACT", target_w, target_h, rx, ry, act_w, act_h, patch, tag)
                
                ax.set_xlim(0, sheet_w)
                ax.set_ylim(0, sheet_h)
                ax.set_aspect('equal')
                ax.axis('off')
                
                ax_leg.axis('off')
                sorted_keys = sorted(unique_parts.keys(), key=lambda k: int(unique_parts[k]['tag']))
                legend_lines = [f"#{unique_parts[k]['tag']} - [{k[0]}] {k[2]}x{k[3]}mm ({k[1]}) : {unique_parts[k]['count']} pcs" for k in sorted_keys]
                col_size = math.ceil(len(legend_lines) / 3) if len(legend_lines) > 0 else 1
                cols = [legend_lines[i:i+col_size] for i in range(0, len(legend_lines), col_size)]
                
                ax_leg.text(0, 1.0, f"Remarks / Parts in Slab {bin_idx + 1}:", fontsize=9, weight='bold', va='top', ha='left')
                for c_idx, col_items in enumerate(cols):
                    ax_leg.text(c_idx * 0.33, 0.75, "\n".join(col_items), fontsize=7, family='monospace', va='top', ha='left')

                fig.text(0.95, 0.05, f"Page {pdf.get_pagecount() + 1}", ha='right', fontsize=9)
                plt.tight_layout(rect=[0, 0.05, 1, 0.95]) 
                st.pyplot(fig)
                pdf.savefig(fig, bbox_inches='tight')
                plt.close(fig)

            # --- DOUBLE STEP NESTING MAPS ---
            if final_virtual_boards:
                st.markdown("---")
                st.subheader("♻️ Double Step Nesting: Recycled Boards")
                for vb in final_virtual_boards:
                    fig3, (ax3, ax_leg3) = plt.subplots(2, 1, figsize=(10, 4.5), gridspec_kw={'height_ratios': [3.5, 1]})
                    fig3.suptitle(f"PROJECT: {project_name.upper()} | RECYCLED BOARD {vb['bin_idx'] + 1} (GLUE DONOR BLOCKS HERE)", fontsize=12, weight='bold', color='#1e8449')
                    ax3.add_patch(patches.Rectangle((0,0), vb['w'], vb['h'], facecolor='#f9f9f9', edgecolor='black', lw=2))

                    vb_dbs = [db['db'] for db in final_donor_blocks if db['vb_idx'] == vb['bin_idx']]
                    for db in vb_dbs:
                        patch = patches.Rectangle((db['x'], db['y']), db['orig_w'], db['orig_h'], edgecolor='#1e8449', linestyle=':', facecolor='#d5f5e3', alpha=0.5, lw=3)
                        ax3.add_patch(patch)
                        ax3.text(db['x'] + db['orig_w']/2, db['y'] + db['orig_h']/2, f"RAW DONOR BLOCK\n{int(db['orig_w'])}x{int(db['orig_h'])}", color='#1e8449', weight='bold', ha='center', va='center', fontsize=9)

                    unique_parts_vb = {}
                    tag_counter_vb = 1
                    for r in vb['rects']:
                        rx, ry, rw, rh, rid = r[1], r[2], r[3], r[4], str(r[5])
                        act_w, act_h = rw - kerf, rh - kerf
                        parts = rid.split('_')
                        t_id = int(parts[1])
                        room_name, part_type_str = id_to_room.get(t_id, "Unassigned"), id_to_type.get(t_id, "Part")
                        key = (room_name, part_type_str, parts[2], parts[3])
                        if key not in unique_parts_vb:
                            unique_parts_vb[key] = {'tag': str(tag_counter_vb), 'count': 0}
                            tag_counter_vb += 1
                        unique_parts_vb[key]['count'] += 1

                    for r in vb['rects']:
                        rx, ry, rw, rh, rid = r[1], r[2], r[3], r[4], str(r[5])
                        act_w, act_h = rw - kerf, rh - kerf
                        parts = rid.split('_')
                        t_id = int(parts[1])
                        room_name, part_type_str = id_to_room.get(t_id, "Unassigned"), id_to_type.get(t_id, "Part")
                        key = (room_name, part_type_str, parts[2], parts[3])
                        tag = unique_parts_vb[key]['tag']

                        patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#2c3e50', facecolor='#85c1e9', lw=1.5)
                        ax3.add_patch(patch)
                        draw_smart_label(ax3, room_name, part_type_str, parts[2], parts[3], rx, ry, act_w, act_h, patch, tag)

                    ax3.set_xlim(0, vb['w'])
                    ax3.set_ylim(0, vb['h'])
                    ax3.set_aspect('equal')
                    ax3.axis('off')
                    
                    ax_leg3.axis('off')
                    sorted_keys = sorted(unique_parts_vb.keys(), key=lambda k: int(unique_parts_vb[k]['tag']))
                    legend_lines = [f"#{unique_parts_vb[k]['tag']} - [{k[0]}] {k[2]}x{k[3]}mm ({k[1]}) : {unique_parts_vb[k]['count']} pcs" for k in sorted_keys]
                    col_size = math.ceil(len(legend_lines) / 3) if len(legend_lines) > 0 else 1
                    cols = [legend_lines[i:i+col_size] for i in range(0, len(legend_lines), col_size)]
                    
                    ax_leg3.text(0, 1.0, f"Remarks / Parts to cut from Recycled Board {vb['bin_idx'] + 1}:", fontsize=9, weight='bold', va='top', ha='left')
                    for c_idx, col_items in enumerate(cols):
                        ax_leg3.text(c_idx * 0.33, 0.75, "\n".join(col_items), fontsize=7, family='monospace', va='top', ha='left')

                    fig3.text(0.95, 0.05, f"Page {pdf.get_pagecount() + 1}", ha='right', fontsize=9)
                    plt.tight_layout(rect=[0, 0.05, 1, 0.95])
                    st.pyplot(fig3)
                    pdf.savefig(fig3, bbox_inches='tight')
                    plt.close(fig3)

            # --- OVERSIZED ASSEMBLY MAPS ---
            if assembled_pieces_data:
                st.markdown("---")
                st.subheader("🧩 Oversized Jointing Assembly Maps")
                for asm in assembled_pieces_data:
                    fig2, ax2 = plt.subplots(figsize=(6, 2.5))
                    room_name, part_type_str = id_to_room.get(asm['id'], "Unassigned"), id_to_type.get(asm['id'], "Part")
                    joint_count = len(asm['frags']) - 1
                    fig2.suptitle(f"PROJECT: {project_name.upper()} | OVERSIZED ASSEMBLY MAP", fontsize=10, weight='bold', color='#1f4e78', y=1.05)
                    ax2.add_patch(patches.Rectangle((0,0), asm['w'], asm['h'], facecolor='#f9f9f9', edgecolor='black', lw=2))
                    
                    if 'Site' in asm['type']:
                        edge_c, face_c = '#5b2c6f', '#d7bde2'
                    else:
                        edge_c, face_c = '#d35400', '#f5b041'
                    
                    for f in asm['frags']:
                        patch = patches.Rectangle((f['x'], f['y']), f['w'], f['h'], edgecolor=edge_c, linestyle='--', facecolor=face_c, alpha=0.6, lw=1.5)
                        ax2.add_patch(patch)
                        draw_smart_label(ax2, room_name, part_type_str, str(int(f['w'])), str(int(f['h'])), f['x'], f['y'], f['w'], f['h'], patch, tag="")
                    
                    ax2.set_xlim(0, asm['w'])
                    ax2.set_ylim(0, asm['h'])
                    ax2.set_aspect('equal')
                    ax2.axis('off')
                    ax2.set_title(f"[{room_name}] Assembled: {asm['w']}x{asm['h']}mm | {asm['type']} | {joint_count} Joints", fontsize=9)
                    fig2.text(0.95, 0.05, f"Page {pdf.get_pagecount() + 1}", ha='right', fontsize=9)
                    st.pyplot(fig2)
                    pdf.savefig(fig2, bbox_inches='tight')
                    plt.close(fig2)

        st.markdown("---")
        st.download_button("📄 Export Production PDF", pdf_buffer.getvalue(), f"{project_name.replace(' ', '_')}_Production_Map.pdf", "application/pdf")
