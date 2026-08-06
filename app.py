import streamlit as st
import pandas as pd
from rectpack import newPacker
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import io
import math
from matplotlib.backends.backend_pdf import PdfPages

# --- PAGE CONFIG & S&C ASIA BRANDING ---
# Using the logo as the actual web browser tab icon
st.set_page_config(layout="wide", page_title="S&C Asia | Production Optimizer", page_icon="logo.png")

try:
    # Places the logo cleanly in the top-left corner of the interface
    st.logo("logo.png")
except FileNotFoundError:
    pass

# Clean, professional title without emojis
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

def mandatory_glue_length_mm(w, h, eff_w, eff_h):
    """
    Total glue-seam length needed to reassemble a piece that was cut as an
    R x C grid of fragments (R rows from the height axis, C columns from the
    width axis) back to its full w x h size.

    Assembly order: glue the R fragments in each column into a full-height
    strip first (R-1 seams per column, each running the full column width),
    then glue the C strips together (C-1 seams, each running the full
    height h). This matches exactly what get_mandatory_fragments() builds,
    and correctly reduces to the old "short side x (frag_count-1)" formula
    when only one axis overflows (R==1 or C==1).
    """
    cols = math.ceil(w / eff_w)
    rows = math.ceil(h / eff_h)
    return (rows - 1) * w + (cols - 1) * h

def can_pack(rects_to_pack, num_slabs, sheet_w, sheet_h, kerf):
    p = newPacker(rotation=True)
    p.add_bin(sheet_w, sheet_h, count=num_slabs)
    for r in rects_to_pack:
        p.add_rect(r['w'] + kerf, r['h'] + kerf, rid=r['rid'])
    p.pack()
    return p, len(p.rect_list()) == len(rects_to_pack)

def draw_labeled_rect(ax, x, y, w, h, edge_color, face_color, lines, sheet_w, sheet_h,
                       fig_w_in, fig_h_in, linestyle='-'):
    """
    Draws a piece rectangle and a text label sized/truncated to fit inside it,
    and clips the text to the rectangle's own boundary so it can never bleed
    into a neighboring piece and become unreadable.
    `lines` should be ordered from LEAST important (first) to MOST important
    (last) - if there isn't room for every line, the least-important ones
    are dropped first and the last line is always kept.
    """
    rect_patch = patches.Rectangle((x, y), w, h, edgecolor=edge_color, facecolor=face_color,
                                    lw=1.5, linestyle=linestyle)
    ax.add_patch(rect_patch)

    pts_per_mm_x = (fig_w_in * 72) / sheet_w
    pts_per_mm_y = (fig_h_in * 72) / sheet_h
    pts_per_mm = min(pts_per_mm_x, pts_per_mm_y)

    fontsize = max(4.5, min(9, min(w, h) * pts_per_mm * 0.16))

    line_height_mm = (fontsize * 1.35) / pts_per_mm_y
    max_lines = max(1, int(h / line_height_mm))
    shown_lines = lines[-max_lines:] if len(lines) > max_lines else lines

    txt = ax.text(x + w / 2, y + h / 2, "\n".join(shown_lines), color='black', weight='bold',
                   ha='center', va='center', fontsize=fontsize, linespacing=1.3)
    txt.set_clip_path(rect_patch)

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
    c0, c1, c2, c3, c4 = st.columns([2, 1.4, 1.4, 1.1, 1.7])

    room = c0.text_input("Room / Set", value="", placeholder="e.g. Kitchen")
    w = c1.number_input("Width (mm)", value=1000, min_value=1)
    h = c2.number_input("Height (mm)", value=350, min_value=1)
    q = c3.number_input("Quantity", value=6, min_value=1)

    c4.markdown("<br>", unsafe_allow_html=True)
    if c4.button("➕ Add to List", use_container_width=True):
        st.session_state.parts.append({
            "room": room.strip() or "Unassigned",
            "w": int(w), "h": int(h), "q": int(q)
        })
        st.rerun()

