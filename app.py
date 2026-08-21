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

def piece_fits_slab(f, eff_w, eff_h):
    return (f['w'] <= eff_w and f['h'] <= eff_h) or (f['h'] <= eff_w and f['w'] <= eff_h)

def get_mandatory_fragments(w, h, eff_w, eff_h):
    frags = []
    curr_x, curr_y = 0, 0
    rem_w, rem_h = w, h

    while rem_w > 0:
        cut_w = min(rem_w, eff_w)
        rem_h = h
        curr_y = 0
        while rem_h > 0:
            cut_h = min(rem_h, eff_h)
            frags.append({'w': cut_w, 'h': cut_h, 'x': curr_x, 'y': curr_y})
            curr_y += cut_h
            rem_h -= cut_h
        curr_x += cut_w
        rem_w -= cut_w
    return frags

def can_pack(rects_to_pack, num_slabs, sheet_w, sheet_h, kerf):
    p = newPacker(rotation=True)
    p.add_bin(sheet_w, sheet_h, count=num_slabs)
    for r in rects_to_pack:
        p.add_rect(r['w'] + kerf, r['h'] + kerf, rid=r['rid'])
    p.pack()
    return p, len(p.rect_list()) == len(rects_to_pack)

# --- SMART LABELING WITH STRICT CLIPPING AND TAG SYSTEM ---
def draw_smart_label(ax, room_name, piece_type, w_label, h_label, rx, ry, act_w, act_h, rect_patch, tag=""):
    cx = rx + act_w / 2
    cy = ry + act_h / 2
    
    if pd.isna(room_name) or str(room_name).strip().lower() in ['nan', 'none', '']:
        room_name = "Unassigned"
        
    room_str = str(room_name).strip()
    is_wide = act_w >= act_h

    tag_text = f"#{tag}" if tag else ""

    # 1. HIDE EXTREMELY TINY SPLINTERS
    if act_w <= 12 or act_h <= 12:
        return

    # 2. OVERRIDE FOR TINY PIECES (e.g. 50x50, 60x60) -> Show ONLY the ID Tag
    if act_w <= 80 and act_h <= 80:
        if tag_text:
            t = ax.text(cx, cy, tag_text, color='black', weight='bold', ha='center', va='center', fontsize=5, clip_on=True)
            t.set_clip_path(rect_patch)
        return

    # 3. LARGE PIECES
    if act_w >= 220 and act_h >= 120:
        text = f"[{room_str}]\n{piece_type}\n{w_label}x{h_label}" if piece_type else f"[{room_str}]\n{w_label}x{h_label}"
        rot = 0
        fs = 6

    # 4. HORIZONTAL STRIPS
    elif is_wide:
        display_room = room_str[:5] + ".." if len(room_str) > 5 else room_str
        if act_h >= 50:
            text = f"[{display_room}] {w_label}x{h_label}"
            fs = 4.5
        elif act_h >= 25:
            # Thin strip, check width
            if act_w >= 100:
                text = f"{w_label}x{h_label}"
                fs = 4
            else:
                text = tag_text
                fs = 4
        else:
            text = tag_text
            fs = 3.5
        rot = 0

    # 5. VERTICAL STRIPS
    else:
        display_room = room_str[:5] + ".." if len(room_str) > 5 else room_str
        if act_w >= 50:
            text = f"[{display_room}] {w_label}x{h_label}"
            fs = 4.5
        elif act_w >= 25:
            # Thin vertical strip
            if act_h >= 100:
                text = f"{w_label}x{h_label}"
                fs = 4
            else:
                text = tag_text
                fs = 4
        else:
            text = tag_text
            fs = 3.5
        rot = 90
        
    if text:
        t = ax.text(cx, cy, text, color='black', weight='bold', ha='center', va='center', fontsize=fs, rotation=rot, clip_on=True)
        t.set_clip_path(rect_patch)


# --- SIDEBAR SETTINGS ---
st.sidebar.header("1. Material Settings")
sheet_w = st.sidebar.number_input("Slab Width (mm)", value=3680)
sheet_h = st.sidebar.number_input("Slab Height (mm)", value=760)
kerf = st.sidebar.number_input("Blade Kerf (mm)", value=3)

