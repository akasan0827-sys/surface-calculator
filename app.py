import streamlit as st
from rectpack import newPacker
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import io
import math
from matplotlib.backends.backend_pdf import PdfPages

st.set_page_config(layout="wide", page_title="Solid Surface Pro")
st.title("📐 Solid Surface Production & Mixed-Batch Optimizer")

# --- SMART SPLIT STRATEGIES ---
SPLIT_STRATEGIES = [
    [0.5, 0.5],       
    [0.6, 0.4],       
    [0.75, 0.25],     
    [0.85, 0.15],     
    [0.95, 0.05],     
    [0.98, 0.02],     
    [0.33, 0.33, 0.34],
    [0.4, 0.4, 0.2],
    [0.45, 0.45, 0.1]
]

def generate_fragments(w, h, strategy_ratios):
    """Splits the piece along the longest edge based on the given ratio array."""
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

def get_mandatory_fragments(w, h, eff_w, eff_h):
    """Finds the best split strategy for pieces that are physically larger than the raw slab."""
    for strategy in SPLIT_STRATEGIES:
        frags = generate_fragments(w, h, strategy)
        if all(f['w'] <= eff_w and f['h'] <= eff_h for f in frags):
            return frags
    # Extreme fallback for massive pieces (e.g. 10 meters long)
    return generate_fragments(w, h, [0.33, 0.33, 0.34])

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
    help="Check to recycle gray waste into standard parts. Uncheck for colors where seams are highly visible (Oversized parts will still be jointed)."
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Visual Key")
st.sidebar.markdown("🟦 **Blue:** Clean Solid Cut")
st.sidebar.markdown("🟩 **Green:** Jointed / Fragment Cut")
st.sidebar.markdown("⬜ **Gray:** Dead Waste")

