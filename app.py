#!/usr/bin/env python3
"""Streamlit web UI — Water Ingress Simulator.

Architecture:
  - Sidebar: inputs organised in collapsible sections (expanders).
  - Main area: five navigation tabs (Setup, Results, Diagnostics, Monte Carlo, Batch).
  - Session state stores all computed outputs so tabs stay populated across
    interactions without recomputing.

Usage:
    streamlit run app.py
"""
import csv
import io
import os
import sys
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'examples'))
from plot_schematics import draw_schematic

from engine import (
    Building, IngressPathway, Simulation,
    parse_external_text, parse_ingress_file,
    parse_ingress_text, parse_velocity_text,
    sample_with_zero_padding,
)
from loss import load_vulnerability_curve
from pump import SumpPump
from report import diagnostics_from_trace, diagnostics_to_csv_rows, generate_narrative
import plot as viz


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title='Water Ingress Simulator',
    page_icon='💧',
    layout='wide',
    initial_sidebar_state='expanded',
)

# Light structural CSS — metric cards and tight sidebar spacing.
st.markdown("""
<style>
[data-testid="stSidebar"] .block-container { padding-top: 0.75rem; }
[data-testid="metric-container"] {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 8px; padding: 0.5rem 0.8rem;
}
.section-label {
    font-size: 0.75rem; font-weight: 700; letter-spacing: 0.06em;
    text-transform: uppercase; color: #94a3b8; margin: 0.6rem 0 0.2rem;
}
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────

for _k in ('run_result', 'mc_result'):
    if _k not in st.session_state:
        st.session_state[_k] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_text(up) -> str:
    return up.getvalue().decode('utf-8') if up else ''

def _read_bytes(up) -> bytes:
    return up.getvalue() if up else b''

def _save_tmp(data: bytes, suffix='') -> str:
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tf.write(data); tf.flush(); tf.close()
    return tf.name

def _time_abbr(unit: str) -> str:
    return {'seconds': 's', 'minutes': 'min', 'hours': 'h'}.get(unit, unit)

def _data_editor(rows, key):
    if hasattr(st, 'data_editor'):
        return st.data_editor(rows, num_rows='dynamic', key=key, use_container_width=True)
    return st.experimental_data_editor(rows, num_rows='dynamic', key=key)

def _tbl_to_pairs(tbl, ka, kb):
    recs = tbl.to_dict('records') if hasattr(tbl, 'to_dict') else list(tbl)
    a, b = [], []
    for r in recs:
        try:
            a.append(float(r.get(ka, list(r.values())[0])))
            b.append(float(r.get(kb, list(r.values())[1])))
        except Exception:
            pass
    return a, b

def _fmt_m(v):  return f'{v:.3f} m'
def _fmt_m3(v): return f'{v:.3f} m³'
def _fmt_pct(v): return f'{v*100:.1f} %'


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR — INPUTS
# ════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title('💧 Water Ingress')
    st.caption('Simulation & loss tool')

    # ── 1. Hydrograph ────────────────────────────────────────────────────────
    with st.expander('🌊  Hydrograph', expanded=True):
        time_unit = st.selectbox(
            'Time unit', ['seconds', 'minutes', 'hours'], index=1,
            help='Applies to the hydrograph CSV and the simulation timestep.')
        _mul = {'seconds': 1.0, 'minutes': 60.0, 'hours': 3600.0}[time_unit]
        _ta = _time_abbr(time_unit)
        timestep = st.number_input(
            f'Timestep  ({_ta})',
            value=1.0, min_value=0.001, step=0.5, format='%.3f')

        ext_mode = st.radio('Input', ['Upload CSV', 'Manual table'],
                            key='ext_mode', horizontal=True)
        uploaded_external = None
        manual_ext_tbl    = None
        if ext_mode == 'Upload CSV':
            uploaded_external = st.file_uploader(
                'Levels CSV  (time, level)', type=['csv', 'txt'], key='ext_up',
                label_visibility='collapsed')
        else:
            manual_ext_tbl = _data_editor(
                [{'time': 0.0, 'level': 0.0},
                 {'time': 30.0, 'level': 0.5},
                 {'time': 60.0, 'level': 0.0}],
                key='ext_tbl')

    # ── 2. Building & ingress ────────────────────────────────────────────────
    with st.expander('🏠  Building & ingress', expanded=True):
        floor_area = st.number_input('Ground-floor area (m²)', value=50.0, min_value=0.1)

        ing_mode = st.radio('Ingress', ['Upload file', 'Manual table'],
                            key='ing_mode', horizontal=True)
        uploaded_ingress = None
        manual_ing_tbl   = None
        if ing_mode == 'Upload file':
            uploaded_ingress = st.file_uploader(
                'Ingress file  (height, area, Cd [, name])',
                type=['txt', 'csv'], key='ing_up',
                label_visibility='collapsed')
        else:
            manual_ing_tbl = _data_editor(
                [{'height': 0.0, 'area': 0.01, 'coeff': 0.6, 'name': 'wall_crack'}],
                key='ing_tbl')

        with st.expander('💨  External velocity  (optional)', expanded=False):
            vel_mode = st.radio(
                'Velocity', ['None', 'Constant', 'Upload CSV', 'Manual table'],
                key='vel_mode', horizontal=False)
            uploaded_velocity = None
            manual_vel_tbl    = None
            default_velocity  = 0.0
            if vel_mode == 'Constant':
                default_velocity = st.number_input(
                    'Velocity (m/s)', value=0.2, min_value=0.0, step=0.05, format='%.2f')
            elif vel_mode == 'Upload CSV':
                uploaded_velocity = st.file_uploader(
                    'Velocity CSV  (time, velocity)', type=['csv', 'txt'], key='vel_up',
                    label_visibility='collapsed')
            elif vel_mode == 'Manual table':
                manual_vel_tbl = _data_editor(
                    [{'time': 0.0, 'velocity': 0.2}, {'time': 60.0, 'velocity': 0.0}],
                    key='vel_tbl')

    # ── 3. Basement ──────────────────────────────────────────────────────────
    with st.expander('🏗️  Basement compartment', expanded=False):
        enable_basement = st.checkbox('Enable basement', value=False)
        if enable_basement:
            c1, c2 = st.columns(2)
            basement_area         = c1.number_input('Area (m²)',        value=30.0, min_value=0.1)
            basement_floor_elev   = c2.number_input('Floor elev (m)',   value=-2.5, step=0.1)
            c3, c4 = st.columns(2)
            basement_ceiling_elev = c3.number_input('Ceiling elev (m)', value=0.0, step=0.1)

            st.markdown('<div class="section-label">Perimeter opening</div>',
                        unsafe_allow_html=True)
            pc1, pc2, pc3 = st.columns(3)
            bsmt_ing_height = pc1.number_input('Sill (m)',  value=0.0,   step=0.05, format='%.2f',  key='bih')
            bsmt_ing_area   = pc2.number_input('Area (m²)', value=0.005, step=0.001, format='%.4f', key='bia')
            bsmt_ing_coeff  = pc3.number_input('Cd',        value=0.5,   step=0.05, format='%.2f',  key='bic')

            st.markdown('<div class="section-label">Ground ↔ basement bypass</div>',
                        unsafe_allow_html=True)
            bc1, bc2 = st.columns(2)
            bsmt_conn_height = bc1.number_input('Sill (m)',  value=0.0, step=0.05, format='%.2f',  key='bch')
            bsmt_conn_area   = bc2.number_input('Area (m²)', value=0.0, step=0.001, format='%.4f', key='bca')
        else:
            basement_area = basement_floor_elev = basement_ceiling_elev = 0.0
            bsmt_ing_height = bsmt_ing_area = bsmt_ing_coeff = 0.0
            bsmt_conn_height = bsmt_conn_area = 0.0

    # ── 4. Sump & pump ───────────────────────────────────────────────────────
    with st.expander('⚙️  Sump & pump', expanded=False):
        if not enable_basement:
            st.caption('Enable the basement compartment first.')
        enable_sump = st.checkbox('Enable sump & pump', value=False,
                                  disabled=not enable_basement)
        if enable_sump and enable_basement:
            sc1, sc2 = st.columns(2)
            sump_area       = sc1.number_input('Sump area (m²)',    value=0.5,   min_value=0.01, step=0.1)
            sump_base_elev  = sc2.number_input('Sump base (m)',     value=float(basement_floor_elev), step=0.1)
            oc1, oc2 = st.columns(2)
            sump_ov_level   = oc1.number_input('Overflow crest (m above base)', value=0.8, step=0.05)
            sump_ov_coeff   = oc2.number_input('Overflow coeff',    value=1.8, step=0.1, format='%.2f')
            sump_ov_exp     = st.number_input('Overflow exp (1.5 = weir)',       value=1.5, step=0.1, format='%.1f')
            st.markdown('<div class="section-label">Pump curve</div>', unsafe_allow_html=True)
            pp1, pp2 = st.columns(2)
            pump_on   = pp1.number_input('ON level (m)',  value=0.10, step=0.02, format='%.2f')
            pump_off  = pp2.number_input('OFF level (m)', value=0.02, step=0.01, format='%.2f')
            ph1, ph2 = st.columns(2)
            pump_hsh  = ph1.number_input('Shut-off head (m)', value=5.0, step=0.5)
            pump_k    = ph2.number_input('k_pump',             value=1000.0, step=100.0, format='%.0f')
            pl1, pl2 = st.columns(2)
            pipe_k    = pl1.number_input('k_pipe', value=0.0, step=10.0, format='%.0f')
            pump_avail = pl2.number_input('Availability (0–1)', value=1.0,
                                          min_value=0.0, max_value=1.0, step=0.05, format='%.2f')
        else:
            enable_sump = False
            sump_area = sump_base_elev = sump_ov_level = sump_ov_coeff = sump_ov_exp = 0.0
            pump_on = pump_off = pump_hsh = pump_k = pipe_k = pump_avail = 0.0

    # ── 5. Loss estimation ───────────────────────────────────────────────────
    with st.expander('💸  Loss estimation', expanded=False):
        st.caption('Upload depth-damage curves (CSV: depth_m, loss_GBP).')
        uploaded_bldg_vuln = st.file_uploader(
            'Building vulnerability', type=['csv'], key='bvuln')
        uploaded_bsmt_vuln = st.file_uploader(
            'Basement vulnerability', type=['csv'], key='svuln')

    # ── 6. Monte Carlo ───────────────────────────────────────────────────────
    with st.expander('🎲  Monte Carlo  (fragility)', expanded=False):
        enable_mc = st.checkbox('Enable fragility MC', value=False)
        if enable_mc:
            uploaded_frag_ing = st.file_uploader(
                'Fragility ingress CSV', type=['csv'], key='frag_ing')
            uploaded_membrane = st.file_uploader(
                'Membrane CSV  (optional)', type=['csv'], key='mem_csv')
            mc1, mc2 = st.columns(2)
            n_reps    = mc1.number_input('Replicates', value=200, min_value=2, step=50)
            frag_seed = mc2.number_input('Seed  (0 = random)', value=42, min_value=0, step=1)
        else:
            uploaded_frag_ing = uploaded_membrane = None
            n_reps = 100; frag_seed = 0

    # ── 7. Output options ────────────────────────────────────────────────────
    with st.expander('🎬  Output options', expanded=False):
        make_anim = st.checkbox('Generate GIF animation  (slow)', value=False)

    st.divider()
    run_button = st.button('▶  Run simulation', type='primary', use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# MAIN AREA — TABS
# ════════════════════════════════════════════════════════════════════════════

_has_run = st.session_state.run_result is not None
_has_mc  = st.session_state.mc_result  is not None

tab_setup, tab_results, tab_diag, tab_mc_out, tab_batch = st.tabs([
    '📥  Setup & preview',
    '📈  Results'      + ('  ✓' if _has_run else ''),
    '🔬  Diagnostics'  + ('  ✓' if _has_run else ''),
    '🎲  Monte Carlo'  + ('  ✓' if _has_mc  else ''),
    '📊  Batch analysis',
])


# ── Tab 1: Setup & preview ────────────────────────────────────────────────────

with tab_setup:
    st.markdown(
        'Review your inputs below, then press **▶ Run simulation** in the sidebar. '
        'Results will appear in the **Results** and **Diagnostics** tabs.')
    st.divider()

    col_ext, col_ing, col_vel = st.columns(3)

    with col_ext:
        st.markdown('**External levels**')
        _show_ext = False
        if ext_mode == 'Upload CSV' and uploaded_external:
            try:
                _et, _el = parse_external_text(_read_text(uploaded_external))
                _p = os.path.join(tempfile.gettempdir(), 'prev_ext.png')
                viz.save_external_preview(_et, _el, _p, time_unit=time_unit)
                st.image(_p, width="stretch")
                st.caption(f'{len(_et)} points  ·  peak {max(_el):.3f} m')
                _show_ext = True
            except Exception as _e:
                st.error(f'Parse error: {_e}')
        elif ext_mode == 'Manual table' and manual_ext_tbl is not None:
            try:
                _et, _el = _tbl_to_pairs(manual_ext_tbl, 'time', 'level')
                if _et:
                    _p = os.path.join(tempfile.gettempdir(), 'prev_ext.png')
                    viz.save_external_preview(_et, _el, _p, time_unit=time_unit)
                    st.image(_p, width="stretch")
                    st.caption(f'{len(_et)} points  ·  peak {max(_el):.3f} m')
                    _show_ext = True
            except Exception:
                pass
        if not _show_ext:
            st.info('Upload a CSV or enter data manually in the **Hydrograph** section.')

    with col_ing:
        st.markdown('**Ingress pathways**')
        _show_ing = False
        if ing_mode == 'Upload file' and uploaded_ingress:
            try:
                _tmp = _save_tmp(_read_bytes(uploaded_ingress), '.txt')
                _il  = parse_ingress_file(_tmp)
                _p   = os.path.join(tempfile.gettempdir(), 'prev_ing.png')
                try:
                    viz.save_ingress_locations(_il, _p)
                except Exception:
                    viz.save_ingress_preview(_il, _p)
                st.image(_p, width="stretch")
                st.caption(f'{len(_il)} pathway(s)  ·  total area '
                           f'{sum(p.area for p in _il):.5f} m²')
                _show_ing = True
            except Exception as _e:
                st.error(f'Parse error: {_e}')
        elif ing_mode == 'Manual table' and manual_ing_tbl is not None:
            try:
                _r = (manual_ing_tbl.to_dict('records')
                      if hasattr(manual_ing_tbl, 'to_dict') else list(manual_ing_tbl))
                if _r:
                    st.dataframe(pd.DataFrame(_r), use_container_width=True, hide_index=True)
                    _show_ing = True
            except Exception:
                pass
        if not _show_ing:
            st.info('Upload an ingress file or define pathways manually.')

    with col_vel:
        st.markdown('**External velocity**')
        _show_vel = False
        if vel_mode == 'Constant':
            st.metric('Constant velocity', f'{default_velocity:.2f} m/s')
            if default_velocity == 0.0:
                st.caption('Hydrodynamic term disabled (v = 0).')
            _show_vel = True
        elif vel_mode == 'Upload CSV' and uploaded_velocity:
            try:
                _vt, _vv = parse_velocity_text(_read_text(uploaded_velocity))
                _p = os.path.join(tempfile.gettempdir(), 'prev_vel.png')
                viz.save_velocity_preview(_vt, _vv, _p, time_unit=time_unit)
                st.image(_p, width="stretch")
                st.caption(f'Peak {max(_vv):.2f} m/s')
                _show_vel = True
            except Exception as _e:
                st.error(f'Parse error: {_e}')
        elif vel_mode == 'Manual table' and manual_vel_tbl is not None:
            try:
                _vt, _vv = _tbl_to_pairs(manual_vel_tbl, 'time', 'velocity')
                if _vt:
                    _p = os.path.join(tempfile.gettempdir(), 'prev_vel.png')
                    viz.save_velocity_preview(_vt, _vv, _p, time_unit=time_unit)
                    st.image(_p, width="stretch")
                    _show_vel = True
            except Exception:
                pass
        if not _show_vel and vel_mode == 'None':
            st.info('No velocity — hydrodynamic term is zero.')
        elif not _show_vel:
            st.info('Upload a velocity CSV or choose a source above.')

    # ── Building schematic ────────────────────────────────────────────────────
    st.divider()
    st.markdown('**Building schematic**')
    _col_l, _col_sch, _col_r = st.columns([1.5, 2, 1.5])
    with _col_sch:
        _bsmt_d_sch = (abs(float(basement_floor_elev))
                       if enable_basement and basement_area > 0 else None)
        _path_style_sch = 'prob' if enable_mc else 'det'
        _gf_paths_sch   = []
        _bsmt_paths_sch = []
        try:
            if ing_mode == 'Upload file' and uploaded_ingress:
                _tmp_sch = _save_tmp(_read_bytes(uploaded_ingress), '.txt')
                for _p in parse_ingress_file(_tmp_sch):
                    if getattr(_p, 'target', 'ground') == 'ground':
                        _gf_paths_sch.append(dict(
                            sill=_p.height, name=_p.name or 'path',
                            style=_path_style_sch))
            elif ing_mode == 'Manual table' and manual_ing_tbl is not None:
                _recs_sch = (manual_ing_tbl.to_dict('records')
                             if hasattr(manual_ing_tbl, 'to_dict') else list(manual_ing_tbl))
                for _rs in _recs_sch:
                    try:
                        _gf_paths_sch.append(dict(
                            sill=float(_rs.get('height', 0.0)),
                            name=str(_rs.get('name', 'path')),
                            style=_path_style_sch,
                        ))
                    except Exception:
                        pass
        except Exception:
            pass
        if enable_basement and basement_area > 0 and float(bsmt_ing_area) > 0:
            _bsmt_paths_sch = [dict(
                sill=float(bsmt_ing_height), name='bsmt ingress', style='det')]
        _mem_cfg_sch = None
        if enable_mc and uploaded_membrane is not None:
            _mem_cfg_sch = dict(sill=0.0, capacity=0.5, style='prob')
        _sch_subtitle = ('Basement' + (' + pump' if enable_sump else '')
                         if enable_basement else 'Ground floor only')
        _sch_cfg = dict(
            label='Current setup', subtitle=_sch_subtitle,
            floor_h=2.5, bsmt_d=_bsmt_d_sch,
            sump=enable_sump, pump=enable_sump,
            gf_paths=_gf_paths_sch, bsmt_paths=_bsmt_paths_sch,
            membrane=_mem_cfg_sch,
        )
        _sch_fig, _sch_ax = plt.subplots(
            figsize=(3.5, 5.0 if _bsmt_d_sch else 3.5))
        _sch_fig.patch.set_facecolor('white')
        draw_schematic(_sch_ax, _sch_cfg)
        st.pyplot(_sch_fig, use_container_width=True)
        plt.close(_sch_fig)


# ════════════════════════════════════════════════════════════════════════════
# RUN LOGIC  (executes when button pressed; stores outputs in session_state)
# ════════════════════════════════════════════════════════════════════════════

if run_button:
    _has_ext = (ext_mode == 'Upload CSV' and uploaded_external is not None) or \
               (ext_mode == 'Manual table' and manual_ext_tbl is not None)
    _has_ing = (ing_mode == 'Upload file' and uploaded_ingress is not None) or \
               (ing_mode == 'Manual table' and manual_ing_tbl is not None)

    if not _has_ext or not _has_ing:
        with tab_results:
            st.error('⚠️  Provide both an **external levels hydrograph** and '
                     '**ingress pathway definitions** before running.')
    else:
        # Progress lives inside the Results tab so the user is guided there.
        with tab_results:
            _prog  = st.progress(0, 'Preparing inputs…')
            _stat  = st.empty()

        try:
            # ── External hydrograph ──────────────────────────────────────────
            if ext_mode == 'Upload CSV':
                _times, _levels = parse_external_text(_read_text(uploaded_external))
            else:
                _times, _levels = _tbl_to_pairs(manual_ext_tbl, 'time', 'level')

            times_s  = [t * _mul for t in _times]
            dt_s     = float(timestep) * _mul

            # ── Ingress pathways ─────────────────────────────────────────────
            if ing_mode == 'Upload file':
                _tmp_ing  = _save_tmp(_read_bytes(uploaded_ingress), '.txt')
                ing_list  = parse_ingress_file(_tmp_ing)
            else:
                _recs = (manual_ing_tbl.to_dict('records')
                         if hasattr(manual_ing_tbl, 'to_dict') else list(manual_ing_tbl))
                _lines = []
                for _r in _recs:
                    try:
                        _v = list(_r.values())
                        _parts = [str(_v[0]), str(_v[1]), str(_v[2])]
                        if len(_v) > 3 and _v[3]:
                            _parts.append(str(_v[3]))
                        _lines.append(','.join(_parts))
                    except Exception:
                        pass
                ing_list = parse_ingress_text('\n'.join(_lines))

            # ── Velocity ─────────────────────────────────────────────────────
            if vel_mode == 'Upload CSV' and uploaded_velocity:
                _vtr, _vvr = parse_velocity_text(_read_text(uploaded_velocity))
                v_times_s  = [t * _mul for t in _vtr]
                v_vals     = list(_vvr)
            elif vel_mode == 'Manual table' and manual_vel_tbl is not None:
                _vtr, _vvr = _tbl_to_pairs(manual_vel_tbl, 'time', 'velocity')
                v_times_s  = [t * _mul for t in _vtr]
                v_vals     = _vvr
            else:
                v_times_s = list(times_s)
                v_vals    = [float(default_velocity)] * len(times_s)

            # ── Building ──────────────────────────────────────────────────────
            bld = Building(float(floor_area))
            if enable_basement and basement_area > 0:
                bld.basement_area              = float(basement_area)
                bld.h_basement                 = 0.0
                bld.z_basement                 = float(basement_floor_elev)
                bld.basement_ceiling_elevation = float(basement_ceiling_elev)
                if bsmt_ing_area > 0:
                    bld.basement_ingress = IngressPathway(
                        height=float(bsmt_ing_height),
                        area=float(bsmt_ing_area),
                        coeff=float(bsmt_ing_coeff),
                        name='ext-basement-perimeter',
                        source='outside', target='basement')
                if bsmt_conn_area > 0:
                    ing_list.append(IngressPathway(
                        height=float(bsmt_conn_height),
                        area=float(bsmt_conn_area),
                        coeff=1.0, name='ground-basement-conn',
                        source='ground', target='basement'))
                if enable_sump and sump_area > 0:
                    bld.sump_pump = SumpPump(
                        sump_area=float(sump_area),
                        sump_base_elevation=float(sump_base_elev),
                        overflow_level=float(sump_ov_level),
                        overflow_coeff=float(sump_ov_coeff),
                        overflow_exponent=float(sump_ov_exp),
                        pump_on_level=float(pump_on),
                        pump_off_level=float(pump_off),
                        pump_shutoff_head=float(pump_hsh),
                        pump_curve_coeff=float(pump_k),
                        pipe_loss_coeff=float(pipe_k),
                        pump_availability=float(pump_avail),
                    )

            # ── Simulate ──────────────────────────────────────────────────────
            _prog.progress(5, 'Running simulation…')
            sim = Simulation(bld, ing_list, times_s, _levels,
                             dt=dt_s,
                             external_vel_times=v_times_s,
                             external_velocities=v_vals)

            def _cb(p):
                try:
                    _prog.progress(5 + int(p * 70), f'Simulating…  {int(p*100)} %')
                except Exception:
                    pass

            _ret = sim.run(progress_callback=_cb, verbose=False)
            if len(_ret) == 4:
                sim_t, sim_h, sim_b, sim_s = _ret
            elif len(_ret) == 3:
                sim_t, sim_h, sim_b = _ret; sim_s = None
            else:
                sim_t, sim_h = _ret; sim_b = sim_s = None

            sim_t_disp = [t / _mul for t in sim_t]

            # Sample external to sim grid
            def _samp(st_list, t_ext, h_ext):
                out = []; j = 0
                for t in st_list:
                    while j < len(t_ext) - 1 and t >= t_ext[j + 1]:
                        j += 1
                    if j < len(t_ext) - 1:
                        t1, h1, t2, h2 = t_ext[j], h_ext[j], t_ext[j+1], h_ext[j+1]
                        out.append(h1 + (h2-h1)*(t-t1)/(t2-t1) if t2!=t1 else h1)
                    else:
                        out.append(h_ext[-1] if h_ext else 0.0)
                return out

            samp_ext = _samp(sim_t, times_s, _levels)
            samp_vel = None
            try:
                samp_vel = sample_with_zero_padding(sim_t, v_times_s, v_vals)
            except Exception:
                pass

            # ── Key metrics ───────────────────────────────────────────────────
            h_pk_gf   = max(sim_h,   default=0.0)
            h_pk_bsmt = max(sim_b,   default=0.0) if sim_b else 0.0
            h_pk_sump = max(sim_s,   default=0.0) if sim_s else 0.0
            vol_in = sum(
                (sim_h[i] - sim_h[i-1]) * float(floor_area)
                for i in range(1, len(sim_h))
                if sim_h[i] > sim_h[i-1]
            )

            # ── Main plot ────────────────────────────────────────────────────
            _prog.progress(80, 'Generating plots…')
            outdir   = tempfile.mkdtemp(prefix='sim_')
            sim_png  = os.path.join(outdir, 'simulation_result.png')
            _bsmt_max = (max(0.0, float(basement_ceiling_elev) - float(basement_floor_elev))
                         if enable_basement and basement_area > 0 else None)
            _sump_ov  = float(sump_ov_level) if enable_sump else None
            viz.save_simulation_result(
                sim_t_disp, sim_h, samp_ext, sim_png,
                time_unit=time_unit,
                basement_levels=sim_b,
                velocity_series=samp_vel,
                sump_levels=sim_s,
                basement_max_depth=_bsmt_max,
                sump_overflow_level=_sump_ov)
            with open(sim_png, 'rb') as _f:
                sim_png_bytes = _f.read()

            # ── Diagnostics ──────────────────────────────────────────────────
            dash_bytes = diag_csv = narrative = None
            ev_rows = {}
            try:
                _prog.progress(85, 'Running diagnostics…')
                diag     = diagnostics_from_trace(sim._last_trace, sim.dt)
                dash_png = os.path.join(outdir, 'dashboard.png')
                viz.save_interpretation_dashboard(diag, dash_png, time_unit=time_unit)
                with open(dash_png, 'rb') as _f:
                    dash_bytes = _f.read()
                narrative = generate_narrative(diag)
                ev  = diag.get('events', {})

                def _t_fmt(k):
                    v = ev.get(k)
                    return f'{v/_mul:.2f} {_ta}' if v is not None else '—'

                ev_rows = {
                    'First ground-floor inundation': _t_fmt('t_first_gf_inundation'),
                    'First basement inundation':     _t_fmt('t_first_basement_inundation'),
                    'First pump activation':         _t_fmt('t_first_pump_on'),
                    'First sump overflow':           _t_fmt('t_first_sump_overflow'),
                    'Pump interception ratio':       (
                        _fmt_pct(ev['pump_interception_ratio'])
                        if ev.get('pump_interception_ratio') is not None else '—'),
                    'Perimeter inflow (m³)':         f'{ev.get("vol_perimeter_total", 0):.4f}',
                    'Pump discharge (m³)':           f'{ev.get("vol_pump_total", 0):.4f}',
                    'Sump overflow (m³)':            f'{ev.get("vol_sump_overflow_total", 0):.4f}',
                }
                _buf = io.StringIO()
                _w   = csv.writer(_buf)
                for _row in diagnostics_to_csv_rows(diag):
                    _w.writerow(_row)
                diag_csv = _buf.getvalue().encode()
            except Exception:
                pass

            # ── Loss ─────────────────────────────────────────────────────────
            bldg_loss = bsmt_loss = None
            if uploaded_bldg_vuln:
                try:
                    bldg_loss = load_vulnerability_curve(
                        _save_tmp(_read_bytes(uploaded_bldg_vuln), '.csv')
                    ).interpolate_loss(h_pk_gf)
                except Exception:
                    pass
            if uploaded_bsmt_vuln:
                try:
                    bsmt_loss = load_vulnerability_curve(
                        _save_tmp(_read_bytes(uploaded_bsmt_vuln), '.csv')
                    ).interpolate_loss(h_pk_bsmt)
                except Exception:
                    pass

            # ── Animation ────────────────────────────────────────────────────
            anim_bytes = None
            if make_anim:
                _prog.progress(88, 'Generating animation…')
                try:
                    _ap  = os.path.join(outdir, 'animation.gif')
                    _sp  = bld.sump_pump
                    _tr  = sim._last_trace
                    viz.generate_animation(
                        sim_t_disp, sim_h, samp_ext, ing_list, _ap,
                        time_unit=time_unit,
                        basement_levels=sim_b,
                        basement_abs_levels=(
                            [bld.z_basement + hb for hb in sim_b] if sim_b else None),
                        velocity_series=samp_vel,
                        sump_levels=sim_s,
                        sump_overflow_level=(_sp.overflow_level if _sp else None),
                        Q_perim_series=(_tr['Q_ext_perimeter'] if _tr else None),
                        Q_bypass_series=(_tr['Q_b_bs'] if _tr else None),
                    )
                    with open(_ap, 'rb') as _f:
                        anim_bytes = _f.read()
                except Exception:
                    pass

            # ── Store ─────────────────────────────────────────────────────────
            st.session_state.run_result = dict(
                sim_t_disp=sim_t_disp, sim_h=sim_h, sim_b=sim_b, sim_s=sim_s,
                h_pk_gf=h_pk_gf, h_pk_bsmt=h_pk_bsmt, h_pk_sump=h_pk_sump,
                vol_in=vol_in,
                time_unit=time_unit, mul=_mul,
                has_basement=sim_b is not None, has_sump=sim_s is not None,
                sim_png_bytes=sim_png_bytes,
                dash_bytes=dash_bytes, diag_csv=diag_csv,
                narrative=narrative or [], ev_rows=ev_rows,
                bldg_loss=bldg_loss, bsmt_loss=bsmt_loss,
                anim_bytes=anim_bytes,
                # Keep parsed inputs for MC factory
                times_s=times_s, levels=_levels,
                v_times_s=v_times_s, v_vals=v_vals, dt_s=dt_s,
                bld_floor=float(floor_area),
            )
            st.session_state.mc_result = None  # clear stale MC on new run

            # ── Monte Carlo ───────────────────────────────────────────────────
            if enable_mc and uploaded_frag_ing is not None:
                _prog.progress(92, 'Running Monte Carlo…')
                try:
                    import fragility as _frag

                    with tab_mc_out:
                        _mc_prog = st.progress(0, 'Monte Carlo…')

                    def _mc_cb(rep, total):
                        try:
                            _mc_prog.progress(
                                min(100, int(rep / total * 100)) if total else 0,
                                f'Replicate {rep} / {total}')
                        except Exception:
                            pass

                    _tmp_fi  = _save_tmp(_read_bytes(uploaded_frag_ing), '.csv')
                    _fpaths  = _frag.parse_pathway_file(_tmp_fi)
                    _fmems   = []
                    if uploaded_membrane:
                        _tmp_m   = _save_tmp(_read_bytes(uploaded_membrane), '.csv')
                        _raw_mem = _frag.parse_pathway_file(_tmp_m)
                        _fmems   = [_frag.fragile_path_to_membrane(fp)
                                    for fp in _raw_mem
                                    if fp.group_id > 0 and fp.fragility is not None]
                    _frag.assign_representative_paths(_fpaths, _fmems)

                    # Capture current building config for factory closure
                    _fa    = float(floor_area)
                    _eb    = enable_basement and float(basement_area) > 0
                    _ba, _bf, _bc = float(basement_area), float(basement_floor_elev), float(basement_ceiling_elev)
                    _bih2, _bia2, _bic2 = float(bsmt_ing_height), float(bsmt_ing_area), float(bsmt_ing_coeff)
                    _es    = enable_sump and enable_basement
                    _sa2, _sbe2, _sol2 = float(sump_area), float(sump_base_elev), float(sump_ov_level)
                    _soc2, _soe2 = float(sump_ov_coeff), float(sump_ov_exp)
                    _pol2, _pfl2, _psh2 = float(pump_on), float(pump_off), float(pump_hsh)
                    _pcc2, _plc2, _pa2  = float(pump_k), float(pipe_k), float(pump_avail)

                    def _bfactory():
                        _b = Building(_fa)
                        if _eb:
                            _b.basement_area = _ba; _b.h_basement = 0.0
                            _b.z_basement = _bf; _b.basement_ceiling_elevation = _bc
                            if _bia2 > 0:
                                _b.basement_ingress = IngressPathway(
                                    height=_bih2, area=_bia2, coeff=_bic2,
                                    name='ext-basement-perimeter',
                                    source='outside', target='basement')
                            if _es and _sa2 > 0:
                                _b.sump_pump = SumpPump(
                                    sump_area=_sa2, sump_base_elevation=_sbe2,
                                    overflow_level=_sol2, overflow_coeff=_soc2,
                                    overflow_exponent=_soe2,
                                    pump_on_level=_pol2, pump_off_level=_pfl2,
                                    pump_shutoff_head=_psh2, pump_curve_coeff=_pcc2,
                                    pipe_loss_coeff=_plc2, pump_availability=_pa2)
                        return _b

                    _seed = int(frag_seed) if frag_seed > 0 else None
                    _mc_res = _frag.run_fragility_montecarlo(
                        building_factory=_bfactory,
                        paths=_fpaths, membranes=_fmems,
                        basement_fragility=None,
                        external_times=times_s, external_levels=_levels,
                        n_replicates=int(n_reps), dt=dt_s,
                        external_vel_times=v_times_s, external_velocities=v_vals,
                        seed=_seed,
                        progress_callback=_mc_cb,
                    )

                    # Percentile table
                    _pct_rows = []
                    _metric_labels = {
                        'peak_h_in':       'Peak GF depth (m)',
                        'peak_h_basement': 'Peak basement depth (m)',
                        'total_volume_in': 'Total volume in (m³)',
                    }
                    for _mk, _ml in _metric_labels.items():
                        if _mk in _mc_res.percentiles:
                            _row = {'Metric': _ml}
                            _row.update({
                                k: f'{v:.4f}' for k, v in _mc_res.percentiles[_mk].items()
                            })
                            _pct_rows.append(_row)

                    # State freq table
                    _sf_rows = []
                    for _elem, _freqs in sorted(_mc_res.state_frequencies.items()):
                        _row2 = {'Element': _elem}
                        for _i, _f in enumerate(_freqs):
                            _row2[f'≥ state {_i}'] = _fmt_pct(_f)
                        _sf_rows.append(_row2)

                    # Histogram data
                    _peak_vals = [rec.peak_h_in for rec in _mc_res.replicates]

                    # CSV outputs
                    _mc_dir  = tempfile.mkdtemp(prefix='mc_')
                    _rep_p   = os.path.join(_mc_dir, 'fragility_replicates.csv')
                    _sum_p   = os.path.join(_mc_dir, 'fragility_summary.csv')
                    _sf_p    = os.path.join(_mc_dir, 'fragility_state_freq.csv')
                    _frag.write_replicates_csv(_mc_res, _rep_p)
                    _frag.write_summary_csv(_mc_res, _sum_p)
                    _frag.write_state_freq_csv(_mc_res, _sf_p)

                    st.session_state.mc_result = dict(
                        n_reps=int(n_reps),
                        pct_rows=_pct_rows,
                        sf_rows=_sf_rows,
                        peak_vals=_peak_vals,
                        rep_csv=open(_rep_p, 'rb').read(),
                        sum_csv=open(_sum_p, 'rb').read(),
                        sf_csv=open(_sf_p,  'rb').read(),
                    )
                    with tab_mc_out:
                        _mc_prog.empty()

                except Exception as _mce:
                    with tab_mc_out:
                        st.error(f'Monte Carlo failed: {_mce}')

            _prog.progress(100, 'Done ✓')
            _stat.success('Simulation complete — see **Results** and **Diagnostics** tabs.')

        except Exception as _exc:
            _prog.empty()
            _stat.empty()
            with tab_results:
                st.error(f'Simulation error: {_exc}')
                with st.expander('Traceback'):
                    st.exception(_exc)


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — RESULTS
# ════════════════════════════════════════════════════════════════════════════

with tab_results:
    _r = st.session_state.run_result
    if _r is None:
        st.info('Configure inputs in the sidebar and press **▶ Run simulation**.')
    else:
        # ── KPI cards ─────────────────────────────────────────────────────────
        k1, k2, k3, k4 = st.columns(4)
        k1.metric('Peak ground-floor depth', _fmt_m(_r['h_pk_gf']))
        k2.metric(
            'Peak basement depth',
            _fmt_m(_r['h_pk_bsmt']) if _r['has_basement'] else '—')
        k3.metric(
            'Peak sump depth',
            _fmt_m(_r['h_pk_sump']) if _r['has_sump'] else '—')
        k4.metric('Total volume ingressed', _fmt_m3(_r['vol_in']))

        # Loss cards (only if available)
        if _r['bldg_loss'] is not None or _r['bsmt_loss'] is not None:
            st.divider()
            lc = st.columns(3)
            if _r['bldg_loss'] is not None:
                lc[0].metric('Building loss', f'£{_r["bldg_loss"]:,.0f}')
            if _r['bsmt_loss'] is not None:
                lc[1].metric('Basement loss', f'£{_r["bsmt_loss"]:,.0f}')
            if _r['bldg_loss'] is not None and _r['bsmt_loss'] is not None:
                lc[2].metric('Total loss',
                             f'£{_r["bldg_loss"]+_r["bsmt_loss"]:,.0f}')

        # ── Main simulation plot ──────────────────────────────────────────────
        st.divider()
        st.image(_r['sim_png_bytes'], width="stretch")

        # ── Narrative ─────────────────────────────────────────────────────────
        if _r['narrative']:
            st.markdown('### Key observations')
            for _b in _r['narrative']:
                st.markdown(f'- {_b}')

        # ── Animation ─────────────────────────────────────────────────────────
        if _r['anim_bytes']:
            st.divider()
            st.markdown('### Animation')
            st.image(_r['anim_bytes'], width="stretch")

        # ── Downloads ─────────────────────────────────────────────────────────
        st.divider()
        st.markdown('### Downloads')
        _dl_cols = st.columns(3)
        _dl_cols[0].download_button(
            '📥  Simulation plot',
            data=_r['sim_png_bytes'], file_name='simulation_result.png',
            mime='image/png', use_container_width=True)
        if _r['anim_bytes']:
            _dl_cols[1].download_button(
                '📥  Animation (GIF)',
                data=_r['anim_bytes'], file_name='simulation_animation.gif',
                mime='image/gif', use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — DIAGNOSTICS
# ════════════════════════════════════════════════════════════════════════════

with tab_diag:
    _r = st.session_state.run_result
    if _r is None:
        st.info('Run a simulation to see the diagnostics dashboard.')
    elif _r['dash_bytes'] is None:
        st.warning('Diagnostics data is unavailable for this simulation.')
    else:
        # ── Dashboard plot ─────────────────────────────────────────────────────
        st.image(_r['dash_bytes'], width="stretch")

        # ── Event table ───────────────────────────────────────────────────────
        if _r['ev_rows']:
            st.markdown('### Event summary')
            _ev_df = pd.DataFrame({
                'Metric': list(_r['ev_rows'].keys()),
                'Value':  list(_r['ev_rows'].values()),
            })
            st.dataframe(
                _ev_df, use_container_width=True, hide_index=True,
                column_config={
                    'Metric': st.column_config.TextColumn('Metric', width='large'),
                    'Value':  st.column_config.TextColumn('Value',  width='small'),
                })

        # ── Downloads ─────────────────────────────────────────────────────────
        st.divider()
        _dl2 = st.columns(2)
        _dl2[0].download_button(
            '📥  Dashboard (PNG)',
            data=_r['dash_bytes'], file_name='interpretation_dashboard.png',
            mime='image/png', use_container_width=True)
        if _r['diag_csv']:
            _dl2[1].download_button(
                '📥  Diagnostics (CSV)',
                data=_r['diag_csv'], file_name='diagnostics.csv',
                mime='text/csv', use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — MONTE CARLO
# ════════════════════════════════════════════════════════════════════════════

with tab_mc_out:
    _mc = st.session_state.mc_result
    if not enable_mc:
        st.info('Enable **Fragility Monte Carlo** in the sidebar to use this tab.')
    elif _mc is None and not run_button:
        st.info('Upload a fragility ingress CSV and press **▶ Run simulation**.')
    elif _mc is not None:
        # ── KPI strip ──────────────────────────────────────────────────────────
        _mn = np.mean(_mc['peak_vals'])
        _p50 = float(np.median(_mc['peak_vals']))
        _p90 = float(np.percentile(_mc['peak_vals'], 90))
        _frac_nonzero = sum(1 for v in _mc['peak_vals'] if v > 1e-6) / len(_mc['peak_vals'])

        kk1, kk2, kk3, kk4 = st.columns(4)
        kk1.metric('Replicates', f'{_mc["n_reps"]:,}')
        kk2.metric('Fraction flooded', _fmt_pct(_frac_nonzero))
        kk3.metric('Median peak depth', _fmt_m(_p50))
        kk4.metric('P90 peak depth',    _fmt_m(_p90))

        st.divider()

        # ── Histogram ─────────────────────────────────────────────────────────
        col_hist, col_pct = st.columns([3, 2])

        with col_hist:
            st.markdown('**Distribution of peak ground-floor depth**')
            _fig, _ax = plt.subplots(figsize=(6, 3.2))
            _fig.patch.set_facecolor('white')
            _ax.set_facecolor('#f9fafb')
            for _sp in ['top', 'right']:
                _ax.spines[_sp].set_visible(False)
            _ax.spines['bottom'].set_color('#c8cdd2')
            _ax.spines['left'].set_color('#c8cdd2')

            _nonzero = [v for v in _mc['peak_vals'] if v > 1e-6]
            _zero_n  = len(_mc['peak_vals']) - len(_nonzero)

            if _nonzero:
                _ax.hist(_nonzero, bins=min(30, max(10, len(_nonzero)//5)),
                         color='#2980b9', edgecolor='white', linewidth=0.4, alpha=0.85)
            if _zero_n > 0:
                _ax.bar([0], [_zero_n], width=max(_ax.get_xlim()[1], 0.01) * 0.04
                        if _ax.get_xlim()[1] > 0 else 0.005,
                        color='#27ae60', alpha=0.7, label=f'Zero ingress  (n={_zero_n})')
                _ax.legend(fontsize=8)

            for _pv, _pc, _col in [(_p50, 'P50', '#e67e22'), (_p90, 'P90', '#c0392b')]:
                if _pv > 0:
                    _ax.axvline(_pv, color=_col, lw=1.5, ls='--',
                                label=f'{_pc} = {_pv:.3f} m')
            _ax.legend(fontsize=8)
            _ax.set_xlabel('Peak interior depth (m)', fontsize=9, color='#2c3140')
            _ax.set_ylabel('Number of replicates',    fontsize=9, color='#2c3140')
            _ax.tick_params(colors='#4a5260', labelsize=8)
            _fig.tight_layout()
            st.pyplot(_fig, use_container_width=True)
            plt.close(_fig)

        with col_pct:
            st.markdown('**Percentile summary**')
            if _mc['pct_rows']:
                _pct_df = pd.DataFrame(_mc['pct_rows']).set_index('Metric')
                st.dataframe(_pct_df, use_container_width=True)
            else:
                st.caption('No percentile data.')

        # ── State frequencies ─────────────────────────────────────────────────
        if _mc['sf_rows']:
            st.divider()
            st.markdown('**Element exceedance frequencies**')
            st.caption(
                'Each value is the fraction of replicates in which the external water level '
                'reached or exceeded the element\'s sampled capacity threshold.')
            _sf_df = pd.DataFrame(_mc['sf_rows']).set_index('Element')
            st.dataframe(_sf_df, use_container_width=True)

        # ── Downloads ─────────────────────────────────────────────────────────
        st.divider()
        st.markdown('### Downloads')
        _mc_dl = st.columns(3)
        _mc_dl[0].download_button(
            '📥  Replicates (CSV)', data=_mc['rep_csv'],
            file_name='fragility_replicates.csv', mime='text/csv',
            use_container_width=True)
        _mc_dl[1].download_button(
            '📥  Summary (CSV)', data=_mc['sum_csv'],
            file_name='fragility_summary.csv', mime='text/csv',
            use_container_width=True)
        _mc_dl[2].download_button(
            '📥  State freq (CSV)', data=_mc['sf_csv'],
            file_name='fragility_state_freq.csv', mime='text/csv',
            use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — BATCH ANALYSIS
# ════════════════════════════════════════════════════════════════════════════

with tab_batch:
    st.markdown(
        'Upload the output CSV from a batch parametric run to view aggregate plots. '
        'Required columns: `h_peak_ext`, `h_peak_int`. '
        'Optional: `aggregate_content_loss`.')
    st.divider()

    uploaded_batch = st.file_uploader(
        'Batch results CSV', type=['csv'],
        help='Output of batch.py (batch_results.csv) or similar.')

    if uploaded_batch is not None:
        try:
            _btxt  = uploaded_batch.getvalue().decode('utf-8').splitlines()
            _brows = list(csv.DictReader(_btxt))
            if not _brows:
                st.warning('File is empty or has no data rows.')
            else:
                _h_ext  = [float(r['h_peak_ext']) for r in _brows]
                _h_int  = [float(r['h_peak_int']) for r in _brows]
                _has_loss = 'aggregate_content_loss' in _brows[0]
                _losses   = [float(r['aggregate_content_loss']) for r in _brows] if _has_loss else None

                _bs_col_l, _bs_col_r = st.columns(2) if _has_loss else (st.columns(1)[0], None)

                with _bs_col_l:
                    st.markdown('**Peak depth: exterior vs interior**')
                    _sc_p = os.path.join(tempfile.gettempdir(), 'batch_scatter.png')
                    viz.save_batch_scatter(_h_ext, _h_int, _sc_p)
                    with open(_sc_p, 'rb') as _f:
                        _sc_b = _f.read()
                    st.image(_sc_b, width="stretch")
                    st.download_button(
                        '📥  Scatter plot (PNG)', data=_sc_b,
                        file_name='batch_scatter.png', mime='image/png',
                        use_container_width=True)

                if _has_loss and _bs_col_r is not None:
                    with _bs_col_r:
                        st.markdown('**Aggregate loss vs exterior depth**')
                        _ls_p = os.path.join(tempfile.gettempdir(), 'batch_loss.png')
                        viz.save_loss_scatter(_h_ext, _losses, _ls_p)
                        with open(_ls_p, 'rb') as _f:
                            _ls_b = _f.read()
                        st.image(_ls_b, width="stretch")
                        st.download_button(
                            '📥  Loss plot (PNG)', data=_ls_b,
                            file_name='batch_loss_scatter.png', mime='image/png',
                            use_container_width=True)

                # Summary stats
                st.divider()
                st.markdown('**Summary statistics**')
                _stats_df = pd.DataFrame({
                    'Metric': ['N runs', 'Peak ext depth (max)', 'Peak int depth (max)',
                               'Fraction flooded (h_in > 0.001 m)'],
                    'Value':  [
                        str(len(_brows)),
                        _fmt_m(max(_h_ext)),
                        _fmt_m(max(_h_int)),
                        _fmt_pct(sum(1 for h in _h_int if h > 0.001) / len(_h_int)),
                    ],
                })
                st.dataframe(_stats_df, use_container_width=True, hide_index=True)

        except KeyError as _ke:
            st.error(f'Missing required column: {_ke}')
        except Exception as _exc:
            st.error(f'Failed to process batch file: {_exc}')
