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
    [0.5, 0.5], 
    [0.6, 0.4], 
    [0.7, 0.3], 
    [0.34, 0.33, 0.33], 
    [0.4, 0.4, 0.2], 
    [0.5, 0.3, 0.2], 
    [0.25, 0.25, 0.25, 0.25]
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
    room_name = "Unassigned" if pd.isna(room_name) or str(room_name).strip().lower() in ['nan', 'none', ''] else room_name
    room_str = str(room_name).strip()
    is_wide = act_w >= act_h
    tag_text = f"#{tag}" if tag else ""

    if act_w <= 12 or act_h <= 12: return
    if act_w <= 80 and act_h <= 80:
        if tag_text:
            t = ax.text(cx, cy, tag_text, color='black', weight='bold', ha='center', va='center', fontsize=5, clip_on=True)
            t.set_clip_path(rect_patch)
        return

    lines, colors, fs, rot = [], [], 4, 0
    if act_w >= 220 and act_h >= 120:
        if tag_text:
            t_badge = ax.text(rx + 15, cy, tag_text, color='#cc0000', weight='bold', ha='left', va='center', fontsize=10, clip_on=True)
            t_badge.set_clip_path(rect_patch)
        lines = [f"[{room_str}]", f"{part_type}", f"{w_label}x{h_label}"]
        colors = ['#cc0000', 'black', 'black']
        rot, fs = 0, 6
    elif is_wide:
        display_room = room_str[:5] + ".." if len(room_str) > 5 else room_str
        if act_h >= 50:
            lines, colors, fs = [f"{tag_text} [{display_room}] {part_type}", f"{w_label}x{h_label}"], ['#cc0000', 'black'], 4.5
        elif act_h >= 25:
            lines, colors, fs = ([f"{tag_text} {w_label}x{h_label}"], ['black'], 4) if act_w >= 100 else ([tag_text], ['black'], 4)
        else:
            lines, colors, fs = [tag_text], ['black'], 3.5
        rot = 0
    else:
        display_room = room_str[:5] + ".." if len(room_str) > 5 else room_str
        if act_w >= 50:
            lines, colors, fs = [f"{tag_text} [{display_room}] {part_type}", f"{w_label}x{h_label}"], ['#cc0000', 'black'], 4.5
        elif act_w >= 25:
            lines, colors, fs = ([f"{tag_text} {w_label}x{h_label}"], ['black'], 4) if act_h >= 100 else ([tag_text], ['black'], 4)
        else:
            lines, colors, fs = [tag_text], ['black'], 3.5
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
strict_grain = st.sidebar.checkbox("Veined Material (Strict Grain Match)", value=False)
st.sidebar.markdown("<br>", unsafe_allow_html=True)

enable_site_limit = st.sidebar.checkbox("Enable Elevator/Site Limit", value=False)
if enable_site_limit:
    site_limit_l = st.sidebar.number_input("Elevator Max Length (mm)", value=2400)
    site_limit_w = st.sidebar.number_input("Elevator Max Width (mm)", value=1200)
else:
    site_limit_l, site_limit_w = None, None

st.sidebar.markdown("<br>", unsafe_allow_html=True)
is_seamless = st.sidebar.checkbox("Enable Double-Step Recycled Nesting", value=True)