st.sidebar.markdown("---")
st.sidebar.header("2. Optimization Rules")
is_seamless = st.sidebar.checkbox(
    "Enable Optional Scrap Recycling", 
    value=True, 
    help="Check to recycle gray waste into standard parts. Uncheck for veined colors where you want zero optional joints."
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Visual Key")
st.sidebar.markdown("🟦 **Blue:** Clean Solid Cut")
st.sidebar.markdown("🟧 **Orange:** Mandatory Joint (Oversized)")
st.sidebar.markdown("🟩 **Green:** Optional Recycled Scrap")
st.sidebar.markdown("⬜ **Gray:** Dead Waste")

# --- UI: LIST MANAGEMENT & UPLOADS ---
if 'parts' not in st.session_state: 
    st.session_state.parts = []

col_manual, col_upload = st.columns([1, 1])

with col_manual:
    st.subheader("🛠️ Manual Input")
    st.markdown("Type dimensions and click **Add** (or press Enter).")
    c_room, c1, c2, c3, c4 = st.columns([2, 2, 2, 2, 2])
    
    room = c_room.text_input("Room/Set", value="Kitchen")
    w = c1.number_input("Width (mm)", value=1000, min_value=1)
    h = c2.number_input("Height (mm)", value=350, min_value=1)
    q = c3.number_input("Quantity", value=6, min_value=1)
    
    c4.markdown("<br>", unsafe_allow_html=True) 
    if c4.button("➕ Add to List", use_container_width=True):
        st.session_state.parts.append({"room": room, "w": int(w), "h": int(h), "q": int(q)})
        st.rerun()

with col_upload:
    st.subheader("📥 Excel Import")
    uploaded_file = st.file_uploader("Upload Cut List (.xlsx)", type=["xlsx", "xls"])
    if uploaded_file is not None:
        try:
            df = pd.read_excel(uploaded_file)
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            room_col = next((c for c in df.columns if any(k in c for k in ['room', 'set', 'area', 'location', 'tag'])), None)
            w_col = next((c for c in df.columns if any(k in c for k in ['width', 'wid', 'w', 'length', 'len'])), None)
            h_col = next((c for c in df.columns if any(k in c for k in ['height', 'hei', 'h', 'depth', 'dep'])), None)
            q_col = next((c for c in df.columns if any(k in c for k in ['qty', 'quantity', 'q', 'pcs', 'count', 'amount'])), None)
            
            if w_col and h_col and q_col:
                if st.button("Load Excel Data", type="primary"):
                    for index, row in df.iterrows():
                        room_val = str(row[room_col]) if room_col and pd.notna(row[room_col]) else "Unassigned"
                        
                        w_val = pd.to_numeric(row[w_col], errors='coerce')
                        h_val = pd.to_numeric(row[h_col], errors='coerce')
                        q_val = pd.to_numeric(row[q_col], errors='coerce')
                        
                        if pd.isna(w_val) or pd.isna(h_val) or pd.isna(q_val):
                            continue
                            
                        w_val, h_val, q_val = int(w_val), int(h_val), int(q_val)
                        if w_val > 0 and h_val > 0 and q_val > 0:
                            st.session_state.parts.append({
                                "room": room_val,
                                "w": w_val, 
                                "h": h_val, 
                                "q": q_val
                            })
                    st.success("Successfully loaded valid rows from Excel cut list!")
                    st.rerun()
            else:
                st.error("⚠️ Ensure your Excel file has columns representing Width, Height, and Qty.")
        except Exception as e:
            st.error(f"Error reading file: {e}")

st.markdown("---")

# Display List with Individual Delete Buttons
if st.session_state.parts:
    st.subheader("Current Order Cut List")
    total_order_sqm = 0
    
    for i, p in enumerate(st.session_state.parts):
        sqm_per_pc = (p['w'] * p['h']) / 1_000_000
        row_total_sqm = sqm_per_pc * p['q']
        total_order_sqm += row_total_sqm
        
        col_text, col_btn = st.columns([6, 1])
        col_text.write(f"• **[{p.get('room', 'Unassigned')}]** — **{p['q']} pcs** of {p['w']}x{p['h']}mm &nbsp;&nbsp;*( {sqm_per_pc:.2f} SQM/pc | Total: {row_total_sqm:.2f} SQM )*")
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
        
        for p in st.session_state.parts:
            for _ in range(p['q']):
                id_to_room[target_id] = p.get('room', 'Unassigned')
                
                if not piece_fits_slab({'w': p['w'], 'h': p['h']}, eff_w, eff_h):
                    best_frags = get_mandatory_fragments(p['w'], p['h'], eff_w, eff_h)
                    mandatory_oversized.append({
                        'id': target_id, 'w': p['w'], 'h': p['h'], 'frags': best_frags
                    })
                else:
                    standard_targets.append({'id': target_id, 'w': p['w'], 'h': p['h']})
                target_id += 1
                
        final_slabs = 0
        final_solid_count = 0
        final_recycled_count = 0
        final_rects = []
        assembled_pieces_data = [] 
        
        slab_area = sheet_w * sheet_h
        theoretical_min_slabs = max(1, math.ceil(true_delivered_area / slab_area))
        max_test_slabs = theoretical_min_slabs + 25 
        
        with st.spinner('Calculating tightest factory layout... this may take a few seconds...'):
            for test_slabs in range(theoretical_min_slabs, max_test_slabs):
                
                base_rects_input = []
                for t in standard_targets:
                    base_rects_input.append({'w': t['w'], 'h': t['h'], 'rid': f"solid_{t['id']}_{t['w']}_{t['h']}"})
                for mt in mandatory_oversized:
                    for f_idx, f in enumerate(mt['frags']):
                        base_rects_input.append({'w': f['w'], 'h': f['h'], 'rid': f"mand_{mt['id']}_{mt['w']}_{mt['h']}_{f_idx}"})
                        
                packer_base, is_base_success = can_pack(base_rects_input, test_slabs, sheet_w, sheet_h, kerf)
                base_rects = packer_base.rect_list()
                
                packed_solid_ids = set([int(str(r[5]).split('_')[1]) for r in base_rects if str(r[5]).startswith('solid')])
                packed_mand_rids = set([str(r[5]) for r in base_rects if str(r[5]).startswith('mand')])
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
                    
                    current_packed_recycled_frags = []
                    all_recycled_packed = True
                    final_packer_instance = packer_base
                    
                    for target in missing_standard:
                        target_packed = False
                        
                        for strategy in SPLIT_STRATEGIES:
                            frags = generate_fragments(target['w'], target['h'], strategy)
                            if any(not piece_fits_slab(f, eff_w, eff_h) for f in frags):
                                continue
                                
                            test_layout = []
                            for tid in packed_solid_ids:
                                t = next(x for x in standard_targets if x['id'] == tid)
                                test_layout.append({'w': t['w'], 'h': t['h'], 'rid': f"solid_{t['id']}_{t['w']}_{t['h']}"})
                            for mt in mandatory_oversized:
                                for f_idx, f in enumerate(mt['frags']):
                                    test_layout.append({'w': f['w'], 'h': f['h'], 'rid': f"mand_{mt['id']}_{mt['w']}_{mt['h']}_{f_idx}"})
                            for f_tuple in current_packed_recycled_frags:
                                test_layout.append({'w': f_tuple['w'], 'h': f_tuple['h'], 'rid': f_tuple['rid']})
                            for f_idx, f in enumerate(frags):
                                test_layout.append({'w': f['w'], 'h': f['h'], 'rid': f"rec_{target['id']}_{target['w']}_{target['h']}_{f_idx}"})
                                
                            test_packer, is_test_success = can_pack(test_layout, test_slabs, sheet_w, sheet_h, kerf)
                            
                            if is_test_success:
                                for f_idx, f in enumerate(frags):
                                    current_packed_recycled_frags.append({
                                        'w': f['w'], 'h': f['h'], 
                                        'rid': f"rec_{target['id']}_{target['w']}_{target['h']}_{f_idx}",
                                        'layout': f 
                                    })
                                final_packer_instance = test_packer
                                target_packed = True
                                break 
                                
                        if not target_packed:
                            all_recycled_packed = False
                            break 
                            
                    if all_recycled_packed:
                        final_slabs = test_slabs
                        final_solid_count = len(packed_solid_ids)
                        final_recycled_count = len(missing_standard)
                        final_rects = final_packer_instance.rect_list()
                        break

        if final_slabs == 0:
            final_slabs = test_slabs

        total_glue_length_mm = 0
        
        for mt in mandatory_oversized:
            seam_length = mt['h'] if mt['w'] >= mt['h'] else mt['w']
            joints_count = len(mt['frags']) - 1
            total_glue_length_mm += (joints_count * seam_length)
            assembled_pieces_data.append({'id': mt['id'], 'w': mt['w'], 'h': mt['h'], 'frags': mt['frags'], 'type': 'Mandatory'})

        if final_recycled_count > 0:
            for t in missing_standard:
                t_frags = [f['layout'] for f in current_packed_recycled_frags if str(f['rid']).startswith(f"rec_{t['id']}_")]
                if t_frags:
                    seam_length = t['h'] if t['w'] >= t['h'] else t['w']
                    joints_count = len(t_frags) - 1
                    total_glue_length_mm += (joints_count * seam_length)
                    assembled_pieces_data.append({'id': t['id'], 'w': t['w'], 'h': t['h'], 'frags': t_frags, 'type': 'Recycled'})
                    
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
        
        st.success(f"📋 **Mixed Batch Output:** {final_solid_count} pieces clean-cut. {len(mandatory_oversized)} mandatory joints applied. {final_recycled_count} pieces optionally recycled.")

        # Excel Export
        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
            pd.DataFrame(st.session_state.parts).to_excel(writer, index=False, sheet_name='CutList')
        st.download_button("📥 Export Cut List to Excel", data=output_excel.getvalue(), file_name="S&C_Asia_Cut_List.xlsx", mime="application/vnd.ms-excel")

        # Visuals & PDF Generation
        pdf_buffer = io.BytesIO()
        with PdfPages(pdf_buffer) as pdf:
            
            # --- PAGE 1: PRODUCTION & EFFICIENCY REPORT SUMMARY ---
            fig_sum, ax_sum = plt.subplots(figsize=(8, 6))
            ax_sum.axis('off')
            
            summary_header = "S&C ASIA | PRODUCTION & MATERIAL EFFICIENCY REPORT"
            summary_content = (
                f"====================================================\n"
                f" PROJECT METRICS SUMMARY\n"
                f"====================================================\n\n"
                f" • Total Slabs Pulled        : {final_slabs} Slabs\n"
                f" • Total Target Area         : {total_project_sqm:.2f} SQM\n"
                f" • True Material Yield       : {yield_percentage:.1f}%\n"
                f" • Estimated Glue Required   : {total_glue_length_cm:.1f} CM\n\n"
                f"----------------------------------------------------\n"
                f" BATCH COMPOSITION BREAKDOWN\n"
                f"----------------------------------------------------\n"
                f" • Solid Clean-Cut Pieces    : {final_solid_count}\n"
                f" • Mandatory Jointed Pieces  : {len(mandatory_oversized)}\n"
                f" • Optionally Recycled Pieces: {final_recycled_count}\n"
            )
            ax_sum.text(0.05, 0.85, summary_header, fontsize=12, weight='bold', color='#1f4e78', va='top')
            ax_sum.text(0.05, 0.70, summary_content, fontsize=10, family='monospace', va='top')
            
            pdf.savefig(fig_sum, bbox_inches='tight')
            plt.close(fig_sum)

            # --- SLAB CUTTING MAPS WITH SMART LEGEND ---
            st.subheader("Factory Floor: Cutting Map")
            for bin_idx in range(final_slabs):
                # We create a layout with 2 rows: Top for the Slab Drawing, Bottom for the Legend/Remarks
                fig, (ax, ax_leg) = plt.subplots(2, 1, figsize=(10, 4.5), gridspec_kw={'height_ratios': [3.5, 1]})
                ax.add_patch(patches.Rectangle((0,0), sheet_w, sheet_h, facecolor='#e0e0e0', edgecolor='black', lw=2))
                
                bin_rects = [r for r in final_rects if r[0] == bin_idx]
                
                # Pre-process unique parts to assign short Tags (#1, #2, etc.)
                unique_parts = {}
                tag_counter = 1
                
                for r in bin_rects:
                    rid = str(r[5])
                    parts = rid.split('_')
                    t_id = int(parts[1])
                    room_name = id_to_room.get(t_id, "Unassigned")
                    act_w, act_h = r[3] - kerf, r[4] - kerf
                    
                    if rid.startswith('solid'):
                        p_type = "SOLID"
                        target_w, target_h = parts[2], parts[3]
                    elif rid.startswith('mand'):
                        p_type = "MAND. FRAG"
                        target_w, target_h = str(int(act_w)), str(int(act_h))
                    elif rid.startswith('rec'):
                        p_type = "FRAG"
                        target_w, target_h = str(int(act_w)), str(int(act_h))
                        
                    key = (room_name, p_type, target_w, target_h)
                    if key not in unique_parts:
                        unique_parts[key] = {'tag': str(tag_counter), 'count': 0}
                        tag_counter += 1
                    unique_parts[key]['count'] += 1
                
                # Plot the rectangles and apply labels
                for r in bin_rects:
                    rx, ry, rw, rh, rid = r[1], r[2], r[3], r[4], str(r[5])
                    act_w, act_h = rw - kerf, rh - kerf
                    
                    parts = rid.split('_')
                    t_id = int(parts[1])
                    room_name = id_to_room.get(t_id, "Unassigned")
                    
                    if rid.startswith('solid'):
                        target_w, target_h = parts[2], parts[3]
                        key = (room_name, "SOLID", target_w, target_h)
                        tag = unique_parts[key]['tag']
                        
                        patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#2c3e50', facecolor='#85c1e9', lw=1.5)
                        ax.add_patch(patch)
                        draw_smart_label(ax, room_name, "SOLID", target_w, target_h, rx, ry, act_w, act_h, patch, tag)
                        
                    elif rid.startswith('mand'):
                        target_w, target_h = str(int(act_w)), str(int(act_h))
                        key = (room_name, "MAND. FRAG", target_w, target_h)
                        tag = unique_parts[key]['tag']
                        
                        patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#d35400', facecolor='#f5b041', lw=1.5, linestyle='--')
                        ax.add_patch(patch)
                        draw_smart_label(ax, room_name, "MAND.", target_w, target_h, rx, ry, act_w, act_h, patch, tag)
                        
                    elif rid.startswith('rec'):
                        target_w, target_h = str(int(act_w)), str(int(act_h))
                        key = (room_name, "FRAG", target_w, target_h)
                        tag = unique_parts[key]['tag']
                        
                        patch = patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#1e8449', facecolor='#82e0aa', lw=1.5, linestyle='--')
                        ax.add_patch(patch)
                        draw_smart_label(ax, room_name, "FRAG", target_w, target_h, rx, ry, act_w, act_h, patch, tag)
                
                ax.set_xlim(0, sheet_w)
                ax.set_ylim(0, sheet_h)
                ax.set_aspect('equal')
                ax.axis('off')
                ax.set_title(f"Slab {bin_idx + 1}", fontsize=11, weight='bold')
                
                # --- FORMAT AND RENDER THE LEGEND SECTION BELOW THE SLAB ---
                ax_leg.axis('off')
                
                sorted_keys = sorted(unique_parts.keys(), key=lambda k: int(unique_parts[k]['tag']))
                legend_lines = []
                for k in sorted_keys:
                    tag = unique_parts[k]['tag']
                    count = unique_parts[k]['count']
                    room, ptype, tw, th = k
                    legend_lines.append(f"#{tag} - [{room}] {tw}x{th}mm ({ptype}) : {count} pcs")
                    
                # Distribute text into 3 clean columns
                col_size = math.ceil(len(legend_lines) / 3) if len(legend_lines) > 0 else 1
                cols = [legend_lines[i:i+col_size] for i in range(0, len(legend_lines), col_size)]
                
                ax_leg.text(0, 1.0, f"Remarks / Parts in Slab {bin_idx + 1}:", fontsize=9, weight='bold', va='top', ha='left')
                
                for c_idx, col_items in enumerate(cols):
                    col_text = "\n".join(col_items)
                    ax_leg.text(c_idx * 0.33, 0.75, col_text, fontsize=7, family='monospace', va='top', ha='left')

                plt.tight_layout()
                st.pyplot(fig)
                pdf.savefig(fig, bbox_inches='tight')
                plt.close(fig)

            # --- ASSEMBLY MAPS ---
            if assembled_pieces_data:
                st.markdown("---")
                st.subheader("🧩 Glue Jointing Assembly Maps")
                
                for asm in assembled_pieces_data:
                    fig2, ax2 = plt.subplots(figsize=(6, 2.5))
                    ax2.add_patch(patches.Rectangle((0,0), asm['w'], asm['h'], facecolor='#f9f9f9', edgecolor='black', lw=2))
                    
                    room_name = id_to_room.get(asm['id'], "Unassigned")
                    joint_count = len(asm['frags']) - 1
                    edge_c = '#d35400' if asm['type'] == 'Mandatory' else '#1e8449'
                    face_c = '#f5b041' if asm['type'] == 'Mandatory' else '#82e0aa'
                    
                    for f in asm['frags']:
                        patch = patches.Rectangle((f['x'], f['y']), f['w'], f['h'], edgecolor=edge_c, linestyle='--', facecolor=face_c, alpha=0.6, lw=1.5)
                        ax2.add_patch(patch)
                        draw_smart_label(ax2, room_name, "", int(f['w']), int(f['h']), f['x'], f['y'], f['w'], f['h'], patch, tag="")
                    
                    ax2.set_xlim(0, asm['w'])
                    ax2.set_ylim(0, asm['h'])
                    ax2.set_aspect('equal')
                    ax2.axis('off')
                    ax2.set_title(f"[{room_name}] Assembled: {asm['w']}x{asm['h']}mm | {asm['type']} | {joint_count} Joints", fontsize=10)
                    st.pyplot(fig2)
                    pdf.savefig(fig2, bbox_inches='tight')
                    plt.close(fig2)

        st.markdown("---")
        st.download_button("📄 Export Production PDF", pdf_buffer.getvalue(), "S&C_Asia_Production_Map.pdf", "application/pdf")