with col_upload:
    st.subheader("📥 Excel Import")
    uploaded_file = st.file_uploader("Upload Cut List (.xlsx)", type=["xlsx", "xls"])
    if uploaded_file is not None:
        try:
            df = pd.read_excel(uploaded_file)

            w_col = next((c for c in df.columns if 'wid' in str(c).lower() or 'w' == str(c).lower()), None)
            h_col = next((c for c in df.columns if 'hei' in str(c).lower() or 'h' == str(c).lower()), None)
            q_col = next((c for c in df.columns if 'qty' in str(c).lower() or 'q' == str(c).lower() or 'quan' in str(c).lower()), None)
            room_col = next((c for c in df.columns if any(k in str(c).lower() for k in ['room', 'area', 'zone', 'set'])), None)

            if w_col and h_col and q_col:
                if not room_col:
                    st.info("ℹ️ No 'Room' column detected — imported pieces will be tagged as 'Unassigned'. Add a 'Room' column to your Excel file to tag them automatically.")
                if st.button("Load Excel Data", type="primary"):
                    for index, row in df.iterrows():
                        room_val = str(row[room_col]).strip() if room_col and pd.notna(row[room_col]) else "Unassigned"
                        st.session_state.parts.append({
                            "room": room_val or "Unassigned",
                            "w": int(row[w_col]),
                            "h": int(row[h_col]),
                            "q": int(row[q_col])
                        })
                    st.rerun()
            else:
                st.error("⚠️ Ensure your Excel file has columns named 'Width', 'Height', and 'Qty'. A 'Room' column is optional.")
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
        room_label = p.get('room', 'Unassigned')

        col_text, col_btn = st.columns([6, 1])
        col_text.write(f"• 🏠 **{room_label}** — **{p['q']} pcs** of {p['w']}x{p['h']}mm &nbsp;&nbsp;*( {sqm_per_pc:.2f} SQM/pc | Total: {row_total_sqm:.2f} SQM )*")
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

        for p in st.session_state.parts:
            room_tag = p.get('room', 'Unassigned')
            for _ in range(p['q']):
                if not piece_fits_slab({'w': p['w'], 'h': p['h']}, eff_w, eff_h):
                    best_frags = get_mandatory_fragments(p['w'], p['h'], eff_w, eff_h)
                    mandatory_oversized.append({
                        'id': target_id, 'w': p['w'], 'h': p['h'], 'frags': best_frags, 'room': room_tag
                    })
                else:
                    standard_targets.append({'id': target_id, 'w': p['w'], 'h': p['h'], 'room': room_tag})
                target_id += 1

        id_to_room = {}
        for t in standard_targets:
            id_to_room[t['id']] = t['room']
        for mt in mandatory_oversized:
            id_to_room[mt['id']] = mt['room']

        final_slabs = 0
        final_solid_count = 0
        final_recycled_count = 0
        final_rects = []
        assembled_pieces_data = []
        missing_standard = []
        current_packed_recycled_frags = []
        solution_found = False

        slab_area = sheet_w * sheet_h
        theoretical_min_slabs = max(1, math.ceil(true_delivered_area / slab_area))
        max_test_slabs = theoretical_min_slabs + 25

        with st.spinner('Calculating tightest factory layout... this may take a few seconds...'):
            for test_slabs in range(theoretical_min_slabs, max_test_slabs):

                # --- BASE PACK ---
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
                    solution_found = True
                    break

                # --- DEEP RECYCLING LOOP ---
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
                        solution_found = True
                        break

        if not solution_found:
            st.error(
                f"⚠️ Could not find a valid cutting layout within {max_test_slabs - 1} slabs. "
                "This order may be too large or contain an awkward mix of sizes for the "
                "heuristic optimizer. Try splitting the order into smaller batches, or "
                "disable/enable 'Optional Scrap Recycling' and re-run."
            )
            st.stop()

        total_glue_length_mm = 0
        total_mandatory_joints = 0

        for mt in mandatory_oversized:
            seam_mm = mandatory_glue_length_mm(mt['w'], mt['h'], eff_w, eff_h)
            total_glue_length_mm += seam_mm
            total_mandatory_joints += len(mt['frags']) - 1
            assembled_pieces_data.append({
                'id': mt['id'], 'w': mt['w'], 'h': mt['h'], 'frags': mt['frags'],
                'type': 'Mandatory Joint', 'room': mt['room']
            })

        if final_recycled_count > 0:
            for t in missing_standard:
                t_frags = [f['layout'] for f in current_packed_recycled_frags if str(f['rid']).startswith(f"rec_{t['id']}_")]
                if t_frags:
                    seam_length = t['h'] if t['w'] >= t['h'] else t['w']
                    joints_count = len(t_frags) - 1
                    total_glue_length_mm += (joints_count * seam_length)
                    total_mandatory_joints += joints_count
                    assembled_pieces_data.append({
                        'id': t['id'], 'w': t['w'], 'h': t['h'], 'frags': t_frags,
                        'type': 'Recycled Scrap', 'room': t['room']
                    })

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

        st.success(
            f"📋 **Mixed Batch Output:** {final_solid_count} pieces clean-cut. "
            f"{len(mandatory_oversized)} piece(s) required mandatory joining "
            f"({total_mandatory_joints} glue seam(s) total). "
            f"{final_recycled_count} pieces optionally recycled."
        )

        # Excel Export
        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
            pd.DataFrame(st.session_state.parts).to_excel(writer, index=False, sheet_name='CutList')
        st.download_button("📥 Export Cut List to Excel", data=output_excel.getvalue(), file_name="S&C_Asia_Cut_List.xlsx", mime="application/vnd.ms-excel")

        # Visuals
        FIG_W_IN, FIG_H_IN = 10, 3
        ASM_FIG_W_IN, ASM_FIG_H_IN = 6, 2.5

        pdf_buffer = io.BytesIO()
        with PdfPages(pdf_buffer) as pdf:
            st.subheader("Factory Floor: Cutting Map")

            for bin_idx in range(final_slabs):
                fig, ax = plt.subplots(figsize=(FIG_W_IN, FIG_H_IN))
                ax.add_patch(patches.Rectangle((0,0), sheet_w, sheet_h, facecolor='#e0e0e0', edgecolor='black', lw=2))

                bin_rects = [r for r in final_rects if r[0] == bin_idx]
                for r in bin_rects:
                    rx, ry, rw, rh, rid = r[1], r[2], r[3], r[4], str(r[5])
                    act_w, act_h = rw - kerf, rh - kerf
                    parts_ = rid.split('_')
                    piece_id = int(parts_[1])
                    room_name = id_to_room.get(piece_id, 'Unassigned')

                    if rid.startswith('solid'):
                        target_w, target_h = parts_[2], parts_[3]
                        lines = ["SOLID", room_name, f"{target_w}x{target_h}"]
                        draw_labeled_rect(ax, rx, ry, act_w, act_h, '#2c3e50', '#85c1e9', lines,
                                           sheet_w, sheet_h, FIG_W_IN, FIG_H_IN)

                    elif rid.startswith('mand'):
                        target_w, target_h = parts_[2], parts_[3]
                        lines = ["MANDATORY", room_name, f"(For {target_w}x{target_h})", f"{int(act_w)}x{int(act_h)}"]
                        draw_labeled_rect(ax, rx, ry, act_w, act_h, '#d35400', '#f5b041', lines,
                                           sheet_w, sheet_h, FIG_W_IN, FIG_H_IN, linestyle='--')

                    elif rid.startswith('rec'):
                        target_w, target_h = parts_[2], parts_[3]
                        lines = ["FRAG", room_name, f"(For {target_w}x{target_h})", f"{int(act_w)}x{int(act_h)}"]
                        draw_labeled_rect(ax, rx, ry, act_w, act_h, '#1e8449', '#82e0aa', lines,
                                           sheet_w, sheet_h, FIG_W_IN, FIG_H_IN, linestyle='--')

                ax.set_xlim(0, sheet_w)
                ax.set_ylim(0, sheet_h)
                ax.set_aspect('equal')
                ax.axis('off')
                ax.set_title(f"Slab {bin_idx + 1}", fontsize=11, weight='bold')
                st.pyplot(fig)
                pdf.savefig(fig, bbox_inches='tight')
                plt.close(fig)

            if assembled_pieces_data:
                st.markdown("---")
                st.subheader("🧩 Glue Jointing Assembly Maps")

                for asm in assembled_pieces_data:
                    fig2, ax2 = plt.subplots(figsize=(ASM_FIG_W_IN, ASM_FIG_H_IN))
                    ax2.add_patch(patches.Rectangle((0,0), asm['w'], asm['h'], facecolor='#f9f9f9', edgecolor='black', lw=2))

                    joint_count = len(asm['frags']) - 1
                    edge_c = '#d35400' if asm['type'] == 'Mandatory Joint' else '#1e8449'
                    face_c = '#f5b041' if asm['type'] == 'Mandatory Joint' else '#82e0aa'

                    for f in asm['frags']:
                        lines = [f"{int(f['w'])}x{int(f['h'])}"]
                        draw_labeled_rect(ax2, f['x'], f['y'], f['w'], f['h'], edge_c, face_c, lines,
                                           asm['w'], asm['h'], ASM_FIG_W_IN, ASM_FIG_H_IN, linestyle='--')

                    ax2.set_xlim(0, asm['w'])
                    ax2.set_ylim(0, asm['h'])
                    ax2.set_aspect('equal')
                    ax2.axis('off')
                    ax2.set_title(
                        f"Room: {asm['room']} | Assembled: {asm['w']}x{asm['h']}mm | {asm['type']} | {joint_count} Joints",
                        fontsize=10
                    )
                    st.pyplot(fig2)
                    pdf.savefig(fig2, bbox_inches='tight')
                    plt.close(fig2)

        st.markdown("---")
        st.download_button("📄 Export Production PDF", pdf_buffer.getvalue(), "S&C_Asia_Production_Map.pdf", "application/pdf")