force_80_yield = st.sidebar.checkbox(
    "Target >80% Yield (Hyper-Jointing)", 
    value=False, 
    help="Forces engine to chop specific missing parts further ONLY if absolutely necessary to hit >80% yield."
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Visual Key")
st.sidebar.markdown("🟦 **Blue:** Clean Solid Cut")
st.sidebar.markdown("🟪 **Purple:** Site Joint (Elevator)")
st.sidebar.markdown("🟧 **Orange:** Factory Joint (Oversized)")
st.sidebar.markdown("🟩 **Green Dotted:** Donor Block (Recycled)")
st.sidebar.markdown("⬜ **Gray:** Dead Waste")


# --- UI: PROJECT SETUP & TABS ---
if 'parts' not in st.session_state: st.session_state.parts = []

st.subheader("📁 Project Setup")
project_name = st.text_input("Master Project Name", value="Amari Hotel Project")

tab_manual, tab_excel = st.tabs(["🛠️ Manual Input (Organized)", "📥 Excel Import"])

with tab_manual:
    st.markdown("Batch-add parts to multiple rooms instantly.")
    c_pref, c_start, c_units = st.columns([2, 1.5, 1.5])
    room_prefix = c_pref.text_input("Room Name / Prefix", value="", placeholder="e.g., 'Unit '")
    enable_auto_num = c_start.checkbox("Auto-Number Rooms", value=True)
    start_num = c_start.number_input("Starting Number", value=101, step=1, disabled=not enable_auto_num)
    num_units = c_units.number_input("Total Rooms to Add", value=15, min_value=1)
    
    st.markdown("<br>", unsafe_allow_html=True)
    c_type, c1, c2, c3, c4 = st.columns([1.5, 1.5, 1.5, 1.5, 2])
    part_type = c_type.selectbox("Part Category", ["Top", "Apron", "Splash", "Skirting", "Other"])
    w = c1.number_input("Width (mm)", value=1970, min_value=1)
    h = c2.number_input("Height (mm)", value=220, min_value=1)
    q_per_unit = c3.number_input("Qty per Room", value=1, min_value=1)
    
    c4.markdown("<br>", unsafe_allow_html=True) 
    if c4.button("➕ Batch Add to List", use_container_width=True):
        for i in range(int(num_units)):
            room_str = f"{room_prefix}{int(start_num) + i}" if enable_auto_num else (room_prefix if room_prefix else "Unassigned")
            st.session_state.parts.append({"room": room_str, "type": part_type, "w": int(w), "h": int(h), "q": int(q_per_unit)})
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
                        w_val, h_val, q_val = pd.to_numeric(row[w_col], errors='coerce'), pd.to_numeric(row[h_col], errors='coerce'), pd.to_numeric(row[q_col], errors='coerce')
                        
                        if pd.isna(w_val) or pd.isna(h_val) or pd.isna(q_val): continue
                        if w_val > 0 and h_val > 0 and q_val > 0:
                            st.session_state.parts.append({"room": room_val, "type": type_val, "w": int(w_val), "h": int(h_val), "q": int(q_val)})
                    st.success("Successfully loaded from Excel!")
                    st.rerun()
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
        eff_w, eff_h = sheet_w - kerf, sheet_h - kerf
        
        standard_targets, mandatory_oversized = [], []
        target_id = 0
        id_to_room, id_to_type = {}, {}
        
        for p in st.session_state.parts:
            for _ in range(p['q']):
                id_to_room[target_id], id_to_type[target_id] = p.get('room', 'Unassigned'), p.get('type', 'Part')
                needs_site_split = False
                if enable_site_limit and not piece_fits_slab({'w': p['w'], 'h': p['h']}, site_limit_l, site_limit_w, strict_grain):
                    needs_site_split = True
                
                if needs_site_split:
                    cw, ch = get_oriented_limits(p['w'], p['h'], site_limit_l, site_limit_w, strict_grain)
                    site_frags = get_mandatory_fragments(p['w'], p['h'], cw, ch)
                    final_frags, all_fit = [], True
                    for sf in site_frags:
                        if not piece_fits_slab({'w': sf['w'], 'h': sf['h']}, eff_w, eff_h, strict_grain):
                            all_fit = False
                            scw, sch = get_oriented_limits(sf['w'], sf['h'], eff_w, eff_h, strict_grain)
                            for sub_f in get_mandatory_fragments(sf['w'], sf['h'], scw, sch):
                                final_frags.append({'w': sub_f['w'], 'h': sub_f['h'], 'x': sf['x'] + sub_f['x'], 'y': sf['y'] + sub_f['y']})
                        else:
                            final_frags.append(sf)
                    mandatory_oversized.append({'id': target_id, 'w': p['w'], 'h': p['h'], 'frags': final_frags, 'type': 'Site Joint' if all_fit else 'Site + Factory Joint'})
                else:
                    if not piece_fits_slab({'w': p['w'], 'h': p['h']}, eff_w, eff_h, strict_grain):
                        cw, ch = get_oriented_limits(p['w'], p['h'], eff_w, eff_h, strict_grain)
                        mandatory_oversized.append({'id': target_id, 'w': p['w'], 'h': p['h'], 'frags': get_mandatory_fragments(p['w'], p['h'], cw, ch), 'type': 'Factory Joint'})
                    else:
                        standard_targets.append({'id': target_id, 'w': p['w'], 'h': p['h']})
                target_id += 1
                
        final_slabs, final_solid_count, final_recycled_count = 0, 0, 0
        final_rects, assembled_pieces_data, final_virtual_boards, final_donor_blocks = [], [], [], []
        slab_area = sheet_w * sheet_h
        theoretical_min_slabs = max(1, math.ceil(true_delivered_area / slab_area))
        
        # Hyper Yield Logic constraint
        total_project_sqm, slab_area_sqm = true_delivered_area / 1_000_000, slab_area / 1_000_000
        if force_80_yield:
            max_allowed_slabs = math.floor(total_project_sqm / (0.80 * slab_area_sqm))
            max_test_slabs = (max_allowed_slabs + 1) if max_allowed_slabs >= theoretical_min_slabs else (theoretical_min_slabs + 1)
        else:
            max_test_slabs = theoretical_min_slabs + 25 
        
        with st.spinner('Calculating 1-to-1 Double-Step Nesting layout... this may take a moment...'):
            for test_slabs in range(theoretical_min_slabs, max_test_slabs):
                base_rects_input = [{'w': t['w'], 'h': t['h'], 'rid': f"solid_{t['id']}_{t['w']}_{t['h']}"} for t in standard_targets]
                for mt in mandatory_oversized:
                    prefix = 'site' if 'Site' in mt['type'] else 'mand'
                    for f_idx, f in enumerate(mt['frags']):
                        base_rects_input.append({'w': f['w'], 'h': f['h'], 'rid': f"{prefix}_{mt['id']}_{mt['w']}_{mt['h']}_{f_idx}"})
                        
                packer_base, is_base_success = can_pack(base_rects_input, test_slabs, sheet_w, sheet_h, kerf, strict_grain)
                base_rects = packer_base.rect_list()
                packed_solid_ids = set([int(str(r[5]).split('_')[1]) for r in base_rects if str(r[5]).startswith('solid')])
                packed_mand_rids = set([str(r[5]) for r in base_rects if str(r[5]).startswith('mand') or str(r[5]).startswith('site')])
                
                if len(packed_mand_rids) < sum(len(mt['frags']) for mt in mandatory_oversized): continue 
                if len(packed_solid_ids) == len(standard_targets):
                    final_slabs, final_solid_count, final_recycled_count, final_rects = test_slabs, len(standard_targets), 0, base_rects
                    break
                    
                if is_seamless:
                    missing_standard = sorted([t for t in standard_targets if t['id'] not in packed_solid_ids], key=lambda x: x['w'] * x['h'], reverse=True)
                    
                    # EXACT 1-TO-1 MAPPING: Each missing piece is its OWN Virtual Board. No generic mixing.
                    virtual_boards = []
                    for vb_idx, t in enumerate(missing_standard):
                        virtual_boards.append({
                            'bin_idx': vb_idx, 'w': t['w'], 'h': t['h'], 'target_id': t['id'],
                            'rects': [(0, 0, 0, t['w'] + kerf, t['h'] + kerf, f"solid_{t['id']}_{t['w']}_{t['h']}")]
                        })

                    strategies_to_test = [[1.0]] + SPLIT_STRATEGIES
                    if force_80_yield:
                        strategies_to_test.extend([[0.2]*5, [1/6]*6, [1/8]*8, [1/10]*10])
                        
                    vb_strategies = {vb['bin_idx']: 0 for vb in virtual_boards}
                    all_recycled_packed, max_attempts = False, len(strategies_to_test) * 3 
                    
                    for attempt in range(max_attempts):
                        test_layout = [{'w': t['w'], 'h': t['h'], 'rid': f"solid_{t['id']}_{t['w']}_{t['h']}"} for t in standard_targets if t['id'] in packed_solid_ids]
                        for mt in mandatory_oversized:
                            prefix = 'site' if 'Site' in mt['type'] else 'mand'
                            for f_idx, f in enumerate(mt['frags']): test_layout.append({'w': f['w'], 'h': f['h'], 'rid': f"{prefix}_{mt['id']}_{mt['w']}_{mt['h']}_{f_idx}"})
                                
                        current_donor_blocks = []
                        for vb in virtual_boards:
                            strat_idx = min(vb_strategies[vb['bin_idx']], len(strategies_to_test) - 1)
                            for db_idx, db in enumerate(split_virtual_board(vb['w'], vb['h'], strategies_to_test[strat_idx], sheet_w, sheet_h, kerf)):
                                rid = f"donor_{vb['bin_idx']}_{db_idx}"
                                test_layout.append({'w': db['w'], 'h': db['h'], 'rid': rid})
                                current_donor_blocks.append({'rid': rid, 'db': db, 'vb_idx': vb['bin_idx']})
                                
                        test_packer, is_test_success = can_pack(test_layout, test_slabs, sheet_w, sheet_h, kerf, strict_grain)
                        
                        if is_test_success:
                            all_recycled_packed = True
                            final_packer_instance, donor_blocks_used = test_packer, current_donor_blocks
                            break
                        else:
                            packed_rids = set(str(r[5]) for r in test_packer.rect_list())
                            failed_vbs = set([db['vb_idx'] for db in current_donor_blocks if db['rid'] not in packed_rids])
                            if not failed_vbs: failed_vbs = set(vb_strategies.keys())
                            
                            advanced_any = False
                            for vb_idx in failed_vbs:
                                if vb_strategies[vb_idx] < len(strategies_to_test) - 1:
                                    vb_strategies[vb_idx] += 1
                                    advanced_any = True
                            if not advanced_any: break
                                
                    if all_recycled_packed:
                        final_slabs, final_solid_count, final_recycled_count, final_rects = test_slabs, len(packed_solid_ids), len(missing_standard), final_packer_instance.rect_list()
                        final_virtual_boards, final_donor_blocks = virtual_boards, donor_blocks_used
                        break

        if final_slabs == 0: final_slabs = test_slabs

        total_glue_length_mm = 0
        for mt in mandatory_oversized:
            total_glue_length_mm += (len(mt['frags']) - 1) * (mt['h'] if mt['w'] >= mt['h'] else mt['w'])
            assembled_pieces_data.append({'id': mt['id'], 'w': mt['w'], 'h': mt['h'], 'frags': mt['frags'], 'type': mt['type']})

        if final_virtual_boards:
            for vb in final_virtual_boards:
                dbs = [db for db in final_donor_blocks if db['vb_idx'] == vb['bin_idx']]
                if len(dbs) > 1:
                    total_glue_length_mm += (len(dbs) - 1) * (vb['h'] if vb['w'] >= vb['h'] else vb['w'])
                    
        total_glue_length_cm = total_glue_length_mm / 10.0
        total_material_area = final_slabs * sheet_w * sheet_h
        yield_percentage = (true_delivered_area / total_material_area) * 100 if total_material_area > 0 else 0

        st.markdown("---")
        st.header("3. Production & Material Efficiency Report")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("📦 Slabs Pulled", f"{final_slabs} Slabs")
        col_m2.metric("📐 Total Target Area", f"{total_project_sqm:.2f} SQM")
        col_m3.metric("🔥 True Material Yield", f"{yield_percentage:.1f}%")
        col_m4.metric("💧 Est. Glue Required", f"{total_glue_length_cm:.1f} CM")
        st.success(f"📋 **Mixed Batch Output:** {final_solid_count} pieces clean-cut. {len(mandatory_oversized)} oversized joints generated. {final_recycled_count} pieces built from Minimum-Chop Recycled Boards.")

        # --- COMPREHENSIVE EXCEL EXPORT (WITH PRECISE DONOR NAMING) ---
        export_data = []
        for bin_idx in range(final_slabs):
            bin_rects = [r for r in final_rects if r[0] == bin_idx]
            for r in bin_rects:
                rid, act_w, act_h = str(r[5]), r[3] - kerf, r[4] - kerf
                parts = rid.split('_')
                if rid.startswith('donor'):
                    t_id_list = [vb['target_id'] for vb in final_virtual_boards if vb['bin_idx'] == int(parts[1])]
                    t_name = f"[{id_to_room.get(t_id_list[0], 'Unassigned')}] {id_to_type.get(t_id_list[0], 'Part')}" if t_id_list else f"Board {int(parts[1]) + 1}"
                    export_data.append({'Slab No.': bin_idx + 1, 'Room/Area': 'FACTORY USE', 'Part Details': f'DONOR BLOCK (For {t_name})', 'Width (mm)': int(act_w), 'Height (mm)': int(act_h)})
                else:
                    t_id = int(parts[1])
                    room_name, part_type_str = id_to_room.get(t_id, "Unassigned"), id_to_type.get(t_id, "Part")
                    cat = "Site Joint" if rid.startswith('site') else ("Factory Joint" if rid.startswith('mand') else "Solid Cut")
                    export_data.append({'Slab No.': bin_idx + 1, 'Room/Area': room_name, 'Part Details': f"{part_type_str} ({cat})", 'Width (mm)': int(act_w), 'Height (mm)': int(act_h)})
        
        df_export = pd.DataFrame(export_data)
        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
            pd.DataFrame(st.session_state.parts).to_excel(writer, index=False, sheet_name='Input Order')
            if not df_export.empty: df_export.to_excel(writer, index=False, sheet_name='Factory Cut Plan')
        
        st.download_button(label="📥 Export Detailed Cut Plan (Excel)", data=output_excel.getvalue(), file_name=f"{project_name.replace(' ', '_')}_Factory_Cut_Plan.xlsx", mime="application/vnd.ms-excel", type="primary")

        # --- PDF GENERATION (STRICT A4 LANDSCAPE) ---
        pdf_buffer = io.BytesIO()
        with PdfPages(pdf_buffer) as pdf:
            fig_sum, ax_sum = plt.subplots(figsize=(11.69, 8.27))
            ax_sum.axis('off')
            fig_sum.suptitle(f"PROJECT: {project_name.upper()}", fontsize=16, weight='bold', color='#cc0000', y=0.95)
            summary_content = (f"====================================================\n PROJECT METRICS SUMMARY\n====================================================\n\n • Total Slabs Pulled        : {final_slabs} Slabs\n • Total Target Area         : {total_project_sqm:.2f} SQM\n • True Material Yield       : {yield_percentage:.1f}%\n • Estimated Glue Required   : {total_glue_length_cm:.1f} CM\n • Vein Matching Required    : {'YES (No Rotation)' if strict_grain else 'NO'}\n\n----------------------------------------------------\n BATCH COMPOSITION BREAKDOWN\n----------------------------------------------------\n • Solid Clean-Cut Pieces    : {final_solid_count}\n • Factory Jointed Pieces    : {len([m for m in mandatory_oversized if m['type'] == 'Factory Joint'])}\n • Site Jointed Pieces       : {len([m for m in mandatory_oversized if 'Site' in m['type']])}\n • Recycled 1-to-1 Assemblies: {final_recycled_count}\n")
            ax_sum.text(0.05, 0.85, "S&C ASIA | PRODUCTION & MATERIAL EFFICIENCY REPORT", fontsize=14, weight='bold', color='#1f4e78', va='top')
            ax_sum.text(0.05, 0.70, summary_content, fontsize=12, family='monospace', va='top')
            fig_sum.text(0.95, 0.05, f"Page {pdf.get_pagecount() + 1}", ha='right', fontsize=9)
            pdf.savefig(fig_sum, bbox_inches='tight')
            plt.close(fig_sum)

            room_groups = {}
            for p in st.session_state.parts:
                r, t = str(p.get('room', 'Unassigned')), str(p.get('type', 'Part'))
                if r not in room_groups: room_groups[r] = {'parts': [], 'totals': {}}
                room_groups[r]['parts'].append(p)
                room_groups[r]['totals'][t] = room_groups[r]['totals'].get(t, 0) + p['q']

            def new_list_page():
                f, a = plt.subplots(figsize=(11.69, 8.27))
                a.axis('off')
                f.suptitle(f"PROJECT: {project_name.upper()} | PACKING CHECKLIST", fontsize=14, weight='bold', color='#cc0000', y=0.95)
                return f, a, 0.88

            fig_list, ax_list, y_pos = new_list_page()
            for room, data in room_groups.items():
                if y_pos < 0.20:
                    fig_list.text(0.95, 0.05, f"Page {pdf.get_pagecount() + 1}", ha='right', fontsize=9)
                    pdf.savefig(fig_list, bbox_inches='tight')
                    plt.close(fig_list)
                    fig_list, ax_list, y_pos = new_list_page()
                ax_list.text(0.05, y_pos, f"▶ ROOM / UNIT: {room}", fontsize=12, weight='bold', color='#cc0000')
                y_pos -= 0.03
                ax_list.text(0.07, y_pos, f"Subtotals: {' | '.join([f'{k}: {v} pcs' for k, v in data['totals'].items()])}", fontsize=10, weight='bold', color='#1f4e78')
                y_pos -= 0.035
                for p in data['parts']:
                    if y_pos < 0.10:
                        fig_list.text(0.95, 0.05, f"Page {pdf.get_pagecount() + 1}", ha='right', fontsize=9)
                        pdf.savefig(fig_list, bbox_inches='tight')
                        plt.close(fig_list)
                        fig_list, ax_list, y_pos = new_list_page()
                    sqm_pc = (p['w'] * p['h']) / 1_000_000
                    ax_list.text(0.07, y_pos, f"• {p.get('type', 'Part')} - {p['q']} pcs of {p['w']}x{p['h']}mm ({sqm_pc:.2f} SQM/pc | Total: {sqm_pc * p['q']:.2f} SQM)", fontsize=9, family='monospace')
                    y_pos -= 0.025
                y_pos -= 0.03 
            fig_list.text(0.95, 0.05, f"Page {pdf.get_pagecount() + 1}", ha='right', fontsize=9)
            pdf.savefig(fig_list, bbox_inches='tight')
            plt.close(fig_list)

            # --- PRIMARY SLAB CUTTING MAPS ---
            st.subheader("Factory Floor: Primary Slab Maps")
            for bin_idx in range(final_slabs):
                fig, (ax, ax_leg) = plt.subplots(2, 1, figsize=(11.69, 8.27), gridspec_kw={'height_ratios': [1.5, 1]})
                fig.suptitle(f"PROJECT: {project_name.upper()} | PRIMARY SLAB {bin_idx + 1}", fontsize=12, weight='bold', color='#1f4e78')
                ax.add_patch(patches.Rectangle((0,0), sheet_w, sheet_h, facecolor='#e0e0e0', edgecolor='black', lw=2))
                bin_rects = [r for r in final_rects if r[0] == bin_idx]
                
                unique_parts, tag_counter = {}, 1
                for r in bin_rects:
                    rid, act_w, act_h = str(r[5]), r[3] - kerf, r[4] - kerf
                    parts = rid.split('_')
                    if rid.startswith('donor'):
                        t_id_list = [vb['target_id'] for vb in final_virtual_boards if vb['bin_idx'] == int(parts[1])]
                        room_name = "FACTORY"
                        p_type = f"DONOR (For {id_to_room.get(t_id_list[0], 'Unassigned')} {id_to_type.get(t_id_list[0], 'Part')})" if t_id_list else f"BOARD {int(parts[1])+1} DONOR"
                        target_w, target_h = str(int(act_w)), str(int(act_h))
                    else:
                        t_id = int(parts[1])
                        room_name, part_type_str = id_to_room.get(t_id, "Unassigned"), id_to_type.get(t_id, "Part")
                        if rid.startswith('solid'): p_type, target_w, target_h = part_type_str, parts[2], parts[3]
                        elif rid.startswith('site'): p_type, target_w, target_h = f"{part_type_str} (SITE JOINT)", str(int(act_w)), str(int(act_h))
                        elif rid.startswith('mand'): p_type, target_w, target_h = f"{part_type_str} (FACT JOINT)", str(int(act_w)), str(int(act_h))
                            
                    key = (room_name, p_type, target_w, target_h)
                    if key not in unique_parts:
                        unique_parts[key] = {'tag': str(tag_counter), 'count': 0}
                        tag_counter += 1
                    unique_parts[key]['count'] += 1
                
                for r in bin_rects:
                    rx, ry, act_w, act_h, rid = r[1], r[2], r[3] - kerf, r[4] - kerf, str(r[5])
                    parts = rid.split('_')
                    if rid.startswith('donor'):
                        target_w, target_h = str(int(act_w)), str(int(act_h))
                        t_id_list = [vb['target_id'] for vb in final_virtual_boards if vb['bin_idx'] == int(parts[1])]
                        p_type = f"DONOR (For {id_to_room.get(t_id_list[0], 'Unassigned')} {id_to_type.get(t_id_list[0], 'Part')})" if t_id_list else f"BOARD {int(parts[1])+1} DONOR"
                        tag = unique_parts[("FACTORY", p_type, target_w, target_h)]['tag']
                        patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#1e8449', facecolor='#a9dfbf', lw=2.5, linestyle=':')
                        ax.add_patch(patch)
                        lbl = f"DONOR\n({id_to_room.get(t_id_list[0], 'Unassigned')})" if t_id_list else f"DONOR BOARD {int(parts[1])+1}"
                        draw_smart_label(ax, "FACTORY", lbl, target_w, target_h, rx, ry, act_w, act_h, patch, tag)
                    else:
                        t_id = int(parts[1])
                        room_name, part_type_str = id_to_room.get(t_id, "Unassigned"), id_to_type.get(t_id, "Part")
                        if rid.startswith('solid'):
                            target_w, target_h = parts[2], parts[3]
                            tag = unique_parts[(room_name, part_type_str, target_w, target_h)]['tag']
                            patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#2c3e50', facecolor='#85c1e9', lw=1.5)
                        elif rid.startswith('site'):
                            target_w, target_h = str(int(act_w)), str(int(act_h))
                            tag = unique_parts[(room_name, f"{part_type_str} (SITE JOINT)", target_w, target_h)]['tag']
                            patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#5b2c6f', facecolor='#d7bde2', lw=1.5, linestyle='--')
                        elif rid.startswith('mand'):
                            target_w, target_h = str(int(act_w)), str(int(act_h))
                            tag = unique_parts[(room_name, f"{part_type_str} (FACT JOINT)", target_w, target_h)]['tag']
                            patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#d35400', facecolor='#f5b041', lw=1.5, linestyle='--')
                        
                        ax.add_patch(patch)
                        draw_smart_label(ax, room_name, part_type_str, target_w, target_h, rx, ry, act_w, act_h, patch, tag)
                
                ax.set_xlim(0, sheet_w); ax.set_ylim(0, sheet_h); ax.set_aspect('equal'); ax.axis('off'); ax_leg.axis('off')
                sorted_keys = sorted(unique_parts.keys(), key=lambda k: int(unique_parts[k]['tag']))
                legend_lines = [f"#{unique_parts[k]['tag']} - [{k[0]}] {k[2]}x{k[3]}mm ({k[1]}) : {unique_parts[k]['count']} pcs" for k in sorted_keys]
                col_size = math.ceil(len(legend_lines) / 3) if len(legend_lines) > 0 else 1
                cols = [legend_lines[i:i+col_size] for i in range(0, len(legend_lines), col_size)]
                
                ax_leg.text(0, 1.0, f"Remarks / Parts in Slab {bin_idx + 1}:", fontsize=10, weight='bold', va='top', ha='left')
                for c_idx, col_items in enumerate(cols): ax_leg.text(c_idx * 0.33, 0.85, "\n\n".join(col_items), fontsize=8.5, family='monospace', va='top', ha='left')
                fig.text(0.95, 0.05, f"Page {pdf.get_pagecount() + 1}", ha='right', fontsize=9)
                plt.tight_layout(rect=[0, 0.05, 1, 0.95]) 
                st.pyplot(fig)
                pdf.savefig(fig, bbox_inches='tight')
                plt.close(fig)

            # --- DOUBLE STEP NESTING MAPS (3 BOARDS PER PAGE A4) ---
            if final_virtual_boards:
                st.markdown("---")
                st.subheader("♻️ Double Step Nesting: 1-to-1 Recycled Assemblies")
                boards_per_page = 3
                for i in range(0, len(final_virtual_boards), boards_per_page):
                    page_vbs = final_virtual_boards[i:i+boards_per_page]
                    fig3, axes = plt.subplots(len(page_vbs), 1, figsize=(11.69, 8.27))
                    if len(page_vbs) == 1: axes = [axes]
                    fig3.suptitle(f"PROJECT: {project_name.upper()} | 1-TO-1 RECYCLED ASSEMBLIES (PAGE {i//boards_per_page + 1})", fontsize=12, weight='bold', color='#1e8449')
                    
                    for idx, vb in enumerate(page_vbs):
                        ax3 = axes[idx]
                        ax3.add_patch(patches.Rectangle((0,0), vb['w'], vb['h'], facecolor='#f9f9f9', edgecolor='black', lw=2))
                        
                        # Draw Target Part FIRST (Light Blue)
                        for r in vb['rects']:
                            rx, ry, act_w, act_h, rid = r[1], r[2], r[3] - kerf, r[4] - kerf, str(r[5])
                            t_id = int(rid.split('_')[1])
                            room_name, part_type_str = id_to_room.get(t_id, "Unassigned"), id_to_type.get(t_id, "Part")
                            patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#2c3e50', facecolor='#85c1e9', lw=1.5, alpha=0.6)
                            ax3.add_patch(patch)
                            draw_smart_label(ax3, room_name, part_type_str, rid.split('_')[2], rid.split('_')[3], rx, ry, act_w, act_h, patch, tag="")
                        
                        # Draw Heavy Green Dotted Stitch Lines ON TOP
                        vb_dbs = [db['db'] for db in final_donor_blocks if db['vb_idx'] == vb['bin_idx']]
                        for db in vb_dbs:
                            patch = patches.Rectangle((db['x'], db['y']), db['orig_w'], db['orig_h'], edgecolor='#1e8449', linestyle=':', facecolor='none', lw=3)
                            ax3.add_patch(patch)
                            ax3.text(db['x'] + db['orig_w']/2, db['y'] + db['orig_h']/2, f"RAW DONOR\n{int(db['orig_w'])}x{int(db['orig_h'])}", color='#1e8449', weight='bold', ha='center', va='center', fontsize=9)

                        ax3.set_xlim(0, max(vb['w'], sheet_w/4))
                        ax3.set_ylim(0, vb['h'] + 10)
                        ax3.set_aspect('equal')
                        ax3.axis('off')
                        ax3.set_title(f"Recycled Assembly {vb['bin_idx'] + 1} -> Target Part: [{room_name}] {part_type_str}", fontsize=10, color='#1f4e78', loc='left')
                    
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
                    fig2, ax2 = plt.subplots(figsize=(11.69, 8.27))
                    room_name, part_type_str = id_to_room.get(asm['id'], "Unassigned"), id_to_type.get(asm['id'], "Part")
                    fig2.suptitle(f"PROJECT: {project_name.upper()} | OVERSIZED ASSEMBLY MAP", fontsize=12, weight='bold', color='#1f4e78', y=0.95)
                    ax2.add_patch(patches.Rectangle((0,0), asm['w'], asm['h'], facecolor='#f9f9f9', edgecolor='black', lw=2))
                    edge_c, face_c = ('#5b2c6f', '#d7bde2') if 'Site' in asm['type'] else ('#d35400', '#f5b041')
                    for f in asm['frags']:
                        patch = patches.Rectangle((f['x'], f['y']), f['w'], f['h'], edgecolor=edge_c, linestyle='--', facecolor=face_c, alpha=0.6, lw=1.5)
                        ax2.add_patch(patch)
                        draw_smart_label(ax2, room_name, part_type_str, str(int(f['w'])), str(int(f['h'])), f['x'], f['y'], f['w'], f['h'], patch, tag="")
                    ax2.set_xlim(0, asm['w']); ax2.set_ylim(0, asm['h']); ax2.set_aspect('equal'); ax2.axis('off')
                    ax2.set_title(f"[{room_name}] Assembled: {asm['w']}x{asm['h']}mm | {asm['type']} | {len(asm['frags']) - 1} Joints", fontsize=10)
                    fig2.text(0.95, 0.05, f"Page {pdf.get_pagecount() + 1}", ha='right', fontsize=9)
                    st.pyplot(fig2)
                    pdf.savefig(fig2, bbox_inches='tight')
                    plt.close(fig2)

        st.markdown("---")
        st.download_button("📄 Export Production PDF", pdf_buffer.getvalue(), f"{project_name.replace(' ', '_')}_Production_Map.pdf", "application/pdf")