# --- INPUT AREA (MULTI-ITEM CUT LIST) ---
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
    run_calc = col_run.button("Run Strict Mathematical Optimizer", type="primary")
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
        
        # 1. Separate pieces that fit vs pieces that are impossible to cut without a joint
        for p in st.session_state.parts:
            for _ in range(p['q']):
                if p['w'] > eff_w or p['h'] > eff_h:
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
        
        # Determine strict minimum slabs to prevent looping from 1
        slab_area = sheet_w * sheet_h
        theoretical_min_slabs = max(1, math.ceil(true_delivered_area / slab_area))
        max_test_slabs = theoretical_min_slabs + 25 
        
        with st.spinner('Running strict factory optimization...'):
            for test_slabs in range(theoretical_min_slabs, max_test_slabs):
                
                # --- BASE PACK (Standards + Mandatory Oversized) ---
                packer_solid = newPacker(rotation=True)
                packer_solid.add_bin(sheet_w, sheet_h, count=test_slabs)
                
                for t in standard_targets:
                    packer_solid.add_rect(t['w'] + kerf, t['h'] + kerf, rid=f"solid_{t['id']}_{t['w']}_{t['h']}")
                    
                for mt in mandatory_oversized:
                    for f_idx, f in enumerate(mt['frags']):
                        packer_solid.add_rect(f['w'] + kerf, f['h'] + kerf, rid=f"mand_{mt['id']}_{mt['w']}_{mt['h']}_{f_idx}")
                        
                packer_solid.pack()
                base_rects = packer_solid.rect_list()
                
                packed_solid_ids = set([int(str(r[5]).split('_')[1]) for r in base_rects if str(r[5]).startswith('solid')])
                packed_mand_rids = set([str(r[5]) for r in base_rects if str(r[5]).startswith('mand')])
                
                expected_mand = sum(len(mt['frags']) for mt in mandatory_oversized)
                
                # If we can't even fit the mandatory oversized parts, we definitely need more slabs
                if len(packed_mand_rids) < expected_mand:
                    continue
                    
                # If everything fit perfectly, we are done!
                if len(packed_solid_ids) == len(standard_targets):
                    final_slabs = test_slabs
                    final_solid_count = len(standard_targets)
                    final_recycled_count = 0
                    final_rects = base_rects
                    break
                    
                # --- OPTIONAL SCRAP RECYCLING LOOP ---
                # We hit this if mandatory pieces fit, but we are missing some standard pieces.
                if is_seamless:
                    missing_standard = [t for t in standard_targets if t['id'] not in packed_solid_ids]
                    missing_standard = sorted(missing_standard, key=lambda x: x['w'] * x['h'], reverse=True)
                    
                    current_packed_recycled_frags = []
                    all_recycled_packed = True
                    
                    for target in missing_standard:
                        target_packed = False
                        
                        for strategy in SPLIT_STRATEGIES:
                            frags = generate_fragments(target['w'], target['h'], strategy)
                            
                            invalid_strategy = False
                            for f in frags:
                                if f['w'] > eff_w or f['h'] > eff_h:
                                    invalid_strategy = True
                                    break
                            if invalid_strategy:
                                continue
                            
                            test_packer = newPacker(rotation=True)
                            test_packer.add_bin(sheet_w, sheet_h, count=test_slabs)
                            
                            # Reload solids, mandatories, and previous recycled frags
                            for tid in packed_solid_ids:
                                t = next(x for x in standard_targets if x['id'] == tid)
                                test_packer.add_rect(t['w'] + kerf, t['h'] + kerf, rid=f"solid_{t['id']}_{t['w']}_{t['h']}")
                                
                            for mt in mandatory_oversized:
                                for f_idx, f in enumerate(mt['frags']):
                                    test_packer.add_rect(f['w'] + kerf, f['h'] + kerf, rid=f"mand_{mt['id']}_{mt['w']}_{mt['h']}_{f_idx}")
                                
                            for f_tuple in current_packed_recycled_frags:
                                test_packer.add_rect(f_tuple['w'] + kerf, f_tuple['h'] + kerf, rid=f_tuple['rid'])
                                
                            for f_idx, f in enumerate(frags):
                                test_packer.add_rect(f['w'] + kerf, f['h'] + kerf, rid=f"rec_{target['id']}_{target['w']}_{target['h']}_{f_idx}")
                                
                            test_packer.pack()
                            packed_rects_test = test_packer.rect_list()
                            
                            # STRICT EVICTION CHECK
                            expected_total = len(packed_solid_ids) + expected_mand + len(current_packed_recycled_frags) + len(frags)
                            
                            if len(packed_rects_test) == expected_total:
                                for f_idx, f in enumerate(frags):
                                    current_packed_recycled_frags.append({
                                        'w': f['w'], 'h': f['h'], 
                                        'rid': f"rec_{target['id']}_{target['w']}_{target['h']}_{f_idx}",
                                        'layout': f 
                                    })
                                target_packed = True
                                break 
                                
                        if not target_packed:
                            all_recycled_packed = False
                            break 
                            
                    if all_recycled_packed:
                        final_slabs = test_slabs
                        final_solid_count = len(packed_solid_ids)
                        final_recycled_count = len(missing_standard)
                        
                        # Generate final coordinates
                        final_packer = newPacker(rotation=True)
                        final_packer.add_bin(sheet_w, sheet_h, count=final_slabs)
                        for tid in packed_solid_ids:
                            t = next(x for x in standard_targets if x['id'] == tid)
                            final_packer.add_rect(t['w'] + kerf, t['h'] + kerf, rid=f"solid_{t['id']}_{t['w']}_{t['h']}")
                        for mt in mandatory_oversized:
                            for f_idx, f in enumerate(mt['frags']):
                                final_packer.add_rect(f['w'] + kerf, f['h'] + kerf, rid=f"mand_{mt['id']}_{mt['w']}_{mt['h']}_{f_idx}")
                        for f_tuple in current_packed_recycled_frags:
                            final_packer.add_rect(f_tuple['w'] + kerf, f_tuple['h'] + kerf, rid=f_tuple['rid'])
                            
                        final_packer.pack()
                        final_rects = final_packer.rect_list()
                        break

        # Fallback if loop finishes entirely
        if final_slabs == 0:
            final_slabs = test_slabs

        # --- DATA AGGREGATION & GLUE CALCULATION ---
        total_glue_length_mm = 0
        
        # 1. Process Mandatory Oversized Assembly Maps
        for mt in mandatory_oversized:
            seam_length = mt['h'] if mt['w'] >= mt['h'] else mt['w']
            joints_count = len(mt['frags']) - 1
            total_glue_length_mm += (joints_count * seam_length)
            assembled_pieces_data.append({
                'id': mt['id'], 'w': mt['w'], 'h': mt['h'], 'frags': mt['frags'], 'type': 'Mandatory (Oversized)'
            })

        # 2. Process Optional Recycled Assembly Maps
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
