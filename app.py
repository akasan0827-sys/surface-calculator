import streamlit as st
from rectpack import newPacker
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import io
import math
from matplotlib.backends.backend_pdf import PdfPages

st.set_page_config(layout="wide", page_title="Solid Surface Pro")
st.title("📐 Solid Surface Production & Mixed-Batch Recycling Tool")

# --- SMART SPLIT STRATEGIES ---
# The engine tests these ratios from top to bottom. 
# It prioritizes 1-Joint (2 pieces) before falling back to 2-Joints (3 pieces).
SPLIT_STRATEGIES = [
    # 1 JOINT (2 Pieces)
    [0.5, 0.5],       # 50/50 Even Split
    [0.6, 0.4],       # 60/40 Split
    [0.75, 0.25],     # 75/25 Split
    [0.85, 0.15],     # 85/15 Split
    [0.95, 0.05],     # 95/5 Sliver Split (Crucial for tight scrap areas)
    [0.98, 0.02],     # 98/2 Extreme Sliver
    
    # 2 JOINTS (3 Pieces) - Fallback
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
    # Process all but the last ratio
    for ratio in strategy_ratios[:-1]:
        length = math.floor(long_side * ratio)
        frags.append({"l": length, "offset": current_offset})
        current_offset += length
    
    # The last piece takes the exact mathematical remainder so there are no mm gaps
    frags.append({"l": long_side - current_offset, "offset": current_offset})

    res = []
    for f in frags:
        if is_w_long:
            res.append({"w": f['l'], "h": short_side, "x": f['offset'], "y": 0})
        else:
            res.append({"w": short_side, "h": f['l'], "x": 0, "y": f['offset']})
    return res

# --- SIDEBAR SETTINGS ---
st.sidebar.header("1. Material Settings")
sheet_w = st.sidebar.number_input("Slab Width (mm)", value=3680)
sheet_h = st.sidebar.number_input("Slab Height (mm)", value=760)
kerf = st.sidebar.number_input("Blade Kerf (mm)", value=3)
is_seamless = st.sidebar.checkbox("Enable Dynamic Fragmentation (Max 2 Joints)", True)

st.sidebar.markdown("---")
st.sidebar.markdown("### Visual Key")
st.sidebar.markdown("🟦 **Blue:** Clean Solid Cut")
st.sidebar.markdown("🟩 **Green:** Recycled Scrap Fragment")
st.sidebar.markdown("⬜ **Gray:** Dead Waste")

# --- INPUT AREA (MULTI-ITEM CUT LIST) ---
st.header("2. Build Target Order List")
if 'parts' not in st.session_state: 
    st.session_state.parts = []
    
with st.form("input", clear_on_submit=True):
    c1, c2, c3 = st.columns(3)
    w = c1.number_input("Width (mm)", value=1850, min_value=1)
    h = c2.number_input("Height (mm)", value=670, min_value=1)
    q = c3.number_input("Quantity", value=10, min_value=1)
    
    if st.form_submit_button("Add Size to Cut List"): 
        st.session_state.parts.append({"w": w, "h": h, "q": q})

if st.session_state.parts:
    st.subheader("Current Order Cut List")
    for idx, p in enumerate(st.session_state.parts):
        st.write(f"• **{p['q']} pcs** of {p['w']}x{p['h']}mm")
        
    col_run, col_clear = st.columns([1, 5])
    run_calc = col_run.button("Run Optimizer", type="primary")
    if col_clear.button("Clear Entire List"):
        st.session_state.parts = []
        st.rerun()

    if run_calc:
        total_target_qty = sum(p['q'] for p in st.session_state.parts)
        true_delivered_area = sum(p['w'] * p['h'] * p['q'] for p in st.session_state.parts)
        
        all_targets = []
        target_id = 0
        for p in st.session_state.parts:
            # Sort dimensions internally so orientation logic is consistent
            for _ in range(p['q']):
                all_targets.append({'id': target_id, 'w': p['w'], 'h': p['h']})
                target_id += 1
                
        final_slabs = 0
        final_solid_count = 0
        final_recycled_count = 0
        final_rects = []
        assembled_pieces_data = [] 
        
        with st.spinner('Running multi-strategy factory optimization...'):
            for test_slabs in range(1, total_target_qty + 1):
                
                # Pass 1: Pack solid pieces
                packer_solid = newPacker(rotation=True)
                packer_solid.add_bin(sheet_w, sheet_h, count=test_slabs)
                
                for t in all_targets:
                    packer_solid.add_rect(t['w'] + kerf, t['h'] + kerf, rid=f"solid_{t['id']}_{t['w']}_{t['h']}")
                packer_solid.pack()
                
                solid_rects = packer_solid.rect_list()
                packed_ids = [int(str(r[5]).split('_')[1]) for r in solid_rects if str(r[5]).startswith('solid')]
                
                if len(packed_ids) >= total_target_qty:
                    final_slabs = test_slabs
                    final_solid_count = total_target_qty
                    final_recycled_count = 0
                    final_rects = solid_rects
                    break
                    
                if is_seamless:
                    missing_targets = [t for t in all_targets if t['id'] not in packed_ids]
                    
                    # Sort missing targets by largest area first to prioritize fitting big pieces
                    missing_targets = sorted(missing_targets, key=lambda x: x['w'] * x['h'], reverse=True)
                    
                    current_packed_recycled_frags = []
                    all_recycled_packed = True
                    
                    for target in missing_targets:
                        target_packed = False
                        
                        # Test every split strategy until one fits in the gray waste
                        for strategy in SPLIT_STRATEGIES:
                            frags = generate_fragments(target['w'], target['h'], strategy)
                            
                            test_packer = newPacker(rotation=True)
                            test_packer.add_bin(sheet_w, sheet_h, count=test_slabs)
                            
                            # Load locked solids
                            for tid in packed_ids:
                                t = next(x for x in all_targets if x['id'] == tid)
                                test_packer.add_rect(t['w'] + kerf, t['h'] + kerf, rid=f"solid_{t['id']}_{t['w']}_{t['h']}")
                                
                            # Load previously locked recycled fragments from other targets
                            for f_tuple in current_packed_recycled_frags:
                                test_packer.add_rect(f_tuple['w'] + kerf, f_tuple['h'] + kerf, rid=f_tuple['rid'])
                                
                            # Try to add CURRENT strategy fragments
                            for f_idx, f in enumerate(frags):
                                test_packer.add_rect(f['w'] + kerf, f['h'] + kerf, rid=f"rec_{target['id']}_{target['w']}_{target['h']}_{f_idx}")
                                
                            test_packer.pack()
                            
                            # Check if all fragments for this specific strategy made it onto the slabs
                            packed_rects_test = test_packer.rect_list()
                            found_frags = sum(1 for r in packed_rects_test if str(r[5]).startswith(f"rec_{target['id']}_"))
                            
                            if found_frags == len(frags):
                                # Strategy success! Lock these fragments in
                                for f_idx, f in enumerate(frags):
                                    current_packed_recycled_frags.append({
                                        'w': f['w'],
                                        'h': f['h'],
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
                        final_solid_count = len(packed_ids)
                        final_recycled_count = len(missing_targets)
                        
                        # Re-run final clean pack to get drawing coordinates
                        final_packer = newPacker(rotation=True)
                        final_packer.add_bin(sheet_w, sheet_h, count=final_slabs)
                        for tid in packed_ids:
                            t = next(x for x in all_targets if x['id'] == tid)
                            final_packer.add_rect(t['w'] + kerf, t['h'] + kerf, rid=f"solid_{t['id']}_{t['w']}_{t['h']}")
                        for f_tuple in current_packed_recycled_frags:
                            final_packer.add_rect(f_tuple['w'] + kerf, f_tuple['h'] + kerf, rid=f_tuple['rid'])
                            
                        final_packer.pack()
                        final_rects = final_packer.rect_list()
                        
                        # Build assembly map data
                        for t in missing_targets:
                            t_frags = [f['layout'] for f in current_packed_recycled_frags if str(f['rid']).startswith(f"rec_{t['id']}_")]
                            assembled_pieces_data.append({
                                'id': t['id'], 'w': t['w'], 'h': t['h'], 'frags': t_frags
                            })
                        break

        if final_slabs == 0:
            final_slabs = test_slabs

        # --- YIELD CALCULATION ---
        total_material_area = final_slabs * sheet_w * sheet_h
        yield_percentage = (true_delivered_area / total_material_area) * 100 if total_material_area > 0 else 0

        # --- UI REPORT ---
        st.markdown("---")
        st.header("3. Production & Material Efficiency Report")
        
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("📦 Slabs Pulled From Stock", f"{final_slabs} Slabs")
        col_m2.metric("🎯 Total Delivered Order", f"{total_target_qty} Pieces")
        col_m3.metric("🔥 True Material Yield", f"{yield_percentage:.1f}%")
        
        st.success(f"📋 **Mixed Batch Output:** Produced **{final_solid_count} pieces** from clean single-cuts, and **{final_recycled_count} pieces** compiled dynamically with max 2-joints.")

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
                st.subheader("🧩 Recycled Jointing Assembly Maps")
                st.info("Gather the specific green 'FRAG' pieces from the slabs to assemble these final mixed products.")
                
                for asm in assembled_pieces_data:
                    fig2, ax2 = plt.subplots(figsize=(6, 2.5))
                    ax2.add_patch(patches.Rectangle((0,0), asm['w'], asm['h'], facecolor='#f9f9f9', edgecolor='black', lw=2))
                    
                    joint_count = len(asm['frags']) - 1
                    joint_text = "1-Joint Seam" if joint_count == 1 else "2-Joint Seam"
                    
                    for f in asm['frags']:
                        ax2.add_patch(patches.Rectangle((f['x'], f['y']), f['w'], f['h'], edgecolor='red', linestyle='--', facecolor='#99ff99', alpha=0.6, lw=1.5))
                        ax2.text(f['x'] + f['w']/2, f['y'] + f['h']/2, f"{int(f['w'])}x{int(f['h'])}", color='black', weight='bold', ha='center', va='center', fontsize=9)
                    
                    ax2.set_xlim(0, asm['w'])
                    ax2.set_ylim(0, asm['h'])
                    ax2.set_aspect('equal')
                    ax2.axis('off')
                    ax2.set_title(f"Assembled Product: {asm['w']}x{asm['h']}mm ({joint_text})", fontsize=10)
                    
                    st.pyplot(fig2)
                    pdf.savefig(fig2, bbox_inches='tight')
                    plt.close(fig2)

        st.markdown("---")
        st.download_button("📄 Export Production PDF", pdf_buffer.getvalue(), "mixed_batch_production.pdf", "application/pdf")