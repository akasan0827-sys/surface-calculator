import streamlit as st
from rectpack import newPacker
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import io
import math
from matplotlib.backends.backend_pdf import PdfPages

st.set_page_config(layout="wide", page_title="Solid Surface Pro")
st.title("📐 Solid Surface Production & Deep-Optimization Tool")

# --- EXPANDED FACTORY SPLIT STRATEGIES ---
# 23 different slicing ratios to guarantee we find the perfect fit for the scrap voids.
SPLIT_STRATEGIES = [
    # 1 JOINT (2 Pieces)
    [0.5, 0.5], [0.55, 0.45], [0.6, 0.4], [0.65, 0.35],
    [0.7, 0.3], [0.75, 0.25], [0.8, 0.2], [0.85, 0.15],
    [0.9, 0.1], [0.95, 0.05], [0.98, 0.02],
    # 2 JOINTS (3 Pieces) - Fallbacks
    [0.34, 0.33, 0.33], [0.4, 0.3, 0.3], [0.4, 0.4, 0.2],
    [0.45, 0.45, 0.1], [0.5, 0.25, 0.25], [0.5, 0.3, 0.2],
    [0.5, 0.4, 0.1], [0.6, 0.2, 0.2], [0.6, 0.3, 0.1],
    [0.7, 0.15, 0.15], [0.7, 0.2, 0.1], [0.8, 0.1, 0.1]
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
    """Checks if a piece physically fits on the slab (allowing for 90-degree rotation)."""
    fits_standard = (f['w'] <= eff_w and f['h'] <= eff_h)
    fits_rotated = (f['h'] <= eff_w and f['w'] <= eff_h)
    return fits_standard or fits_rotated

def get_mandatory_fragments(w, h, eff_w, eff_h):
    for strategy in SPLIT_STRATEGIES:
        frags = generate_fragments(w, h, strategy)
        if all(piece_fits_slab(f, eff_w, eff_h) for f in frags):
            return frags
    return generate_fragments(w, h, [0.34, 0.33, 0.33])

# --- CLOUD-SAFE HEURISTIC PACKER ---
def can_pack(rects_to_pack, num_slabs, sheet_w, sheet_h, kerf):
    """Attempts to pack the layout cleanly."""
    p = newPacker(rotation=True)
    p.add_bin(sheet_w, sheet_h, count=num_slabs)
    for r in rects_to_pack:
        p.add_rect(r['w'] + kerf, r['h'] + kerf, rid=r['rid'])
    p.pack()
    
    if len(p.rect_list()) == len(rects_to_pack):
        return p, True 
    return p, False 

# --- SIDEBAR SETTINGS ---
st.sidebar.header("1. Material Settings")
sheet_w = st.sidebar.number_input("Slab Width (mm)", value=3680)
sheet_h = st.sidebar.number_input("Slab Height (mm)", value=760)
kerf = st.sidebar.number_input("Blade Kerf (mm)", value=3)

st.sidebar.markdown("---")
st.sidebar.header("2. Optimization Rules")
is_seamless = st.sidebar.checkbox(
    "Enable Deep Scrap Recycling", 
    value=True, 
    help="Hunts for tightest yields using up to 2-joints per recycled piece."
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Visual Key")
st.sidebar.markdown("🟦 **Blue:** Clean Solid Cut")
st.sidebar.markdown("🟩 **Green:** Jointed / Fragment Cut")
st.sidebar.markdown("⬜ **Gray:** Dead Waste")

# --- INPUT AREA ---
st.header("Build Target Order List")
if 'parts' not in st.session_state: 
    st.session_state.parts = []
    
with st.form("input", clear_on_submit=True):
    c1, c2, c3 = st.columns(3)
    w = c1.number_input("Width (mm)", value=1000, min_value=1)
    h = c2.number_input("Height (mm)", value=350, min_value=1)
    q = c3.number_input("Quantity", value=6, min_value=1)
    
    if st.form_submit_button("Add Size to Cut List"): 
        st.session_state.parts.append({"w": w, "h": h, "q": q})

if st.session_state.parts:
    st.subheader("Current Order Cut List")
    total_order_sqm = 0
    
    for idx, p in enumerate(st.session_state.parts):
        sqm_per_pc = (p['w'] * p['h']) / 1_000_000
        row_total_sqm = sqm_per_pc * p['q']
        total_order_sqm += row_total_sqm
        st.write(f"• **{p['q']} pcs** of {p['w']}x{p['h']}mm &nbsp;&nbsp;*( {sqm_per_pc:.2f} SQM/pc | Total: {row_total_sqm:.2f} SQM )*")
        
    st.info(f"📐 **Total Project Area:** {total_order_sqm:.2f} SQM")
        
    col_run, col_clear = st.columns([1, 5])
    run_calc = col_run.button("Run Deep Heuristic Optimizer", type="primary")
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
            for _ in range(p['q']):
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
        max_test_slabs = theoretical_min_slabs + 30 
        
        with st.spinner('Running deep heuristic permutations... this may take a few seconds...'):
            for test_slabs in range(theoretical_min_slabs, max_test_slabs):
                
                # --- BASE PACK (Solid + Mandatory) ---
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
                    continue # Not enough room for mandatories, bump up slab count
                    
                if len(packed_solid_ids) == len(standard_targets):
                    final_slabs = test_slabs
                    final_solid_count = len(standard_targets)
                    final_recycled_count = 0
                    final_rects = base_rects
                    break
                    
                # --- OPTIONAL DEEP RECYCLING LOOP ---
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
                            
                            # Verify physical possibility of the cuts before running heavy math
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

        # --- DATA AGGREGATION & GLUE CALCULATION ---
        total_glue_length_mm = 0
        
        for mt in mandatory_oversized:
            seam_length = mt['h'] if mt['w'] >= mt['h'] else mt['w']
            joints_count = len(mt['frags']) - 1
            total_glue_length_mm += (joints_count * seam_length)
            assembled_pieces_data.append({
                'id': mt['id'], 'w': mt['w'], 'h': mt['h'], 'frags': mt['frags'], 'type': 'Mandatory (Oversized)'
            })

        if final_recycled_count > 0:
            for t in missing_standard:
                t_frags = [f['layout'] for f in current_packed_recycled_frags if str(f['rid']).startswith(f"rec_{t['id']}_")]
                if t_frags:
                    seam_length = t['h'] if t['w'] >= t['h'] else t['w']
                    joints_count = len(t_frags) - 1
                    total_glue_length_mm += (joints_count * seam_length)
                    assembled_pieces_data.append({
                        'id': t['id'], 'w': t['w'], 'h': t['h'], 'frags': t_frags, 'type': 'Recycled Scrap'
                    })
                    
        total_glue_length_cm = total_glue_length_mm / 10.0

        # --- YIELD CALCULATION ---
        total_material_area = final_slabs * sheet_w * sheet_h
        yield_percentage = (true_delivered_area / total_material_area) * 100 if total_material_area > 0 else 0
        total_project_sqm = true_delivered_area / 1_000_000

        # --- UI REPORT ---
        st.markdown("---")
        st.header("3. Production & Material Efficiency Report")
        
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("📦 Slabs Pulled", f"{final_slabs} Slabs")
        col_m2.metric("📐 Total Target Area", f"{total_project_sqm:.2f} SQM")
        col_m3.metric("🔥 True Material Yield", f"{yield_percentage:.1f}%")
        col_m4.metric("💧 Est. Glue Required", f"{total_glue_length_cm:.1f} CM")
        
        st.success(f"📋 **Mixed Batch Output:** {final_solid_count} pieces clean-cut. {len(mandatory_oversized)} mandatory joints applied. {final_recycled_count} pieces recycled dynamically.")

        # --- VISUALIZATION & PDF EXPORT ---
        pdf_buffer = io.BytesIO()
        with PdfPages(pdf_buffer) as pdf:
            st.subheader("Factory Floor: Cutting Map")
            
            for bin_idx in range(final_slabs):
                fig, ax = plt.subplots(figsize=(10, 3))
                ax.add_patch(patches.Rectangle((0,0), sheet_w, sheet_h, facecolor='#e0e0e0', edgecolor='black', lw=2))
                
                bin_rects = [r for r in final_rects if r[0] == bin_idx]
                for r in bin_rects:
                    rx, ry, rw, rh, rid = r[1], r[2], r[3], r[4], str(r[5])
                    act_w, act_h = rw - kerf, rh - kerf
                    
                    if rid.startswith('solid'):
                        parts = rid.split('_')
                        target_w, target_h = parts[2], parts[3]
                        ax.add_patch(patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#003366', facecolor='#66b3ff', lw=1.5))
                        ax.text(rx + act_w/2, ry + act_h/2, f"SOLID\n{target_w}x{target_h}", color='black', weight='bold', ha='center', va='center', fontsize=8)
                    else:
                        parts = rid.split('_')
                        target_w, target_h = parts[2], parts[3]
                        ax.add_patch(patches.Rectangle((rx, ry), act_w, act_h, edgecolor='#006600', facecolor='#99ff99', lw=1.5, linestyle='--'))
                        ax.text(rx + act_w/2, ry + act_h/2, f"FRAG\n{int(act_w)}x{int(act_h)}\n(For {target_w}x{target_h})", color='black', ha='center', va='center', fontsize=7)
                
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
                st.info("Gather the specific green 'FRAG' pieces from the slabs to assemble these final jointed products.")
                
                for asm in assembled_pieces_data:
                    fig2, ax2 = plt.subplots(figsize=(6, 2.5))
                    ax2.add_patch(patches.Rectangle((0,0), asm['w'], asm['h'], facecolor='#f9f9f9', edgecolor='black', lw=2))
                    
                    joint_count = len(asm['frags']) - 1
                    
                    for f in asm['frags']:
                        ax2.add_patch(patches.Rectangle((f['x'], f['y']), f['w'], f['h'], edgecolor='red', linestyle='--', facecolor='#99ff99', alpha=0.6, lw=1.5))
                        ax2.text(f['x'] + f['w']/2, f['y'] + f['h']/2, f"{int(f['w'])}x{int(f['h'])}", color='black', weight='bold', ha='center', va='center', fontsize=9)
                    
                    ax2.set_xlim(0, asm['w'])
                    ax2.set_ylim(0, asm['h'])
                    ax2.set_aspect('equal')
                    ax2.axis('off')
                    ax2.set_title(f"Assembled: {asm['w']}x{asm['h']}mm | {asm['type']} | {joint_count} Joints", fontsize=10)
                    
                    st.pyplot(fig2)
                    pdf.savefig(fig2, bbox_inches='tight')
                    plt.close(fig2)

        st.markdown("---")
        st.download_button("📄 Export Production PDF", pdf_buffer.getvalue(), "mixed_batch_production.pdf", "application/pdf")
